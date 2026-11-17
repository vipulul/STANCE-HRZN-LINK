// ============================================================================
// STANCE // HRZN-LINK — ESP32-S3 Thin-Client HUD Firmware (HRZN-01)
// ============================================================================
// Philosophy:
//   - Thin Client / Smart Host: no hardcoded UI layouts or local menus.
//   - Receives pre-rendered, vertically mirrored JPEG / RGB565 frames over WS.
//   - Receives calibration & actuation commands via JSON text frames.
//   - Compatible with Arduino IDE 2.x and `arduino-cli` (`sketch.yaml`).
// ============================================================================

#include <Arduino.h>
#include <WiFi.h>
#include <math.h>

#define LGFX_USE_V1
#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include <LovyanGFX.hpp>
#include <WebSocketsClient.h>

#include "boot_animation.h"
#include "config.h"

#if __has_include("secrets.h")
  #include "secrets.h"
#else
  #warning "secrets.h not found — using secrets.example.h placeholders. Copy secrets.example.h to secrets.h."
  #include "secrets.example.h"
#endif

// ----------------------------------------------------------------------------
// LovyanGFX Display Configuration — IPS ILI9488 (320x480 Native / 480x320 Landscape)
// ----------------------------------------------------------------------------
class HrznDisplay : public lgfx::LGFX_Device {
  lgfx::Panel_ILI9488 _panelInstance;
  lgfx::Bus_SPI       _busInstance;

public:
  HrznDisplay() {
    {
      auto cfg = _busInstance.config();
      cfg.spi_host    = SPI2_HOST;
      cfg.spi_mode    = 0;
      cfg.freq_write  = 60000000;   // 60 MHz SPI clock (matches verified examples/main.cpp)
      cfg.pin_sclk    = TFT_SCLK;
      cfg.pin_mosi    = TFT_MOSI;
      cfg.pin_miso    = -1;
      cfg.pin_dc      = TFT_DC;
      cfg.dma_channel = SPI_DMA_CH_AUTO;
      _busInstance.config(cfg);
      _panelInstance.setBus(&_busInstance);
    }

    {
      auto cfg = _panelInstance.config();
      cfg.pin_cs           = TFT_CS;
      cfg.pin_rst          = TFT_RST;
      cfg.pin_busy         = -1;
      cfg.memory_width     = 320;
      cfg.memory_height    = 480;
      cfg.panel_width      = 320;
      cfg.panel_height     = 480;
      cfg.offset_x         = 0;
      cfg.offset_y         = 0;
      cfg.offset_rotation  = 0;
      cfg.dummy_read_pixel = 8;
      cfg.dummy_read_bits  = 1;
      cfg.readable         = false;
      cfg.invert           = true;
      cfg.rgb_order        = false;
      cfg.bus_shared       = false;
      _panelInstance.config(cfg);
    }

    setPanel(&_panelInstance);
  }
};

// ----------------------------------------------------------------------------
// Binary Frame Header (14 bytes, little-endian — matches docs/PROTOCOL.md)
// ----------------------------------------------------------------------------
static constexpr uint8_t FRAME_MAGIC_0    = 0x48; // 'H'
static constexpr uint8_t FRAME_MAGIC_1    = 0x5A; // 'Z'
static constexpr uint8_t FRAME_FMT_RGB565 = 0x01;
static constexpr uint8_t FRAME_FMT_JPEG   = 0x02;

struct __attribute__((packed)) HrznFrameHeader {
  uint8_t  magic[2];
  uint8_t  version;
  uint8_t  format;
  uint8_t  flags;
  uint8_t  seq;
  uint16_t x;
  uint16_t y;
  uint16_t w;
  uint16_t h;
};

// ----------------------------------------------------------------------------
// Runtime State
// ----------------------------------------------------------------------------
HrznDisplay      display;
WebSocketsClient webSocket;
Servo            flapServo;

// Calibrated servo parameters (synced from server, initialized to safe defaults)
uint16_t servoClosedUs     = SERVO_CLOSED_US;
uint16_t servoOpenUs       = SERVO_OPEN_US;
uint16_t defaultSweepMs    = SERVO_DEFAULT_SWEEP_MS;
uint16_t settleDetachMs    = SERVO_SETTLE_DETACH_MS;
uint8_t  currentBrightness = TFT_DEFAULT_BRIGHTNESS;

