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
- **Display:** SPI TFT LCD (`320x240`, driven via `LovyanGFX`)
- **Actuator:** Micro servo (`SG90` or equivalent) driven via 50 Hz PWM (`writeMicroseconds`)
- **Power:** 5V USB input (external 5V rail recommended if servo brownouts occur)

## Default Placeholder GPIO Mapping (`HRZN-01`)

> [!IMPORTANT]
> Update [`../firmware/hrzn_firmware/config.h`](../firmware/hrzn_firmware/config.h) to match your exact ESP32-S3 board wiring before flashing.

| Signal | Placeholder GPIO | Notes |
| :--- | :--- | :--- |
| `TFT_MOSI` | `GPIO 11` | SPI MOSI (SDA) |
| `TFT_SCLK` | `GPIO 12` | SPI Clock (SCL) |
| `TFT_CS` | `GPIO 10` | TFT Chip Select |
| `TFT_DC` | `GPIO 9` | Data / Command |
| `TFT_RST` | `GPIO 14` | Hardware Reset |
| `TFT_BL` | `GPIO 13` | PWM Backlight Control |
| `SERVO_PIN` | `GPIO 4` | 50 Hz PWM Signal |

## Optical Combiner & Vertical Mirroring Notes

Because the flip-up HUD projects the TFT image onto an angled acrylic/glass combiner film toward the viewer, the image on the physical TFT panel must be **vertically mirrored** so text and graphics read normally in the reflection.

Per the `STANCE // HRZN-LINK` thin-client architecture, vertical mirroring is rendered centrally by `server/renderer/` before streaming binary frames to `HRZN-01`, while the companion web UI renders an un-mirrored live preview.
