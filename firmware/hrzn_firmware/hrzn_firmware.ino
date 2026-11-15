// ============================================================================
// STANCE // HRZN-LINK — ESP32-S3 Thin-Client HUD Firmware (HRZN-01)
// ============================================================================
// Philosophy:
//   - Thin Client / Smart Host: no hardcoded UI layouts or local menus.
//   - Receives pre-rendered, vertically mirrored RGB565 / JPEG frames over WS.
//   - Receives calibration & actuation commands via JSON text frames.
//   - Compatible with Arduino IDE 2.x and `arduino-cli` (`sketch.yaml`).
// ============================================================================

#include <Arduino.h>
#include <WiFi.h>
#include <math.h>

#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include <LovyanGFX.hpp>
#include <WebSocketsClient.h>

#include "config.h"

#if __has_include("secrets.h")
  #include "secrets.h"
#else
  #warning "secrets.h not found — using secrets.example.h placeholders. Copy secrets.example.h to secrets.h."
  #include "secrets.example.h"
#endif

// ----------------------------------------------------------------------------
// LovyanGFX Display Configuration (Placeholder SPI TFT Setup)
// Adjust Panel_* class (e.g. Panel_ST7789 / Panel_ILI9341) to match your TFT.
// ----------------------------------------------------------------------------
class HrznDisplay : public lgfx::LGFX_Device {
  lgfx::Panel_ST7789 _panelInstance;
  lgfx::Bus_SPI      _busInstance;
  lgfx::Light_PWM    _lightInstance;

public:
  HrznDisplay() {
    {
      auto cfg = _busInstance.config();
      cfg.spi_host    = SPI2_HOST;
      cfg.spi_mode    = 0;
      cfg.freq_write  = 40000000;
      cfg.freq_read   = 16000000;
      cfg.spi_3wire   = false;
      cfg.use_lock    = true;
      cfg.dma_channel = SPI_DMA_CH_AUTO;
      cfg.pin_sclk    = TFT_SCLK;
      cfg.pin_mosi    = TFT_MOSI;
      cfg.pin_miso    = -1;
      cfg.pin_dc      = TFT_DC;
      _busInstance.config(cfg);
      _panelInstance.setBus(&_busInstance);
    }

    {
      auto cfg = _panelInstance.config();
      cfg.pin_cs          = TFT_CS;
      cfg.pin_rst         = TFT_RST;
      cfg.pin_busy        = -1;
      cfg.panel_width     = TFT_HEIGHT;
      cfg.panel_height    = TFT_WIDTH;
      cfg.offset_x        = 0;
      cfg.offset_y        = 0;
      cfg.offset_rotation = 1;
      cfg.readable        = false;
      cfg.invert          = true;
      cfg.rgb_order       = false;
      cfg.dlen_16bit      = false;
      cfg.bus_shared      = false;
      _panelInstance.config(cfg);
    }

    {
      auto cfg = _lightInstance.config();
      cfg.pin_bl      = TFT_BL;
      cfg.invert      = false;
      cfg.freq        = 12000;
      cfg.pwm_channel = 7;
      _lightInstance.config(cfg);
      _panelInstance.setLight(&_lightInstance);
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

// Connectivity & telemetry state
bool     wsConnected      = false;
uint32_t lastWifiCheckMs  = 0;
uint32_t lastTelemetryMs  = 0;
uint32_t frameCounter     = 0;
uint32_t fpsWindowStartMs = 0;
float    measuredFps      = 0.0f;

// ----------------------------------------------------------------------------
// Helper Functions
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
  Serial.println("[WS] Sent device_hello");
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
    currentBrightness = doc["brightness"]        | TFT_DEFAULT_BRIGHTNESS;
    display.setBrightness(currentBrightness);

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
    currentBrightness  = brightness;
    display.setBrightness(currentBrightness);
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
    Serial.println("[FRAME] Invalid header magic or version");
    return;
  }

  const uint8_t* pixelData = payload + sizeof(HrznFrameHeader);
  size_t pixelLen          = length - sizeof(HrznFrameHeader);

  if (hdr.format == FRAME_FMT_RGB565) {
    size_t expectedLen = static_cast<size_t>(hdr.w) * static_cast<size_t>(hdr.h) * 2;
    if (pixelLen < expectedLen) {
      Serial.printf("[FRAME] RGB565 underrun: got %u, expected %u\n",
                    static_cast<unsigned>(pixelLen), static_cast<unsigned>(expectedLen));
      return;
    }
    display.startWrite();
    display.pushImage(hdr.x, hdr.y, hdr.w, hdr.h,
                      reinterpret_cast<const uint16_t*>(pixelData));
    display.endWrite();
  }
  else if (hdr.format == FRAME_FMT_JPEG) {
    display.drawJpg(pixelData, pixelLen, hdr.x, hdr.y, hdr.w, hdr.h);
  }
  else {
    Serial.printf("[FRAME] Unsupported pixel format: 0x%02X\n", hdr.format);
    return;
  }

  frameCounter++;
  uint32_t now = millis();
  uint32_t dt  = now - fpsWindowStartMs;
  if (dt >= 2000) {
    measuredFps      = (static_cast<float>(frameCounter) * 1000.0f) / static_cast<float>(dt);
    frameCounter     = 0;
    fpsWindowStartMs = now;
  }
}

static void onWebSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_DISCONNECTED:
      if (wsConnected) {
        Serial.println("[WS] Disconnected from STANCE-HRZN-LINK");
      }
      wsConnected = false;
      break;

