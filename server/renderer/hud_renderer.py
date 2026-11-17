"""NumPy frame mirroring, RGB565/JPEG packetization, and Pillow grid fallback renderer."""

from __future__ import annotations

import base64
import io
import math
import struct
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from server.config_store import DeviceStatus, GridLayoutId, HrznConfig

if TYPE_CHECKING:
    from server.layout_engine import LayoutEvaluationResult

HUD_WIDTH = 480
HUD_HEIGHT = 320

FRAME_MAGIC = b"HZ"
FRAME_PROTOCOL_VERSION = 1
FMT_RGB565 = 0x01
FMT_JPEG = 0x02
FLAG_PARTIAL_REGION = 0x01
FLAG_PRE_MIRRORED = 0x02
# Links2004/WebSockets on ESP32 defaults to WEBSOCKETS_MAX_DATA_SIZE = 15 * 1024 (15,360 bytes).
MAX_WS_PAYLOAD_BYTES = 14000

BG_BLACK = (0, 0, 0)
CYAN_BRIGHT = (0, 240, 255)
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
            return ImageFont.truetype(path, size=max(8, size))
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=max(8, size))
    except TypeError:
        return ImageFont.load_default()


def _parse_hex_rgb(color: str, fallback: tuple[int, int, int] = CYAN_BRIGHT) -> tuple[int, int, int]:
    """Parse a `#RRGGBB` hex string into an `(R, G, B)` tuple."""
    raw = (color or "").strip().lstrip("#")
    if len(raw) == 6:
        try:
            return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))
        except ValueError:
            pass
    return fallback


