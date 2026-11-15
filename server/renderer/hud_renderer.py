"""Pillow + NumPy server-side HUD renderer and binary frame packetizer."""

from __future__ import annotations

import base64
import io
import struct
from datetime import datetime
from typing import Literal

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from server.config_store import DeviceStatus, HrznConfig

HUD_WIDTH = 320
HUD_HEIGHT = 240

FRAME_MAGIC = b"HZ"
FRAME_PROTOCOL_VERSION = 1
FMT_RGB565 = 0x01
FMT_JPEG = 0x02
FLAG_PRE_MIRRORED = 0x02

# High-contrast optical combiner palette on pure black (#000000 = transparent reflection)
BG_BLACK = (0, 0, 0)
CYAN_BRIGHT = (0, 240, 255)
CYAN_DIM = (12, 92, 110)
EMERALD = (16, 225, 140)
AMBER = (245, 166, 35)
SLATE_LIGHT = (215, 228, 240)
SLATE_MUTED = (100, 118, 138)


def _load_font(size: int) -> ImageFont.ImageFont:
    """Load a crisp monospace font if available, falling back to Pillow default."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "C:/Windows/Fonts/consolab.ttf",
        "C:/Windows/Fonts/consola.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


class HudRenderer:
    """Renders 320x240 tactical HUD frames and packs them for HRZN-01."""

    def __init__(self, width: int = HUD_WIDTH, height: int = HUD_HEIGHT) -> None:
        self.width = width
        self.height = height
        self._font_xl = _load_font(40)
        self._font_md = _load_font(15)
        self._font_sm = _load_font(12)
        self._font_xs = _load_font(10)

    def render_unmirrored(self, config: HrznConfig, device: DeviceStatus) -> Image.Image:
        """Render the 320x240 HUD in normal upright orientation for preview and pre-mirroring."""
        img = Image.new("RGB", (self.width, self.height), BG_BLACK)
        draw = ImageDraw.Draw(img)

        # Outer HUD corner reticle brackets
        m = 8
        tick = 18
        for x0, y0, dx, dy in (
            (m, m, 1, 1),
            (self.width - 1 - m, m, -1, 1),
            (m, self.height - 1 - m, 1, -1),
            (self.width - 1 - m, self.height - 1 - m, -1, -1),
        ):
            draw.line([(x0, y0), (x0 + dx * tick, y0)], fill=CYAN_BRIGHT, width=2)
            draw.line([(x0, y0), (x0, y0 + dy * tick)], fill=CYAN_BRIGHT, width=2)

        # Header banner
        draw.text((18, 14), config.hud_title[:24], font=self._font_sm, fill=CYAN_BRIGHT)
        link_label = "ONLINE" if device.connected else "STANDBY"
        link_color = EMERALD if device.connected else AMBER
        draw.text((self.width - 66, 14), link_label, font=self._font_sm, fill=link_color)
        draw.line([(16, 34), (self.width - 16, 34)], fill=CYAN_DIM, width=1)

        # Subtitle + center digital clock
        now = datetime.now()
        time_str = now.strftime("%H:%M:%S")
        date_str = now.strftime("%a %Y-%m-%d").upper()

        draw.text((18, 42), config.hud_subtitle[:32], font=self._font_xs, fill=SLATE_MUTED)

        bbox = draw.textbbox((0, 0), time_str, font=self._font_xl)
        tw = bbox[2] - bbox[0]
        draw.text(((self.width - tw) // 2, 66), time_str, font=self._font_xl, fill=SLATE_LIGHT)

        dbbox = draw.textbbox((0, 0), date_str, font=self._font_sm)
        dw = dbbox[2] - dbbox[0]
        draw.text(((self.width - dw) // 2, 118), date_str, font=self._font_sm, fill=CYAN_BRIGHT)

        # Optical horizon bar + flap deployment progress
        bar_x0, bar_y0 = 28, 148
        bar_w, bar_h = self.width - 56, 8
        draw.rectangle([bar_x0, bar_y0, bar_x0 + bar_w, bar_y0 + bar_h], outline=CYAN_DIM, width=1)

        active_pct = device.flap_position_pct if device.connected else config.target_angle_pct
        fill_w = int((bar_w - 4) * max(0, min(100, active_pct)) / 100)
        if fill_w > 0:
            draw.rectangle(
                [bar_x0 + 2, bar_y0 + 2, bar_x0 + 2 + fill_w, bar_y0 + bar_h - 2],
                fill=CYAN_BRIGHT,
            )

        # Subtle center crosshair tick
        cx = self.width // 2
        draw.line([(cx, bar_y0 - 4), (cx, bar_y0 + bar_h + 4)], fill=EMERALD, width=1)

        # Telemetry footer strip
        draw.line([(16, 174), (self.width - 16, 174)], fill=CYAN_DIM, width=1)

        servo_us = device.servo_us if device.connected else (
            config.servo_open_us if config.flap_state == "open" else config.servo_closed_us
        )
        rssi_text = f"{device.rssi_dbm} dBm" if device.rssi_dbm is not None else "-- dBm"
        fps_text = f"{device.fps:.1f}" if device.connected else f"{config.target_fps:.1f}*"

        draw.text((20, 182), f"FLAP {active_pct:3d}%", font=self._font_sm, fill=SLATE_LIGHT)
        draw.text((118, 182), f"PWM {servo_us:4d}us", font=self._font_sm, fill=CYAN_BRIGHT)
        draw.text((226, 182), f"BRT {config.brightness:3d}", font=self._font_sm, fill=SLATE_LIGHT)

        draw.text((20, 204), f"RSSI {rssi_text}", font=self._font_xs, fill=SLATE_MUTED)
        draw.text((138, 204), f"FMT {config.frame_format}", font=self._font_xs, fill=SLATE_MUTED)
        draw.text((236, 204), f"FPS {fps_text}", font=self._font_xs, fill=EMERALD)

        return img

    @staticmethod
    def image_to_rgb565_be(image: Image.Image) -> bytes:
        """Convert an RGB image into big-endian RGB565 (>u2) bytes using NumPy."""
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint16)
        r = (rgb[:, :, 0] & 0xF8) << 8
        g = (rgb[:, :, 1] & 0xFC) << 3
        b = rgb[:, :, 2] >> 3
        rgb565 = (r | g | b).astype(">u2")
        return rgb565.tobytes()

    @staticmethod
    def image_to_jpeg(image: Image.Image, quality: int = 85) -> bytes:
        """Encode an RGB image as baseline JPEG bytes."""
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=False)
        return buf.getvalue()

    @staticmethod
    def encode_png_bytes(image: Image.Image) -> bytes:
        """Encode an image as PNG bytes for HTTP preview serving."""
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()

    @classmethod
    def encode_png_data_url(cls, image: Image.Image) -> str:
        """Encode an image as a base64 PNG data URL for WebSocket UI streaming."""
        raw = cls.encode_png_bytes(image)
        b64 = base64.b64encode(raw).decode("ascii")
        return f"data:image/png;base64,{b64}"

    def build_frame_packet(
        self,
        unmirrored: Image.Image,
        seq: int,
        fmt: Literal["RGB565", "JPEG"] = "RGB565",
        mirror_vertical: bool = True,
    ) -> bytes:
        """Apply vertical combiner mirroring (if enabled) and pack the 14-byte binary frame."""
        frame = (
            unmirrored.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            if mirror_vertical
            else unmirrored
        )
        flags = FLAG_PRE_MIRRORED if mirror_vertical else 0x00

        if fmt == "JPEG":
            fmt_byte = FMT_JPEG
            payload = self.image_to_jpeg(frame)
        else:
            fmt_byte = FMT_RGB565
            payload = self.image_to_rgb565_be(frame)

        header = struct.pack(
            "<2sBBBBHHHH",
            FRAME_MAGIC,
            FRAME_PROTOCOL_VERSION,
            fmt_byte,
            flags,
            seq & 0xFF,
            0,
            0,
            frame.width,
            frame.height,
        )
        return header + payload
