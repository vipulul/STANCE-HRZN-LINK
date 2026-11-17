# STANCE // HRZN Hardware Reference (`HRZN-01`)

This directory stores mechanical CAD files (STLs / STEPs), wiring diagrams, and Bills of Materials (BOM) for the active **HRZN-01 (V1)** motorized flip-up HUD hardware.

For future hardware upgrades, see [`../ROADMAP.md`](../ROADMAP.md).

## Directory Layout

```text
hardware/
├── cad/        # 3D-printable enclosures, hinge brackets, combiner mounts (.stl / .step)
├── wiring/     # Wiring schematics and pinout diagrams
├── bom/        # Component lists and sourcing notes
└── README.md
```

## `HRZN-01` (V1 — Benchtop / External DevKit)

- **MCU:** External ESP32-S3 DevKit (USB-C powered & programmed)
- **Display:** IPS `ILI9488` (`480x320` landscape / `320x480` native, powered at **`3.3V` (`3V3`) on `VDD`**, driven via `LovyanGFX` at 60 MHz SPI)
- **Actuator:** Micro servo (`SG90` or equivalent) driven via 50 Hz PWM (`writeMicroseconds`)
- **Power:** 5V USB input for ESP32-S3 & servo (external 5V rail recommended if servo brownouts occur); **`ILI9488` `VDD/VCC` must be connected to `3.3V` (`3V3`)**

## Verified GPIO Mapping (`HRZN-01`)

> [!IMPORTANT]
> Update [`../firmware/hrzn_firmware/config.h`](../firmware/hrzn_firmware/config.h) to match your exact ESP32-S3 board wiring before flashing.

| Signal | GPIO / Rail | Notes |
| :--- | :--- | :--- |
| `TFT_VDD` | `3V3` | **`3.3V` supply required** (do not feed `5V` to `ILI9488` VDD) |
| `TFT_MOSI` | `GPIO 11` | SPI MOSI (`SDI/SDA`) |
| `TFT_SCLK` | `GPIO 12` | SPI Clock (`SCK/SCL`) |
| `TFT_MISO` | `-1` (NC) | `SDO/MISO` left unconnected |
| `TFT_CS` | `GPIO 10` | TFT Chip Select |
| `TFT_DC` | `GPIO 9` | Data / Command |
| `TFT_RST` | `GPIO 8` | Hardware Reset |
| `TFT_BL` | `GPIO 13` | PWM Backlight Control |
| `SERVO_PIN` | `GPIO 4` | 50 Hz PWM Signal |

## Optical Combiner & Vertical Mirroring Notes

Because the flip-up HUD projects the TFT image onto an angled acrylic/glass combiner film toward the viewer, the image on the physical TFT panel must be **vertically mirrored** so text and graphics read normally in the reflection.

Per the `STANCE // HRZN-LINK` thin-client architecture, vertical mirroring is rendered centrally by `server/renderer/` before streaming binary frames to `HRZN-01`, while the companion web UI renders an un-mirrored live preview.