// Non-blocking cosine-eased servo sweep state
struct ServoMotion {
  bool     moving        = false;
  bool     waitingDetach = false;
  uint16_t startUs       = SERVO_CLOSED_US;
  uint16_t targetUs      = SERVO_CLOSED_US;
  uint16_t currentUs     = SERVO_CLOSED_US;
  uint32_t startMs       = 0;
  uint32_t durationMs    = SERVO_DEFAULT_SWEEP_MS;
  uint32_t settledAtMs   = 0;
  uint8_t  targetPct     = 0;
} servoMotion;

// Connectivity & diagnostics state
bool        wsConnected            = false;
bool        hasReceivedFrame       = false;
wl_status_t lastWifiStatus         = WL_IDLE_STATUS;
uint32_t    lastWifiCheckMs        = 0;
uint32_t    lastTelemetryMs        = 0;
uint32_t    lastDiagMs             = 0;
uint32_t    frameCounter           = 0;
uint32_t    totalFramesRx          = 0;
int16_t     lastFrameSeq           = -1;
uint32_t    fpsWindowStartMs       = 0;
float       measuredFps            = 0.0f;
char        lastWifiStatusText[64] = "";
char        lastWsStatusText[64]   = "";

// ----------------------------------------------------------------------------
// Diagnostic Helpers
// ----------------------------------------------------------------------------
static const char* wifiStatusToString(wl_status_t status) {
  switch (status) {
    case WL_IDLE_STATUS:     return "WL_IDLE_STATUS";
    case WL_NO_SSID_AVAIL:   return "WL_NO_SSID_AVAIL";
    case WL_SCAN_COMPLETED:  return "WL_SCAN_COMPLETED";
    case WL_CONNECTED:       return "WL_CONNECTED";
    case WL_CONNECT_FAILED:  return "WL_CONNECT_FAILED";
    case WL_CONNECTION_LOST: return "WL_CONNECTION_LOST";
    case WL_DISCONNECTED:    return "WL_DISCONNECTED";
    default:                 return "WL_UNKNOWN";
  }
}

static void setBacklightBrightness(uint8_t brightness) {
  currentBrightness = brightness;
  if (brightness == 255) {
#if defined(ESP_ARDUINO_VERSION) && (ESP_ARDUINO_VERSION >= ESP_ARDUINO_VERSION_VAL(3, 0, 0))
    ledcDetach(TFT_BL);
#else
    ledcDetachPin(TFT_BL);
#endif
    pinMode(TFT_BL, OUTPUT);
    digitalWrite(TFT_BL, HIGH);
  } else if (brightness == 0) {
#if defined(ESP_ARDUINO_VERSION) && (ESP_ARDUINO_VERSION >= ESP_ARDUINO_VERSION_VAL(3, 0, 0))
    ledcDetach(TFT_BL);
#else
    ledcDetachPin(TFT_BL);
#endif
    pinMode(TFT_BL, OUTPUT);
    digitalWrite(TFT_BL, LOW);
  } else {
    analogWrite(TFT_BL, brightness);
  }
  Serial.printf("[BL] GPIO %d brightness set to %u/255\n", TFT_BL, brightness);
}

static void updateBootScreenStatus(const char* wifiMsg, const char* wsMsg) {
  if (hasReceivedFrame) return;

  bool updateWifi = (strcmp(wifiMsg, lastWifiStatusText) != 0);
  bool updateWs   = (strcmp(wsMsg, lastWsStatusText) != 0);
  if (!updateWifi && !updateWs) return;

  display.startWrite();
  display.setTextSize(1);
  if (updateWifi) {
    display.fillRect(14, 146, display.width() - 28, 16, TFT_BLACK);
    display.setCursor(14, 146);
    display.setTextColor(WiFi.status() == WL_CONNECTED ? TFT_GREEN : TFT_YELLOW, TFT_BLACK);
    display.printf("WIFI: %s", wifiMsg);
    snprintf(lastWifiStatusText, sizeof(lastWifiStatusText), "%s", wifiMsg);
  }
  if (updateWs) {
    display.fillRect(14, 200, display.width() - 28, 16, TFT_BLACK);
    display.setCursor(14, 200);
    display.setTextColor(wsConnected ? TFT_GREEN : TFT_ORANGE, TFT_BLACK);
    display.printf("LINK: %s", wsMsg);
    snprintf(lastWsStatusText, sizeof(lastWsStatusText), "%s", wsMsg);
  }
  display.endWrite();
}

