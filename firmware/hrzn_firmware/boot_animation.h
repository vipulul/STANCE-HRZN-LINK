#pragma once

// ============================================================================
// STANCE // HRZN-LINK — Modular Boot Animation
// ============================================================================
// Edit the constants or `playBootAnimation()` below to customize the startup
// animation without touching the core WebSocket/display firmware.
// ============================================================================

#include <LovyanGFX.hpp>

// Customizable Boot Animation Configuration
static constexpr const char* BOOT_BRAND_TITLE  = "S T A N C E";
static constexpr const char* BOOT_MODEL_TITLE  = "H R Z N";
static constexpr const char* BOOT_STATUS_LABEL = "INITIALIZING OPTICAL LINK...";

static constexpr uint16_t BOOT_COLOR_BRAND  = TFT_MAGENTA;
static constexpr uint16_t BOOT_COLOR_MODEL  = TFT_CYAN;
static constexpr uint16_t BOOT_COLOR_BAR    = TFT_CYAN;
static constexpr uint16_t BOOT_COLOR_FRAME  = TFT_YELLOW;

static constexpr int      BOOT_BAR_WIDTH    = 360;
static constexpr int      BOOT_BAR_HEIGHT   = 16;
static constexpr uint16_t BOOT_FADE_STEP_MS = 6;

template <typename DisplayT>
static void drawBootBrandOverlay(DisplayT& tft, int cx) {
  tft.setTextDatum(textdatum_t::middle_center);
  tft.setTextSize(3);
  tft.setTextColor(BOOT_COLOR_BRAND);
  tft.drawString(BOOT_BRAND_TITLE, cx, 100);

  tft.setTextSize(6);
  tft.setTextColor(BOOT_COLOR_MODEL);
  tft.drawString(BOOT_MODEL_TITLE, cx, 170);
}

template <typename DisplayT>
static void playBootAnimation(DisplayT& tft,
                              void (*setBacklightFn)(uint8_t),
                              uint8_t finalBrightness) {
  const int w  = tft.width();
  const int h  = tft.height();
  const int cx = w / 2;

  setBacklightFn(0);
  tft.fillScreen(TFT_BLACK);
  drawBootBrandOverlay(tft, cx);

  // 1. Hardware backlight fade-in with subtle scanline glitches
  for (int b = 0; b <= 255; b += 2) {
    setBacklightFn(static_cast<uint8_t>(b));

    if (random(100) > 94) {
      int gy = random(0, h);
      tft.drawFastHLine(0, gy, random(50, w), TFT_WHITE);
      delay(5);
      tft.drawFastHLine(0, gy, w, TFT_BLACK);
      drawBootBrandOverlay(tft, cx);
    }
    delay(BOOT_FADE_STEP_MS);
  }

  setBacklightFn(255);
  delay(350);

  // 2. Progress bar animation
  const int barWidth = (w - 40 < BOOT_BAR_WIDTH) ? (w - 40) : BOOT_BAR_WIDTH;
  const int startX   = (w - barWidth) / 2;
  const int startY   = h - 62;

  tft.drawRect(startX - 2, startY - 2, barWidth + 4, BOOT_BAR_HEIGHT + 4, BOOT_COLOR_FRAME);

  tft.setTextSize(1);
  tft.setTextColor(TFT_WHITE);
  tft.setTextDatum(textdatum_t::bottom_left);
  tft.drawString(BOOT_STATUS_LABEL, startX, startY - 6);

  for (int i = 0; i <= barWidth; i += random(4, 14)) {
    if (i > barWidth) i = barWidth;
    tft.fillRect(startX, startY, i, BOOT_BAR_HEIGHT, BOOT_COLOR_BAR);

    if (random(100) > 90) {
      int gy = random(60, startY - 24);
      tft.drawFastHLine(0, gy, w, TFT_WHITE);
      delay(15);
      tft.drawFastHLine(0, gy, w, TFT_BLACK);
      drawBootBrandOverlay(tft, cx);
    }
    delay(random(10, 30));
  }
  tft.fillRect(startX, startY, barWidth, BOOT_BAR_HEIGHT, BOOT_COLOR_BAR);
  delay(300);

  // Brief flash transition before entering diagnostic standby screen
  tft.fillScreen(TFT_WHITE);
  delay(45);
  tft.fillScreen(TFT_BLACK);
  tft.setTextDatum(textdatum_t::top_left);
  setBacklightFn(finalBrightness);
}
