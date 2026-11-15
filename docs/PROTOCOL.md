# STANCE // HRZN-LINK Protocol Specification (`v1`)

The `STANCE // HRZN-LINK` protocol governs all communication between the Dockerized `stance-hrzn-link` host server, the `HRZN-01` ESP32-S3 HUD client, and the companion Vue 3 web dashboard on port `8080`.

- **Device WebSocket:** `ws://<LINK_HOST>:8080/ws/device` (UTF-8 JSON control + Binary frame packets)
- **Dashboard WebSocket:** `ws://<LINK_HOST>:8080/ws/ui` (Live config, device telemetry, and un-mirrored PNG preview stream)
- **HTTP REST API:** `/api/health`, `/api/state`, `/api/config`, `/api/flap`, `/api/brightness`, `/api/preview.png`

---

## 1. Device Connection & Handshake (`/ws/device`)

```text
HRZN-01 (ESP32-S3)                       STANCE-HRZN-LINK (FastAPI)
       |                                             |
       |--- WS Connect (/ws/device) ---------------->|
       |                                             |
       |--- JSON: device_hello --------------------->|  (HRZN-01, 320x240, capabilities)
       |<-- JSON: config_sync -----------------------|  (Saved servo limits, brightness, flap state)
       |                                             |
       |<== BIN: Frame Packet (RGB565 / JPEG) =======|  (Pre-mirrored HUD frames)
       |<-- JSON: flap_move / set_brightness --------|  (Runtime hardware control)
       |--- JSON: telemetry_report ----------------->|  (Periodic health & state)
```

### 1.1 `device_hello` (Client -> Server)

Sent immediately upon WebSocket connection establishment. Identifies `HRZN-01`, display dimensions, and supported pixel formats.

```json
{
  "type": "device_hello",
  "protocol_version": 1,
  "device_id": "hrzn-a1b2c3d4e5f6",
  "hw_version": "HRZN-01",
  "fw_version": "0.1.0-alpha",
  "display": {
    "width": 320,
    "height": 240,
    "formats": ["RGB565", "JPEG"],
    "needs_vertical_mirror": true
  },
  "capabilities": {
    "servo": true,
    "backlight_pwm": true
  }
}
```

### 1.2 `config_sync` (Server -> Client)

Sent by the server immediately in response to `device_hello` (or whenever configuration changes are synced). Firmware applies these values immediately without storing permanent overrides locally.

```json
{
  "type": "config_sync",
  "servo_closed_us": 1000,
  "servo_open_us": 2000,
  "sweep_duration_ms": 800,
  "settle_detach_ms": 250,
  "brightness": 200,
  "flap_state": "open",
  "target_angle_pct": 100
}
```

| Field | Type | Range / Values | Description |
| :--- | :--- | :--- | :--- |
| `servo_closed_us` | `uint16` | `500..2500` | PWM pulse width (µs) when HUD flap is closed |
| `servo_open_us` | `uint16` | `500..2500` | PWM pulse width (µs) when HUD flap is open |
| `sweep_duration_ms` | `uint16` | `100..5000` | Default cosine-eased sweep duration (ms) |
| `settle_detach_ms` | `uint16` | `50..2000` | Delay after reaching target before detaching servo PWM |
| `brightness` | `uint8` | `0..255` | TFT backlight PWM duty cycle |
| `flap_state` | `string` | `"open" \| "closed" \| "custom"` | Initial target flap state on connect |
| `target_angle_pct` | `uint8` | `0..100` | Target flap deployment percentage (`0` = closed, `100` = open) |

---

## 2. Device JSON Control Messages

### 2.1 `flap_move` (Server -> Client)

Commands the servo to sweep smoothly (cosine-eased) to open, closed, or an intermediate calibration percentage.

```json
{
  "type": "flap_move",
  "state": "open",
  "position_pct": 100,
  "duration_ms": 800
}
```

- `"open"` -> `100%` (`servo_open_us`)
- `"closed"` -> `0%` (`servo_closed_us`)
- `"custom"` -> linear interpolation between `servo_closed_us` and `servo_open_us` using `position_pct` (`0..100`)
- `duration_ms` is optional; when omitted or `0`, firmware uses `sweep_duration_ms`.

### 2.2 `set_servo_limits` (Server -> Client)

Updates calibrated servo endpoint pulse widths and timing parameters in RAM (persisted server-side in `STANCE-HRZN-LINK`).

```json
{
  "type": "set_servo_limits",
  "closed_us": 980,
  "open_us": 2040,
  "sweep_duration_ms": 750,
  "settle_detach_ms": 250
}
```