static void initBootScreen(const char* wifiMsg, const char* wsMsg) {
  if (hasReceivedFrame) return;

  display.startWrite();
  display.fillScreen(TFT_BLACK);
  display.drawRect(4, 4, display.width() - 8, display.height() - 8, TFT_CYAN);

  // Header
  display.setTextSize(2);
  display.setTextColor(TFT_CYAN, TFT_BLACK);
  display.setCursor(14, 14);
  display.print("STANCE // HRZN-01");

  display.setTextSize(1);
  display.setTextColor(TFT_LIGHTGREY, TFT_BLACK);
  display.setCursor(14, 40);
  display.print("IPS ILI9488 Boot & Link Diagnostics");

  // Color test bars to verify display + backlight immediately on boot
  display.fillRect(14, 60, 108, 18, TFT_RED);
  display.fillRect(128, 60, 108, 18, TFT_GREEN);
  display.fillRect(242, 60, 108, 18, TFT_BLUE);
  display.fillRect(356, 60, 108, 18, TFT_CYAN);

  // Pinout reference
  display.setTextColor(TFT_DARKGREY, TFT_BLACK);
  display.setCursor(14, 92);
  display.printf("PINS CS:%d DC:%d RST:%d SDI:%d SCK:%d BL:%d",
                 TFT_CS, TFT_DC, TFT_RST, TFT_MOSI, TFT_SCLK, TFT_BL);

  // Static Wi-Fi & WebSocket labels
  display.setTextColor(TFT_WHITE, TFT_BLACK);
  display.setCursor(14, 126);
  display.printf("SSID: %s", WIFI_SSID);

  display.setCursor(14, 180);
  display.printf("HOST: ws://%s:%u%s", LINK_HOST, LINK_PORT, LINK_WS_PATH);

  display.setTextColor(TFT_CYAN, TFT_BLACK);
  display.setCursor(14, 286);
  display.printf("BRT: %u/255  HEAP: %u KB", currentBrightness, ESP.getFreeHeap() / 1024);
  display.endWrite();

  lastWifiStatusText[0] = '\0';
  lastWsStatusText[0]   = '\0';
  updateBootScreenStatus(wifiMsg, wsMsg);
}

static void returnToWaitingScreen(const char* wifiMsg, const char* wsMsg) {
  if (hasReceivedFrame) {
    hasReceivedFrame = false;
    lastFrameSeq     = -1;
    frameCounter     = 0;
    measuredFps      = 0.0f;
    initBootScreen(wifiMsg, wsMsg);
  } else {
    updateBootScreenStatus(wifiMsg, wsMsg);
  }
}

// ----------------------------------------------------------------------------
// Servo Helpers
// ----------------------------------------------------------------------------
static uint16_t clampServoUs(int32_t us) {
  if (us < SERVO_MIN_SAFE_US) return SERVO_MIN_SAFE_US;
  if (us > SERVO_MAX_SAFE_US) return SERVO_MAX_SAFE_US;
  return static_cast<uint16_t>(us);
}

static uint16_t pctToServoUs(uint8_t pct) {
  uint8_t clampedPct = (pct > 100) ? 100 : pct;
  int32_t span = static_cast<int32_t>(servoOpenUs) - static_cast<int32_t>(servoClosedUs);
  int32_t target = static_cast<int32_t>(servoClosedUs) + (span * clampedPct) / 100;
  return clampServoUs(target);
}

static void startServoSweepPct(uint8_t pct, uint16_t durationMs) {
  uint8_t clampedPct = (pct > 100) ? 100 : pct;
  uint16_t targetUs  = pctToServoUs(clampedPct);
  uint16_t sweepMs   = (durationMs > 0) ? durationMs : defaultSweepMs;

  if (!flapServo.attached()) {
    flapServo.setPeriodHertz(50);
    flapServo.attach(SERVO_PIN, SERVO_MIN_SAFE_US, SERVO_MAX_SAFE_US);
  }

  servoMotion.startUs       = servoMotion.currentUs;
  servoMotion.targetUs      = targetUs;
  servoMotion.targetPct     = clampedPct;
  servoMotion.startMs       = millis();
  servoMotion.durationMs    = (sweepMs < 50) ? 50 : sweepMs;
  servoMotion.moving        = true;
  servoMotion.waitingDetach = false;

  Serial.printf("[SERVO] Sweep -> %u%% (%u us -> %u us in %lu ms)\n",
                clampedPct, servoMotion.startUs, targetUs,
                static_cast<unsigned long>(servoMotion.durationMs));
}