    case WStype_CONNECTED:
      wsConnected = true;
      Serial.printf("[WS] Connected to ws://%s:%u%s\n",
                    LINK_HOST, LINK_PORT, LINK_WS_PATH);
      sendDeviceHello();
      break;

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
      break;
  }
}

// ----------------------------------------------------------------------------
// Wi-Fi Supervision (Non-blocking)
// ----------------------------------------------------------------------------
static void ensureWifiConnected() {
  if (WiFi.status() == WL_CONNECTED) return;

  uint32_t now = millis();
  if (now - lastWifiCheckMs < WIFI_RECONNECT_INTERVAL_MS) return;
  lastWifiCheckMs = now;

  Serial.printf("[WIFI] Connecting to SSID '%s'...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
}

// ----------------------------------------------------------------------------
// Arduino Entry Points
// ----------------------------------------------------------------------------
void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  delay(200);
  Serial.println();
  Serial.println("===========================================");
  Serial.printf(" STANCE // HRZN-LINK Firmware (%s v%s)\n", HW_VERSION_STR, FW_VERSION_STR);
  Serial.println("===========================================");

  // Server sends big-endian RGB565 (>u2) ready for direct SPI TFT DMA write
  display.init();
  display.setSwapBytes(false);
  display.setBrightness(currentBrightness);
  display.fillScreen(TFT_BLACK);

  // Initialize servo state without holding torque continuously at idle
  ESP32PWM::allocateTimer(0);
  servoMotion.currentUs = servoClosedUs;

  // Connect Wi-Fi & configure non-blocking WebSocket client
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  lastWifiCheckMs  = millis();
  fpsWindowStartMs = millis();

  webSocket.begin(LINK_HOST, LINK_PORT, LINK_WS_PATH);
  webSocket.onEvent(onWebSocketEvent);
  webSocket.setReconnectInterval(WS_RECONNECT_INTERVAL_MS);
  webSocket.enableHeartbeat(15000, 3000, 2);
}

void loop() {
  ensureWifiConnected();

  if (WiFi.status() == WL_CONNECTED) {
    webSocket.loop();
  }

  updateServoMotion();

  uint32_t now = millis();
  if (wsConnected && (now - lastTelemetryMs >= TELEMETRY_INTERVAL_MS)) {
    lastTelemetryMs = now;
    sendTelemetryReport();
  }
}
