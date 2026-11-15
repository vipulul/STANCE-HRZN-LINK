# STANCE // HRZN-LINK

**STANCE Labs** motorized flip-up Heads-Up Display (HUD) platform for **`HRZN-01`**.

`STANCE // HRZN-LINK` follows a **Thin Client / Smart Host** architecture: the ESP32-S3 (`HRZN-01`) stays lean and stateless—acting solely as a WebSocket display and servo actuator client—while all layout rendering, vertical optical-combiner mirroring, persistent calibration, and the companion web UI run inside a single-port (`8080`) FastAPI + Vue 3 server.

Future hardware and smart-home plans are tracked separately in [`ROADMAP.md`](ROADMAP.md).

---

## Architecture Overview

```text
+-----------------------+       HTTP / WS (:8080)       +-----------------------------------+
|                       | <---------------------------> |  Docker Server (STANCE-HRZN-LINK) |
|  Companion Web UI     |   Calibration, Flap Control,  |  - Python 3.12 + FastAPI          |
|  Vue 3 + Tailwind CSS |   Un-mirrored Live Preview    |  - Pillow + NumPy HUD Renderer    |
+-----------------------+                               |  - Persistent JSON Config Store   |
                                                        |  - Static Vue Dist Serving        |
                                                        +-----------------------------------+
                                                                          ^
                                                                          | WS (/ws/device)
                                                           (JSON Control  |  + Binary RGB565/JPEG)
                                                                          v
                                                        +-----------------------------------+
                                                        |  ESP32-S3 Thin Client (HRZN-01)   |
                                                        |  - SPI TFT Frame Blit (LovyanGFX) |
                                                        |  - Cosine-eased Servo Sweep       |
                                                        |  - Backlight PWM & Telemetry      |
                                                        +-----------------------------------+
```

### Core Design Principles
- **Thin Client / Smart Host:** `HRZN-01` stores no layouts or local menus. It receives pre-rendered, vertically mirrored frames and JSON control commands over `/ws/device`.
- **Single-Port Serving (`8080`):** FastAPI serves the built Vue 3 frontend (`web/dist/`), REST API (`/api/*`), device WebSocket (`/ws/device`), and dashboard WebSocket (`/ws/ui`) on port `8080`.
- **Standard Arduino Tooling:** Firmware uses standard `.ino` sketches compatible with both **Arduino IDE 2.x** and **`arduino-cli`** (no PlatformIO).

---

## Tech Stack (V1 — `HRZN-01`)

- **Firmware (`firmware/hrzn_firmware/`):** ESP32-S3 Arduino (`LovyanGFX`, `ArduinoJson`, `WebSockets`, `ESP32Servo`)
- **Backend (`server/`):** Python 3.12, FastAPI, Uvicorn, Pillow, NumPy, Pydantic
- **Frontend (`web/`):** Vue 3, Vite, TypeScript, Tailwind CSS

---

## Repository Structure

```text
stance-hrzn-link/
├── firmware/
│   └── hrzn_firmware/          # Standard Arduino sketch + arduino-cli profile
│       ├── hrzn_firmware.ino
│       ├── config.h
│       ├── secrets.example.h
│       └── sketch.yaml
├── server/                     # FastAPI backend, Pillow/NumPy HUD renderer & config store
│   ├── renderer/
│   │   └── hud_renderer.py
│   ├── config_store.py
│   ├── main.py
│   └── requirements.txt
├── web/                        # Vue 3 + Vite + TypeScript + Tailwind companion UI
├── hardware/                   # CAD STLs, wiring diagrams, and BOM (HRZN-01)
├── docs/
│   └── PROTOCOL.md             # WebSocket JSON & binary frame packet spec
├── Dockerfile                  # Multi-stage build (Vue dist -> Python 3.12 FastAPI)
├── docker-compose.yml          # Single-port 8080 service definition
├── ROADMAP.md                  # Future HRZN-02 hardware & Home Assistant integrations
└── README.md
```

---

## Quickstart

### 1. Run with Docker (Recommended — Single Port `8080`)

```bash
docker compose up -d --build
```

Open **`http://localhost:8080`** in your browser for the companion control panel and live HUD preview.

### 2. Local Development (Hot-Reload)

**Terminal 1 — FastAPI Backend (`:8080`):**
```bash
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# Linux/macOS:        source .venv/bin/activate
pip install -r server/requirements.txt
uvicorn server.main:app --reload --host 0.0.0.0 --port 8080
```

**Terminal 2 — Vue 3 + Vite Frontend (`:5173` proxying `/api` & `/ws` -> `:8080`):**
```bash
cd web
npm install
npm run dev
```

### 3. Flash `HRZN-01` Firmware

1. Copy the secrets template and enter your Wi-Fi credentials and host IP:
   ```bash
   cp firmware/hrzn_firmware/secrets.example.h firmware/hrzn_firmware/secrets.h
   ```
   *(Windows PowerShell: `Copy-Item firmware\hrzn_firmware\secrets.example.h firmware\hrzn_firmware\secrets.h`)*

2. Verify the placeholder GPIO pins in [`firmware/hrzn_firmware/config.h`](firmware/hrzn_firmware/config.h) match your ESP32-S3 wiring.

3. **Option A — `arduino-cli`:**
   ```bash
   arduino-cli core update-index
   arduino-cli compile --profile hrzn_s3 firmware/hrzn_firmware
   arduino-cli upload --profile hrzn_s3 -p COMx firmware/hrzn_firmware
   ```

4. **Option B — Arduino IDE 2.x:**
   - Open [`firmware/hrzn_firmware/hrzn_firmware.ino`](firmware/hrzn_firmware/hrzn_firmware.ino).
   - Select **ESP32S3 Dev Module** (`esp32:esp32:esp32s3`).
   - Install `LovyanGFX`, `ArduinoJson`, `WebSockets` (Markus Sattler), and `ESP32Servo` via Library Manager, then click **Upload**.

See [`docs/PROTOCOL.md`](docs/PROTOCOL.md) for the complete WebSocket and binary packet specification.