static void updateServoMotion() {
  uint32_t now = millis();

  if (servoMotion.moving) {
    uint32_t elapsed = now - servoMotion.startMs;
    if (elapsed >= servoMotion.durationMs) {
      servoMotion.currentUs = servoMotion.targetUs;
      flapServo.writeMicroseconds(servoMotion.currentUs);
      servoMotion.moving        = false;
      servoMotion.waitingDetach = true;
      servoMotion.settledAtMs   = now;
      Serial.printf("[SERVO] Reached %u us; detaching in %u ms\n",
                    servoMotion.currentUs, settleDetachMs);
    } else {
      float t     = static_cast<float>(elapsed) / static_cast<float>(servoMotion.durationMs);
      float eased = 0.5f * (1.0f - cosf(static_cast<float>(M_PI) * t));
      int32_t delta = static_cast<int32_t>(servoMotion.targetUs) -
                      static_cast<int32_t>(servoMotion.startUs);
      uint16_t nextUs = clampServoUs(static_cast<int32_t>(servoMotion.startUs) +
                                     lroundf(static_cast<float>(delta) * eased));
      if (nextUs != servoMotion.currentUs) {
        servoMotion.currentUs = nextUs;
        flapServo.writeMicroseconds(nextUs);
      }
    }
  } else if (servoMotion.waitingDetach) {
    if (now - servoMotion.settledAtMs >= settleDetachMs) {
      if (flapServo.attached()) {
        flapServo.detach();
      }
      servoMotion.waitingDetach = false;
      Serial.println("[SERVO] Detached to prevent jitter/buzz");
    }
  }
}

