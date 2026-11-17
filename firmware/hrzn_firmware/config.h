#pragma once

// ============================================================================
// STANCE // HRZN-LINK — HRZN-01 Hardware Configuration & Fallback Defaults
// ============================================================================
// Target Hardware: HRZN-01 (ESP32-S3 DevKit + SPI TFT + Micro Servo, USB power)
// All runtime behavior (servo endpoints, sweep speed, brightness, layouts)
// is synchronized from the Dockerized STANCE-HRZN-LINK server on connect.
// ============================================================================

// Firmware & Device Identification
#define HW_VERSION_STR   "HRZN-01"
#define FW_VERSION_STR   "0.1.0-alpha"
#define PROTOCOL_VERSION 1

// ----------------------------------------------------------------------------
// Display Geometry (IPS ILI9488 480x320 Landscape)
// ----------------------------------------------------------------------------
#define TFT_WIDTH   480
#define TFT_HEIGHT  320

// ----------------------------------------------------------------------------
// Placeholder GPIO Pinouts (HRZN-01 — ESP32-S3 DevKit)
// Replace these placeholder pin numbers with your actual ESP32-S3 wiring.
// ----------------------------------------------------------------------------
#define TFT_MOSI   11
#define TFT_SCLK   12
#define TFT_CS     10
#define TFT_DC     9
#define TFT_RST    8
#define TFT_BL     13

#define SERVO_PIN  4

// ----------------------------------------------------------------------------
// Safe Fallback Defaults (Overridden by server `config_sync` on WebSocket connect)
// ----------------------------------------------------------------------------
#define SERVO_MIN_SAFE_US       500
#define SERVO_MAX_SAFE_US       2500
#define SERVO_CLOSED_US         1000
#define SERVO_OPEN_US           2000
#define SERVO_DEFAULT_SWEEP_MS  800
#define SERVO_SETTLE_DETACH_MS  250

#define TFT_DEFAULT_BRIGHTNESS  255   // 0..255 PWM duty cycle (255 = steady 100% on boot)

// ----------------------------------------------------------------------------
// Non-blocking Timing Intervals
// ----------------------------------------------------------------------------
#define WIFI_RECONNECT_INTERVAL_MS  15000
#define WS_RECONNECT_INTERVAL_MS    3000
#define TELEMETRY_INTERVAL_MS       5000
#define SERIAL_DIAG_INTERVAL_MS     2000
#define SERIAL_BAUD_RATE            115200