def _scale_rgb(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return (
        max(0, min(255, int(rgb[0] * factor))),
        max(0, min(255, int(rgb[1] * factor))),
        max(0, min(255, int(rgb[2] * factor))),
    )


def _compute_slot_rects(
    layout_id: GridLayoutId,
    width: int,
    height: int,
    gap: int = 2,
) -> list[tuple[int, int, int, int]]:
    """Compute `(x0, y0, x1, y1)` pixel bounding boxes for each grid template."""
    w = max(60, width)
    h = max(60, height)

    if layout_id == "1x1":
        return [(0, 0, w, h)]
    if layout_id == "2x1":
        mid = w // 2
        return [(0, 0, mid - gap // 2, h), (mid + gap // 2, 0, w, h)]
    if layout_id == "1x2":
        mid = h // 2
        return [(0, 0, w, mid - gap // 2), (0, mid + gap // 2, w, h)]
    if layout_id == "2x2":
        mx, my = w // 2, h // 2
        return [
            (0, 0, mx - gap // 2, my - gap // 2),
            (mx + gap // 2, 0, w, my - gap // 2),
            (0, my + gap // 2, mx - gap // 2, h),
            (mx + gap // 2, my + gap // 2, w, h),
        ]
    if layout_id == "2-big-1-small":
        mx = w // 2
        top_h = int(h * 0.63)
        return [
            (0, 0, mx - gap // 2, top_h - gap // 2),
            (mx + gap // 2, 0, w, top_h - gap // 2),
            (0, top_h + gap // 2, w, h),
        ]
    if layout_id == "3x1":
        c1, c2 = w // 3, (2 * w) // 3
        return [
            (0, 0, c1 - gap // 2, h),
            (c1 + gap // 2, 0, c2 - gap // 2, h),
            (c2 + gap // 2, 0, w, h),
        ]
    if layout_id == "4x1":
        c1, c2, c3 = w // 4, w // 2, (3 * w) // 4
        return [
            (0, 0, c1 - gap // 2, h),
            (c1 + gap // 2, 0, c2 - gap // 2, h),
            (c2 + gap // 2, 0, c3 - gap // 2, h),
            (c3 + gap // 2, 0, w, h),
        ]
    return [(0, 0, w, h)]


class HudRenderer:
    """Renders fallback HUD frames and builds NumPy-mirrored differential packets."""

    def __init__(self, width: int = HUD_WIDTH, height: int = HUD_HEIGHT) -> None:
        self.width = width
        self.height = height
        self._font_cache: dict[int, ImageFont.ImageFont] = {}
        self._last_sent_frame: Optional[np.ndarray] = None

    def _font(self, size: int) -> ImageFont.ImageFont:
        clamped = max(8, int(size))
        if clamped not in self._font_cache:
            self._font_cache[clamped] = _load_font(clamped)
        return self._font_cache[clamped]

    def reset_diff_state(self) -> None:
        """Force the next frame to transmit all horizontal strips."""
        self._last_sent_frame = None

    def _draw_clock_slot(
        self,
        draw: ImageDraw.ImageDraw,
        rect: tuple[int, int, int, int],
        settings: dict[str, Any],
        data: dict[str, Any],
    ) -> None:
        x0, y0, x1, y1 = rect
        sw = max(1, x1 - x0)
        sh = max(1, y1 - y0)
        cx = x0 + sw // 2
        cy = y0 + sh // 2

        accent = _parse_hex_rgb(str(settings.get("accentColor", "#00f0ff")))
        accent_dim = _scale_rgb(accent, 0.32)
        accent_ghost = _scale_rgb(accent, 0.14)
        accent_tag = _scale_rgb(accent, 0.72)
        preset = str(settings.get("stylePreset", "tactical"))
        format24h = bool(settings.get("format24h", True))
        show_seconds = bool(settings.get("showSeconds", True))
        show_date = bool(settings.get("showDate", True))
        show_arc = bool(settings.get("showArcRing", True))

        now = datetime.now()
        hours = now.hour if format24h else (now.hour % 12 or 12)
        minutes = now.minute
        seconds = now.second
        ampm = "PM" if now.hour >= 12 else "AM"
        date_str = str(data.get("date_display") or now.strftime("%Y-%m-%d"))
        weekday = str(data.get("weekday") or now.strftime("%a").upper())
        sec_pct = float(data.get("minute_progress_pct", (seconds / 60.0) * 100.0))

        # Tactical corner brackets & header tags (matches Widget.vue)
        if preset == "tactical" and sw >= 155 and sh >= 135:
            m = 6
            tick = max(8, min(16, min(sw, sh) // 8))
            for bx, by, dx, dy in (
                (x0 + m, y0 + m, 1, 1),
                (x1 - m, y0 + m, -1, 1),
                (x0 + m, y1 - m, 1, -1),
                (x1 - m, y1 - m, -1, -1),
            ):
                draw.line([(bx, by), (bx + dx * tick, by)], fill=accent, width=2)
                draw.line([(bx, by), (bx, by + dy * tick)], fill=accent, width=2)
            tag_font = self._font(9)
            draw.text(
                (x0 + 14, y0 + 8),
                f"CHRONOS // {'24H' if format24h else '12H'}",
                font=tag_font,
                fill=accent_tag,
            )
            loc_box = draw.textbbox((0, 0), "LOC", font=tag_font)
            draw.text((x1 - 14 - (loc_box[2] - loc_box[0]), y0 + 8), "LOC", font=tag_font, fill=accent_tag)

        # Optional radial arc ring if container has space
        min_dim = min(sw, sh)
        if show_arc and preset != "minimal" and min_dim >= 136:
            radius = int(min_dim * 0.42)
            bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
            draw.arc(bbox, start=0, end=360, fill=accent_dim, width=2)
            end_angle = -90 + int(360 * max(0.0, min(100.0, sec_pct)) / 100.0)
            draw.arc(bbox, start=-90, end=end_angle, fill=accent, width=4)
            for idx in range(12):
                ang = math.radians(idx * 30 - 90)
                r_in = radius - 6
                r_out = radius + 1
                draw.line(
                    [
                        (cx + int(math.cos(ang) * r_in), cy + int(math.sin(ang) * r_in)),
                        (cx + int(math.cos(ang) * r_out), cy + int(math.sin(ang) * r_out)),
                    ],
                    fill=accent_dim,
                    width=1,
                )

        time_core = f"{hours:02d}:{minutes:02d}"
        font_size = max(18, min(int(sw * 0.20), int(sh * 0.30), 72))
        font_time = self._font(font_size)
        tb = draw.textbbox((0, 0), time_core, font=font_time)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]

        has_side_meta = show_seconds or (not format24h)
        sec_text = f":{seconds:02d}" if show_seconds else ""
        ampm_text = ampm if not format24h else ""
        sec_font = self._font(max(11, min(int(sw * 0.075), int(sh * 0.12), 26)))
        ampm_font = self._font(max(8, min(int(sw * 0.042), int(sh * 0.065), 13)))

        meta_w = 0
        gap_x = max(3, min(10, int(sw * 0.018)))
        if has_side_meta:
            sb = draw.textbbox((0, 0), sec_text, font=sec_font) if sec_text else (0, 0, 0, 0)
            ab = draw.textbbox((0, 0), ampm_text, font=ampm_font) if ampm_text else (0, 0, 0, 0)
            meta_w = gap_x + max(sb[2] - sb[0], ab[2] - ab[0])

        total_w = tw + meta_w
        core_left = cx - total_w // 2
        extra_rows_h = 0
        if preset in ("segmented", "minimal"):
            extra_rows_h += 12
        if show_date and sh >= 80:
            extra_rows_h += 22
        time_y = cy - (th + extra_rows_h) // 2

        if preset == "segmented":
            draw.text((core_left - tb[0], time_y - tb[1]), "88:88", font=font_time, fill=accent_ghost)
            text_color = accent
        else:
            text_color = SLATE_LIGHT

        draw.text((core_left - tb[0], time_y - tb[1]), time_core, font=font_time, fill=text_color)

        if has_side_meta:
            meta_x = core_left + tw + gap_x
            if ampm_text and sec_text:
                draw.text((meta_x, time_y), ampm_text, font=ampm_font, fill=accent)
                sec_h = draw.textbbox((0, 0), sec_text, font=sec_font)[3]
                draw.text((meta_x, max(time_y + 12, time_y + th - sec_h)), sec_text, font=sec_font, fill=accent)
            elif ampm_text:
                draw.text((meta_x, time_y + max(0, th // 3)), ampm_text, font=ampm_font, fill=accent)
            elif sec_text:
                sec_h = draw.textbbox((0, 0), sec_text, font=sec_font)[3]
                draw.text((meta_x, time_y + max(0, th - sec_h)), sec_text, font=sec_font, fill=accent)

        next_y = time_y + th + max(6, min(12, sh // 24))

        if preset == "segmented" and sh >= 90:
            bar_w = max(64, min(int(sw * 0.52), 190))
            bar_h = max(3, min(6, int(sh * 0.016)))
            cell_gap = max(2, min(4, int(sw * 0.008)))
            cell_w = max(3, (bar_w - 11 * cell_gap) // 12)
            total_bar_w = 12 * cell_w + 11 * cell_gap
            bx0 = cx - total_bar_w // 2
            active_cells = max(1, math.ceil((seconds / 60.0) * 12))
            for idx in range(12):
                cx0 = bx0 + idx * (cell_w + cell_gap)
                fill_c = accent if idx < active_cells else accent_ghost
                draw.rectangle([cx0, next_y, cx0 + cell_w, next_y + bar_h], fill=fill_c)
            next_y += bar_h + max(6, min(10, sh // 28))
        elif preset == "minimal" and sh >= 90:
            line_w = max(28, min(int(sw * 0.32), 110))
            draw.rectangle([cx - line_w // 2, next_y, cx + line_w // 2, next_y + 2], fill=accent)
            next_y += 8

        if show_date and sh >= 80:
            date_label = f"{weekday} {date_str}" if sw >= 145 else date_str[5:]
            date_font = self._font(max(9, min(15, int(min(sw * 0.046, sh * 0.075)))))
            db = draw.textbbox((0, 0), date_label, font=date_font)
            dw = db[2] - db[0]
            draw.text(
                (cx - dw // 2, next_y),
                date_label,
                font=date_font,
                fill=accent if preset != "minimal" else SLATE_MUTED,
            )

    def render_unmirrored(
        self,
        config: HrznConfig,
        device: DeviceStatus,
        layout_eval: Optional[LayoutEvaluationResult] = None,
    ) -> Image.Image:
        """Render the configured HUD grid in normal upright orientation (fallback renderer)."""
        _ = device
        width = config.display_width
        height = config.display_height
        self.width = width
        self.height = height

        img = Image.new("RGB", (width, height), BG_BLACK)
        draw = ImageDraw.Draw(img)

        if layout_eval is not None:
            layout_id = layout_eval.active_layout
            slots = layout_eval.slots
            plugin_settings = layout_eval.effective_plugin_settings
            plugin_data = layout_eval.plugin_data
        else:
            layout_id = config.manual_layout
            slots = config.grid_slots
            plugin_settings = config.plugin_configs
            plugin_data = {}

        rects = _compute_slot_rects(layout_id, width, height)
        for idx, rect in enumerate(rects):
            plugin_id = slots[idx] if idx < len(slots) else None
            if plugin_id == "clock":
                self._draw_clock_slot(
                    draw=draw,
                    rect=rect,
                    settings=plugin_settings.get("clock", {}),
                    data=plugin_data.get("clock", {}),
                )
            elif len(rects) > 1:
                x0, y0, x1, y1 = rect
                draw.rectangle([x0 + 2, y0 + 2, x1 - 2, y1 - 2], outline=(24, 34, 46), width=1)

        return img

    @staticmethod
    def rgb_array_to_rgb565_le(rgb_arr: np.ndarray) -> bytes:
        """Convert an `(H, W, 3)` uint8 RGB array into little-endian RGB565 (`<u2`) bytes."""
        rgb = rgb_arr.astype(np.uint16, copy=False)
        r = (rgb[:, :, 0] & 0xF8) << 8
        g = (rgb[:, :, 1] & 0xFC) << 3
        b = rgb[:, :, 2] >> 3
        rgb565 = (r | g | b).astype("<u2")
        return rgb565.tobytes()

    @classmethod
    def image_to_rgb565_be(cls, image: Image.Image) -> bytes:
        """Convert an RGB image into little-endian RGB565 (`<u2`) bytes for LovyanGFX setSwapBytes(true)."""
        rgb_arr = np.asarray(image.convert("RGB"), dtype=np.uint8)
        return cls.rgb_array_to_rgb565_le(rgb_arr)

    @staticmethod
    def image_to_jpeg(image: Image.Image, quality: int = 95, subsampling: int = 0) -> bytes:
        """Encode an RGB image as baseline JPEG bytes (default 4:4:4 chroma for sharp HUD text)."""
        buf = io.BytesIO()
        image.convert("RGB").save(
            buf,
            format="JPEG",
            quality=quality,
            subsampling=subsampling,
            optimize=False,
        )
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

    def build_frame_packets(
        self,
        unmirrored: Image.Image,
        seq: int,
        fmt: Literal["RGB565", "JPEG"] = "RGB565",
        mirror_vertical: bool = True,
        force_full: bool = False,
    ) -> list[bytes]:
        """Flip vertically in NumPy if enabled and emit <15 KB packets when pixels change."""
        arr = np.asarray(unmirrored.convert("RGB"), dtype=np.uint8)
        frame_arr = np.flipud(arr) if mirror_vertical else arr
        height, width, _ = frame_arr.shape
        base_flags = FLAG_PRE_MIRRORED if mirror_vertical else 0x00

        prev_arr = None if force_full else self._last_sent_frame
        if (
            prev_arr is not None
            and prev_arr.shape == frame_arr.shape
            and np.array_equal(frame_arr, prev_arr)
        ):
            return []

        if fmt == "JPEG":
            strip_h = 80 if width <= 480 else max(16, min(80, (480 * 80) // max(1, width)))
            packets: list[bytes] = []
            frame_img = Image.fromarray(frame_arr, mode="RGB")
            for y0 in range(0, height, strip_h):
                y1 = min(height, y0 + strip_h)
                strip = frame_img.crop((0, y0, width, y1))
                payload = self.image_to_jpeg(strip, quality=95, subsampling=0)
                if len(payload) > MAX_WS_PAYLOAD_BYTES:
                    payload = self.image_to_jpeg(strip, quality=85, subsampling=0)
                if len(payload) > MAX_WS_PAYLOAD_BYTES:
                    payload = self.image_to_jpeg(strip, quality=72, subsampling=0)
                header = struct.pack(
                    "<2sBBBBHHHH",
                    FRAME_MAGIC,
                    FRAME_PROTOCOL_VERSION,
                    FMT_JPEG,
                    base_flags | FLAG_PARTIAL_REGION,
                    seq & 0xFF,
                    0,
                    y0,
                    strip.width,
                    strip.height,
                )
                packets.append(header + payload)
            self._last_sent_frame = frame_arr.copy()
            return packets

        # Chunk RGB565 into 10px horizontal strips (9,614 bytes at 480px width) and skip unchanged strips.
        max_rows = max(1, (MAX_WS_PAYLOAD_BYTES - 14) // max(1, width * 2))
        strip_h = min(10, max_rows)
        full_redraw = prev_arr is None or prev_arr.shape != frame_arr.shape

        packets = []
        for y0 in range(0, height, strip_h):
            y1 = min(height, y0 + strip_h)
            curr_strip = frame_arr[y0:y1]
            if not full_redraw and np.array_equal(curr_strip, prev_arr[y0:y1]):
                continue
            payload = self.rgb_array_to_rgb565_le(curr_strip)
            header = struct.pack(
                "<2sBBBBHHHH",
                FRAME_MAGIC,
                FRAME_PROTOCOL_VERSION,
                FMT_RGB565,
                base_flags | FLAG_PARTIAL_REGION,
                seq & 0xFF,
                0,
                y0,
                width,
                y1 - y0,
            )
            packets.append(header + payload)

        self._last_sent_frame = frame_arr.copy()
        return packets

    def build_frame_packet(
        self,
        unmirrored: Image.Image,
        seq: int,
        fmt: Literal["RGB565", "JPEG"] = "RGB565",
        mirror_vertical: bool = True,
    ) -> bytes:
        """Apply vertical combiner mirroring in NumPy and pack a single 14-byte binary frame."""
        arr = np.asarray(unmirrored.convert("RGB"), dtype=np.uint8)
        frame_arr = np.flipud(arr) if mirror_vertical else arr
        height, width, _ = frame_arr.shape
        flags = FLAG_PRE_MIRRORED if mirror_vertical else 0x00

        if fmt == "JPEG":
            fmt_byte = FMT_JPEG
            payload = self.image_to_jpeg(Image.fromarray(frame_arr, mode="RGB"))
        else:
            fmt_byte = FMT_RGB565
            payload = self.rgb_array_to_rgb565_le(frame_arr)

        header = struct.pack(
            "<2sBBBBHHHH",
            FRAME_MAGIC,
            FRAME_PROTOCOL_VERSION,
            fmt_byte,
            flags,
            seq & 0xFF,
            0,
            0,
            width,
            height,
        )
        return header + payload