static String buildDeviceId() {
  uint8_t mac[6];
  WiFi.macAddress(mac);
  char buf[24];
  snprintf(buf, sizeof(buf), "hrzn-%02x%02x%02x%02x%02x%02x",
           mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  return String(buf);
}

static void sendDeviceHello() {
  JsonDocument doc;
  doc["type"]             = "device_hello";
  doc["protocol_version"] = PROTOCOL_VERSION;
  doc["device_id"]        = buildDeviceId();
  doc["hw_version"]       = HW_VERSION_STR;
  doc["fw_version"]       = FW_VERSION_STR;

  JsonObject disp = doc["display"].to<JsonObject>();
  disp["width"]                 = TFT_WIDTH;
  disp["height"]                = TFT_HEIGHT;
  disp["needs_vertical_mirror"] = true;
  JsonArray fmts = disp["formats"].to<JsonArray>();
  fmts.add("RGB565");
  fmts.add("JPEG");

  JsonObject caps = doc["capabilities"].to<JsonObject>();
  caps["servo"]         = true;
  caps["backlight_pwm"] = true;

  String out;
  serializeJson(doc, out);
  webSocket.sendTXT(out);
  Serial.printf("[WS TX] %s\n", out.c_str());
}

static void sendTelemetryReport() {
  if (!wsConnected) return;

  JsonDocument doc;
  doc["type"]              = "telemetry_report";
  doc["uptime_s"]          = millis() / 1000UL;
  doc["rssi_dbm"]          = WiFi.RSSI();
  doc["free_heap"]         = ESP.getFreeHeap();
  doc["flap_position_pct"] = servoMotion.targetPct;
  doc["servo_us"]          = servoMotion.currentUs;
  doc["servo_attached"]    = flapServo.attached();
  doc["brightness"]        = currentBrightness;
  doc["fps"]               = measuredFps;

  String out;
  serializeJson(doc, out);
  webSocket.sendTXT(out);
}

// ----------------------------------------------------------------------------
// JSON Control & Binary Frame Handlers
// ----------------------------------------------------------------------------
static void handleJsonCommand(const uint8_t* payload, size_t length) {
  Serial.printf("[WS RX TEXT] (%u bytes): %.*s\n",
                static_cast<unsigned>(length),
                static_cast<int>(length),
                reinterpret_cast<const char*>(payload));

  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  if (err) {
    Serial.printf("[WS] JSON parse error: %s\n", err.c_str());
    return;
  }

  const char* type = doc["type"] | "";

  if (strcmp(type, "config_sync") == 0) {
    servoClosedUs     = clampServoUs(doc["servo_closed_us"] | SERVO_CLOSED_US);
    servoOpenUs       = clampServoUs(doc["servo_open_us"]   | SERVO_OPEN_US);
    defaultSweepMs    = doc["sweep_duration_ms"] | SERVO_DEFAULT_SWEEP_MS;
    settleDetachMs    = doc["settle_detach_ms"]  | SERVO_SETTLE_DETACH_MS;
    uint8_t syncedBrt = doc["brightness"]        | TFT_DEFAULT_BRIGHTNESS;
    // Protect against an accidentally saved 0 brightness blanking the screen on connect
    uint8_t targetBrt = (syncedBrt > 0) ? syncedBrt : TFT_DEFAULT_BRIGHTNESS;
    setBacklightBrightness(targetBrt);

    const char* flapState = doc["flap_state"] | "closed";
    uint8_t targetPct     = doc["target_angle_pct"] | (strcmp(flapState, "open") == 0 ? 100 : 0);
    Serial.printf("[CFG] Synced: closed=%u open=%u sweep=%u ms bright=%u target=%u%%\n",
                  servoClosedUs, servoOpenUs, defaultSweepMs, currentBrightness, targetPct);
    startServoSweepPct(targetPct, defaultSweepMs);
  }
  else if (strcmp(type, "flap_move") == 0) {
    const char* state = doc["state"] | "custom";
    uint16_t duration = doc["duration_ms"] | 0;
    uint8_t targetPct = 0;

    if (strcmp(state, "open") == 0) {
      targetPct = 100;
    } else if (strcmp(state, "closed") == 0) {
      targetPct = 0;
    } else {
      targetPct = doc["position_pct"] | servoMotion.targetPct;
    }
    startServoSweepPct(targetPct, duration);
  }
  else if (strcmp(type, "set_servo_limits") == 0) {
    servoClosedUs  = clampServoUs(doc["closed_us"]         | servoClosedUs);
    servoOpenUs    = clampServoUs(doc["open_us"]           | servoOpenUs);
    defaultSweepMs = doc["sweep_duration_ms"]              | defaultSweepMs;
    settleDetachMs = doc["settle_detach_ms"]               | settleDetachMs;
    Serial.printf("[CFG] Updated limits: closed=%u open=%u sweep=%u ms detach=%u ms\n",
                  servoClosedUs, servoOpenUs, defaultSweepMs, settleDetachMs);
  }
  else if (strcmp(type, "set_brightness") == 0) {
    uint8_t brightness = doc["brightness"] | currentBrightness;
    setBacklightBrightness(brightness);
    Serial.printf("[CFG] Brightness set to %u\n", currentBrightness);
  }
  else {
    Serial.printf("[WS] Unhandled JSON message type: %s\n", type);
  }
}

static void handleBinaryFrame(const uint8_t* payload, size_t length) {
  if (length < sizeof(HrznFrameHeader)) {
    Serial.printf("[FRAME] Packet too small (%u bytes)\n", static_cast<unsigned>(length));
    return;
  }

  HrznFrameHeader hdr;
  memcpy(&hdr, payload, sizeof(HrznFrameHeader));

  if (hdr.magic[0] != FRAME_MAGIC_0 || hdr.magic[1] != FRAME_MAGIC_1 ||
      hdr.version != PROTOCOL_VERSION) {
    Serial.printf("[FRAME] Invalid header magic=%02X %02X ver=%u\n",
                  hdr.magic[0], hdr.magic[1], hdr.version);
    return;
  }

  const uint8_t* pixelData = payload + sizeof(HrznFrameHeader);
  size_t pixelLen          = length - sizeof(HrznFrameHeader);

  if (totalFramesRx == 0 || (totalFramesRx % 20 == 0)) {
    Serial.printf("[FRAME #%lu] seq=%u fmt=0x%02X rect=(%u,%u,%u,%u) payload=%u bytes\n",
                  static_cast<unsigned long>(totalFramesRx + 1),
                  hdr.seq, hdr.format, hdr.x, hdr.y, hdr.w, hdr.h,
                  static_cast<unsigned>(pixelLen));
  }

  if (hdr.format == FRAME_FMT_RGB565) {
    size_t expectedLen = static_cast<size_t>(hdr.w) * static_cast<size_t>(hdr.h) * 2;
    if (pixelLen < expectedLen) {
      Serial.printf("[FRAME] RGB565 underrun: got %u, expected %u\n",
                    static_cast<unsigned>(pixelLen), static_cast<unsigned>(expectedLen));
      return;
    }
    display.setSwapBytes(true);
    display.startWrite();
    display.pushImage(hdr.x, hdr.y, hdr.w, hdr.h,
                      reinterpret_cast<const uint16_t*>(pixelData));
    display.endWrite();
  }
  else if (hdr.format == FRAME_FMT_JPEG) {
    display.setSwapBytes(false);
    bool ok = display.drawJpg(pixelData, pixelLen, hdr.x, hdr.y, hdr.w, hdr.h);
    if (!ok) {
      Serial.printf("[FRAME] drawJpg returned false (len=%u)\n", static_cast<unsigned>(pixelLen));
    }
  }
  else {
    Serial.printf("[FRAME] Unsupported pixel format: 0x%02X\n", hdr.format);
    return;
  }

  hasReceivedFrame = true;
  if (static_cast<int16_t>(hdr.seq) != lastFrameSeq) {
    lastFrameSeq = static_cast<int16_t>(hdr.seq);
    totalFramesRx++;
    frameCounter++;

    uint32_t now = millis();
    uint32_t dt  = now - fpsWindowStartMs;
    if (dt >= 2000) {
      measuredFps      = (static_cast<float>(frameCounter) * 1000.0f) / static_cast<float>(dt);
      frameCounter     = 0;
      fpsWindowStartMs = now;
    }
  }
}

static void onWebSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_DISCONNECTED:
      Serial.printf("[WS] Disconnected (wasConnected=%s, len=%u)\n",
                    wsConnected ? "true" : "false",
                    static_cast<unsigned>(length));
      if (length > 0 && payload != nullptr) {
        Serial.printf("[WS] Disconnect reason: %.*s\n",
                      static_cast<int>(length),
                      reinterpret_cast<const char*>(payload));
      }
      wsConnected = false;
      if (WiFi.status() == WL_CONNECTED) {
        String ipStr = WiFi.localIP().toString();
        returnToWaitingScreen(ipStr.c_str(), "WS Disconnected (waiting for server...)");
      } else {
        returnToWaitingScreen(wifiStatusToString(WiFi.status()), "Waiting for Wi-Fi");
      }
      break;

    case WStype_CONNECTED: {
      wsConnected = true;
      Serial.printf("[WS] Connected to ws://%s:%u%s\n",
                    LINK_HOST, LINK_PORT, LINK_WS_PATH);
      String ipStr = WiFi.localIP().toString();
      updateBootScreenStatus(ipStr.c_str(), "WS Connected! Waiting for frames...");
      sendDeviceHello();
      break;
    }

    case WStype_TEXT:
      handleJsonCommand(payload, length);
      break;

    case WStype_BIN:
      handleBinaryFrame(payload, length);
      break;

    case WStype_ERROR:
      Serial.println("[WS] Socket error");
      break;

    default:
      Serial.printf("[WS] Event type=%d len=%u\n", static_cast<int>(type),
                    static_cast<unsigned>(length));
      break;
  }
}