- Firmware clamps `closed_us` and `open_us` to safe mechanical bounds (`500..2500` µs).
- `closed_us` may be greater than `open_us` depending on servo horn orientation; interpolation supports inverted ranges.

### 2.3 `set_brightness` (Server -> Client)

Adjusts the SPI TFT PWM backlight brightness immediately.

```json
{
  "type": "set_brightness",
  "brightness": 180
}
```

| Field | Type | Range | Description |
| :--- | :--- | :--- | :--- |
| `brightness` | `uint8` | `0..255` | `0` turns backlight off; `255` is maximum brightness |

### 2.4 `telemetry_report` (Client -> Server)

Sent periodically by `HRZN-01` (default every `5000 ms`).

```json
{
  "type": "telemetry_report",
  "uptime_s": 1420,
  "rssi_dbm": -54,
  "free_heap": 214560,
  "flap_position_pct": 100,
  "servo_us": 2000,
  "servo_attached": false,
  "brightness": 180,
  "fps": 2.0
}
```

---

## 3. Binary Frame Packet Specification

Display updates are transmitted as raw **WebSocket Binary Frames** on `/ws/device`.

### 3.1 Packet Layout

Each binary WebSocket message consists of a **14-byte little-endian packed header** immediately followed by the pixel payload:

```text
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   Magic[0]    |   Magic[1]    |    Version    |    Format     |
|    (0x48)     |    (0x5A)     |    (0x01)     | (0x01 / 0x02) |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|     Flags     |  Sequence ID  |          Region X (LE)        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          Region Y (LE)        |        Region Width (LE)      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|       Region Height (LE)      |        Payload Bytes ...      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

### 3.2 Header Field Reference (`HrznFrameHeader`, 14 bytes)

| Offset | Size | Field | Type | Description |
| :--- | :--- | :--- | :--- | :--- |
| `0` | 2 | `magic` | `uint8[2]` | Fixed magic bytes `0x48, 0x5A` (`"HZ"`) |
| `2` | 1 | `version` | `uint8` | Packet header version (`0x01`) |
| `3` | 1 | `format` | `uint8` | `0x01` = Big-Endian `RGB565`, `0x02` = `JPEG` |
| `4` | 1 | `flags` | `uint8` | Bitmask (`0x01` = partial region, `0x02` = pre-mirrored vertically) |
| `5` | 1 | `seq` | `uint8` | Rolling sequence number (`0..255`) |
| `6` | 2 | `x` | `uint16` LE | Destination X coordinate (`0` for full frame) |
| `8` | 2 | `y` | `uint16` LE | Destination Y coordinate (`0` for full frame) |
| `10` | 2 | `w` | `uint16` LE | Region width in pixels (`320` for full frame) |
| `12` | 2 | `h` | `uint16` LE | Region height in pixels (`240` for full frame) |
| `14` | `N` | `payload` | `uint8[]` | Encoded pixel data |

### 3.3 Payload Formats

1. **Big-Endian RGB565 (`format = 0x01`)**
   - Payload length MUST equal `w * h * 2` bytes (`153,600` bytes for `320x240`).
   - Encoded as big-endian `RGB565` (`>u2`) in SPI wire byte order, matching `LovyanGFX` `setSwapBytes(false)` + `pushImage`.
2. **JPEG (`format = 0x02`)**
   - Standard baseline JPEG matching `(w, h)` dimensions, decoded via `LovyanGFX` `drawJpg`.

---

## 4. Dashboard WebSocket (`/ws/ui`) & REST API

- **`GET /api/health`** — Returns `{ "status": "ok", "hw_target": "HRZN-01", "device_connected": bool }`.
- **`GET /api/state`** — Returns persisted `config` + live `device` status.
- **`POST /api/config`** — Updates & persists `HrznConfig`; pushes `set_servo_limits`, `set_brightness`, and/or `flap_move` to `HRZN-01` if connected.
- **`POST /api/flap`** — Quick flap actuation (`state`: `"open" | "closed" | "custom"`, optional `position_pct`, optional `duration_ms`).
- **`POST /api/brightness`** — Quick backlight update (`brightness`: `0..255`).
- **`GET /api/preview.png`** — Returns the current **un-mirrored** `320x240` HUD frame as `image/png`.
- **`WS /ws/ui`** — Streams JSON `{ "type": "state_update", "config": ..., "device": ..., "preview_data_url": "data:image/png;base64,..." }` whenever frames or state update, and accepts `{ "type": "flap_move" | "set_brightness" | "update_config", ... }` commands from the UI.
