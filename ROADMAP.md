# STANCE // HRZN-LINK — Future Roadmap

This document captures planned hardware upgrades and software integrations beyond the active **V1 (`HRZN-01`)** scope. Keeping these items here ensures the active V1 codebase remains clean, lightweight, and focused on bringing up `HRZN-01`.

---

## 1. Hardware Upgrades (`HRZN-02` — V2)

- **Self-Contained Wireless Enclosure (LilyGO T7-S3):**
  - Transition from an external USB-powered ESP32-S3 DevKit to a compact **LilyGO T7-S3** controller inside a unified 3D-printed housing.
  - **1S LiPo Battery & Power Monitoring:** Integrated JST battery support, USB-C charging, and ADC voltage divider sensing (`battery_mv` telemetry + low-battery sleep protection).
- **Metal-Gear Actuator (`MG90S`):**
  - Upgrade from plastic-gear SG90 micro servo to an **MG90S** metal-gear micro servo for higher durability and smoother combiner hinge torque.
- **Secondary Status Display (`TM1637`):**
  - 4-digit 7-segment LED module (`CLK` / `DIO`) for low-power always-on time/status readout even when the motorized HUD flap is closed.
- **Addressable Accent Lighting (`WS2812B`):**
  - Embedded **WS2812B** RGB LED strip for desk ambience, presence-state indication, and notification flashes controlled from `STANCE-HRZN-LINK`.
- **24 GHz 2D Multi-Target Tracking Radar (`HLK-LD2450`):**
  - UART-connected **HLK-LD2450** millimeter-wave radar capable of tracking up to **3 simultaneous targets** with $(X, Y)$ millimeter coordinates and target velocity.
  - Supports **virtual desk-zone filtering** (e.g., auto-deploy HUD only when seated within the primary workstation bounding box, ignoring passersby behind the desk).

---

## 2. Software & Smart Home Integrations

- **Home Assistant MQTT Auto-Discovery Bridge:**
  - Optional MQTT client inside `STANCE-HRZN-LINK` publishing Home Assistant Discovery payloads so the HUD appears automatically in Home Assistant with zero manual YAML:
    - `cover`: Motorized HUD flap (open / close / set position).
    - `light`: `WS2812B` accent LEDs (brightness, RGB color, effects) and TFT backlight control.
    - `binary_sensor` & `sensor`: `HLK-LD2450` per-zone occupancy, target count, $(X, Y)$ coordinates, speed, and `HRZN-02` battery voltage.
- **Live 2D Radar Zone Editor (Vue 3 Web UI):**
  - Interactive drag-and-drop canvas in the companion web dashboard displaying live `HLK-LD2450` target dots in real time alongside editable polygonal/rectangular desk detection zones.
- **Widget Plugin Ecosystem (Server Renderer):**
  - Modular Pillow/NumPy HUD widgets for weather, Pomodoro timers, media playback ("Now Playing"), system resource graphs, calendar alerts, and Home Assistant entity states.