// ----------------------------------------------------------------------------
// Wi-Fi Supervision (Non-blocking)
// ----------------------------------------------------------------------------
static void ensureWifiConnected() {
  wl_status_t st = WiFi.status();

  if (st != lastWifiStatus) {
    Serial.printf("[WIFI] Status changed: %s -> %s\n",
                  wifiStatusToString(lastWifiStatus),
                  wifiStatusToString(st));
    lastWifiStatus = st;

    if (st == WL_CONNECTED) {
      String ipStr = WiFi.localIP().toString();
      Serial.printf("[WIFI] Connected! IP=%s GW=%s DNS=%s RSSI=%d dBm\n",
                    ipStr.c_str(),
                    WiFi.gatewayIP().toString().c_str(),
                    WiFi.dnsIP().toString().c_str(),
                    WiFi.RSSI());
      updateBootScreenStatus(ipStr.c_str(), wsConnected ? "WS Connected" : "Connecting WS...");
    } else {
      wsConnected = false;
      returnToWaitingScreen(wifiStatusToString(st), "Waiting for Wi-Fi");
    }
  }

  if (st == WL_CONNECTED) return;

  uint32_t now = millis();
  if (now - lastWifiCheckMs < WIFI_RECONNECT_INTERVAL_MS) return;
  lastWifiCheckMs = now;

  Serial.printf("[WIFI] Re-attempting WiFi.begin('%s') (current=%s)...\n",
                WIFI_SSID, wifiStatusToString(st));
  WiFi.disconnect(false);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
}

static void printPeriodicDiagnostics() {
  uint32_t now = millis();
  if (now - lastDiagMs < SERIAL_DIAG_INTERVAL_MS) return;
  lastDiagMs = now;

  wl_status_t st = WiFi.status();
  Serial.printf("[DIAG t=%lus] wifi=%s ip=%s rssi=%d ws=%s target=ws://%s:%u%s frames=%lu heap=%u maxAlloc=%u\n",
                static_cast<unsigned long>(now / 1000UL),
                wifiStatusToString(st),
                (st == WL_CONNECTED) ? WiFi.localIP().toString().c_str() : "0.0.0.0",
                (st == WL_CONNECTED) ? WiFi.RSSI() : 0,
                wsConnected ? "CONNECTED" : "DISCONNECTED",
                LINK_HOST, LINK_PORT, LINK_WS_PATH,
                static_cast<unsigned long>(totalFramesRx),
                ESP.getFreeHeap(),
                ESP.getMaxAllocHeap());
}

// ----------------------------------------------------------------------------
// Arduino Entry Points
// ----------------------------------------------------------------------------
void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  uint32_t serialWaitStart = millis();
  while (!Serial && (millis() - serialWaitStart < 1500)) {
    delay(10);
  }

  Serial.println();
  Serial.println("===========================================");
  Serial.printf(" STANCE // HRZN-LINK Firmware (%s v%s)\n", HW_VERSION_STR, FW_VERSION_STR);
  Serial.println("===========================================");
  Serial.printf("[BOOT] Display: IPS ILI9488 (%dx%d)\n", TFT_WIDTH, TFT_HEIGHT);
  Serial.printf("[BOOT] Pins: CS=%d RST=%d DC=%d SDI/MOSI=%d SCK=%d BL=%d SERVO=%d\n",
                TFT_CS, TFT_RST, TFT_DC, TFT_MOSI, TFT_SCLK, TFT_BL, SERVO_PIN);
  Serial.printf("[BOOT] Heap=%u bytes | MaxAlloc=%u bytes | PSRAM=%u bytes\n",
                ESP.getFreeHeap(), ESP.getMaxAllocHeap(), ESP.getPsramSize());
  Serial.printf("[BOOT] Target WiFi='%s' -> Server=ws://%s:%u%s\n",
                WIFI_SSID, LINK_HOST, LINK_PORT, LINK_WS_PATH);

  // Initialize IPS ILI9488 display (480x320 landscape) and play modular boot animation
  bool dispOk = display.init();
  display.setRotation(1);
  display.setSwapBytes(true);
  Serial.printf("[DISP] init=%s logical=%dx%d brightness=%u\n",
                dispOk ? "OK" : "FAIL",
                display.width(), display.height(), currentBrightness);

  playBootAnimation(display, setBacklightBrightness, TFT_DEFAULT_BRIGHTNESS);
  initBootScreen("Connecting Wi-Fi...", "Waiting for Wi-Fi");

  // Initialize servo on LEDC Timer 2 so it never conflicts with backlight or Timer 0
  ESP32PWM::allocateTimer(2);
  servoMotion.currentUs = servoClosedUs;

  // Connect Wi-Fi & configure non-blocking WebSocket client
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  lastWifiCheckMs  = millis();
  lastDiagMs       = millis();
  fpsWindowStartMs = millis();

  webSocket.begin(LINK_HOST, LINK_PORT, LINK_WS_PATH);
  webSocket.onEvent(onWebSocketEvent);
  webSocket.setReconnectInterval(WS_RECONNECT_INTERVAL_MS);
}

void loop() {
  ensureWifiConnected();

  if (WiFi.status() == WL_CONNECTED) {
    webSocket.loop();
  }

  updateServoMotion();
  printPeriodicDiagnostics();

  uint32_t now = millis();
  if (wsConnected && (now - lastTelemetryMs >= TELEMETRY_INTERVAL_MS)) {
    lastTelemetryMs = now;
    sendTelemetryReport();
  }
}
