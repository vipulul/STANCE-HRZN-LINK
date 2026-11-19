"""Backend Telemetry / Debug plugin provider auto-discovered from `plugins/telemetry/`."""

from __future__ import annotations

import inspect
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Optional

from server.plugins.base import HudPluginProvider, PluginRuntimeStatus

if TYPE_CHECKING:
    from server.config_store import DeviceStatus, HrznConfig


def _default_config() -> Any:
    return SimpleNamespace(
        servo_closed_us=1000,
        servo_open_us=2000,
        sweep_duration_ms=800,
        settle_detach_ms=250,
        flap_state="open",
        target_angle_pct=100,
        frame_format="RGB565",
        target_fps=2.5,
        display_width=480,
        display_height=320,
        layout_mode="manual",
        manual_layout="1x1",
    )


def _default_device() -> Any:
    return SimpleNamespace(
        connected=False,
        rssi_dbm=None,
        flap_position_pct=0,
        servo_us=1000,
        servo_attached=False,
        fps=0.0,
    )


def _to_utc(dt: datetime) -> datetime:
    """Normalize a naive or aware datetime to UTC for timestamp comparison."""
    if dt.tzinfo is None:
        return dt.astimezone().astimezone(timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_config_like(obj: Any) -> bool:
    return (
        obj is not None
        and hasattr(obj, "servo_closed_us")
        and hasattr(obj, "target_fps")
        and hasattr(obj, "manual_layout")
    )


def _resolve_runtime_context() -> tuple[Any, Any, Any]:
    """Retrieve live server config, device status, and optional LinkState without circular imports."""
    for mod_name in ("server.main", "__main__"):
        mod = sys.modules.get(mod_name)
        candidate = getattr(mod, "state", None) if mod is not None else None
        if (
            candidate is not None
            and hasattr(candidate, "store")
            and hasattr(candidate, "device_status")
        ):
            return candidate.store.config, candidate.device_status, candidate

    # Fallback during LinkState.__init__ or standalone LayoutEngine.evaluate(config) calls.
    fallback_config: Any = None
    frame = inspect.currentframe()
    try:
        cursor = frame.f_back if frame is not None else None
        while cursor is not None:
            local_self = cursor.f_locals.get("self")
            if (
                local_self is not None
                and hasattr(local_self, "store")
                and hasattr(local_self, "device_status")
            ):
                return local_self.store.config, local_self.device_status, local_self
            if fallback_config is None:
                local_cfg = cursor.f_locals.get("config")
                if _is_config_like(local_cfg):
                    fallback_config = local_cfg
            cursor = cursor.f_back
    finally:
        del frame

    return fallback_config or _default_config(), _default_device(), None


def _is_recent_flap_sweep(
    link_state: Any,
    config: HrznConfig,
    reference_utc: datetime,
) -> bool:
    """Check whether a recent `flap_move` log entry falls within the active sweep window."""
    ws_logs = getattr(link_state, "ws_logs", None)
    if not ws_logs:
        return False

    sweep_window_s = (config.sweep_duration_ms + config.settle_detach_ms) / 1000.0
    if sweep_window_s <= 0:
        return False

    for entry in reversed(ws_logs):
        if entry.get("event") != "flap_move":
            continue
        raw_ts = entry.get("ts")
        if not isinstance(raw_ts, str):
            return False
        try:
            event_ts = _to_utc(datetime.fromisoformat(raw_ts))
        except ValueError:
            return False
        elapsed_s = (reference_utc - event_ts).total_seconds()
        return 0.0 <= elapsed_s <= sweep_window_s
    return False


def _resolve_flap_state(
    config: HrznConfig,
    device: DeviceStatus,
    link_state: Any,
    reference_utc: datetime,
) -> str:
    """Derive normalized flap actuator state: OPEN, CLOSED, or MOVING."""
    raw_cfg_state = str(config.flap_state).strip().upper()
    if (
        device.servo_attached
        or raw_cfg_state == "MOVING"
        or (device.connected and abs(int(device.flap_position_pct) - int(config.target_angle_pct)) > 2)
        or _is_recent_flap_sweep(link_state, config, reference_utc)
    ):
        return "MOVING"

    if raw_cfg_state == "CLOSED" or int(config.target_angle_pct) <= 0:
        return "CLOSED"
    return "OPEN"


def _resolve_servo_pulse_us(config: HrznConfig, device: DeviceStatus) -> int:
    """Return live reported servo pulse width (µs) or interpolate from target angle."""
    if device.connected or device.servo_attached:
        return int(device.servo_us)
    span = int(config.servo_open_us) - int(config.servo_closed_us)
    return round(int(config.servo_closed_us) + (span * int(config.target_angle_pct)) / 100.0)


def _resolve_active_layout(config: HrznConfig, link_state: Any) -> str:
    """Return the active HUD grid layout identifier."""
    if config.layout_mode == "manual":
        return str(config.manual_layout)
    latest_layout = getattr(link_state, "latest_layout", None)
    if latest_layout is not None and getattr(latest_layout, "active_layout", None):
        return str(latest_layout.active_layout)
    return str(config.manual_layout)


def _estimate_frame_latency_ms(
    config: HrznConfig,
    link_state: Any,
    renderer_mode: str,
) -> int:
    """Return measured frame latency if present or estimate pipeline encode latency in ms."""
    measured = getattr(link_state, "last_frame_latency_ms", None)
    if isinstance(measured, (int, float)) and measured >= 0:
        return max(1, round(float(measured)))

    base_ms = 28.0 if renderer_mode == "playwright" else 9.0
    pixel_scale = (max(1, int(config.display_width)) * max(1, int(config.display_height))) / (480.0 * 320.0)
    format_overhead = 6.0 if config.frame_format == "JPEG" else 3.0
    return max(1, round(base_ms * pixel_scale + format_overhead))


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class TelemetryPluginProvider(HudPluginProvider):
    """Live stream, flap actuator, servo PWM, and ESP32-S3 diagnostics provider."""

    id = "telemetry"
    name = "HUD Telemetry"
    description = "Live stream FPS, flap state, servo pulse, and configurable link/hardware event triggers."
    base_priority = 6
    default_dynamic_mode = "on_event"
    supports_on_event = True
    default_settings: dict[str, Any] = {
        "dynamicMode": "on_event",
        "userPriority": 6,
        "accentColor": "#00f0ff",
        "showFps": True,
        "showFlapState": True,
        "showServoPulse": True,
        "showDeviceStatus": True,
        "showLatency": True,
        "showLayout": False,
        "compactLabels": False,
        "showCornerBrackets": True,
        "autoSurfaceOnEvent": True,
        "activeWhenFlapOpen": False,
        "triggerOnFlapMove": True,
        "triggerOnFlapOpen": False,
        "triggerOnDeviceDisconnect": False,
        "triggerOnWeakWifi": True,
        "rssiThresholdDbm": -75,
        "triggerOnHighLatency": False,
        "latencyThresholdMs": 60,
        "triggerOnLowFps": False,
        "minFpsThreshold": 1.5,
    }

    def evaluate(
        self,
        settings: dict[str, Any],
        now: Optional[datetime] = None,
    ) -> PluginRuntimeStatus:
        merged = self.merge_settings(settings)
        reference_utc = _to_utc(now) if now is not None else datetime.now(timezone.utc)

        config, device, link_state = _resolve_runtime_context()

        device_connected = bool(device.connected)
        stream_fps = (
            round(float(device.fps), 1)
            if device_connected and float(device.fps) > 0
            else round(float(config.target_fps), 1)
        )
        flap_state = _resolve_flap_state(config, device, link_state, reference_utc)
        servo_pulse_us = _resolve_servo_pulse_us(config, device)
        wifi_rssi = int(device.rssi_dbm) if device.rssi_dbm is not None else None
        playwright_capture = getattr(link_state, "playwright_capture", None)
        renderer_mode = (
            "playwright"
            if playwright_capture is not None and getattr(playwright_capture, "is_ready", False)
            else "pillow-fallback"
        )
        frame_latency_ms = _estimate_frame_latency_ms(config, link_state, renderer_mode)
        active_layout = _resolve_active_layout(config, link_state)

        trigger_flap_move = bool(
            merged.get("triggerOnFlapMove", merged.get("autoSurfaceOnEvent", True))
        )
        trigger_flap_open = bool(merged.get("triggerOnFlapOpen", False))
        trigger_disconnect = bool(merged.get("triggerOnDeviceDisconnect", False))
        trigger_weak_wifi = bool(merged.get("triggerOnWeakWifi", True))
        rssi_thresh = _coerce_int(merged.get("rssiThresholdDbm"), -75)
        trigger_high_latency = bool(merged.get("triggerOnHighLatency", False))
        latency_thresh = _coerce_int(merged.get("latencyThresholdMs"), 60)
        trigger_low_fps = bool(merged.get("triggerOnLowFps", False))
        min_fps = _coerce_float(merged.get("minFpsThreshold"), 1.5)

        active_triggers: list[str] = []
        if trigger_flap_move and flap_state == "MOVING":
            active_triggers.append("Flap moving")
        if trigger_flap_open and flap_state == "OPEN":
            active_triggers.append("Flap open")
        if trigger_disconnect and not device_connected:
            active_triggers.append("ESP32 offline")
        if trigger_weak_wifi and wifi_rssi is not None and wifi_rssi <= rssi_thresh:
            active_triggers.append(f"Weak Wi-Fi ({wifi_rssi} dBm <= {rssi_thresh})")
        if trigger_high_latency and frame_latency_ms >= latency_thresh:
            active_triggers.append(f"High latency ({frame_latency_ms} ms >= {latency_thresh})")
        if trigger_low_fps and device_connected and stream_fps < min_fps:
            active_triggers.append(f"Low FPS ({stream_fps:.1f} < {min_fps:.1f})")

        event_triggered = len(active_triggers) > 0
        if event_triggered:
            reason = ", ".join(active_triggers)
        else:
            reason = (
                f"Flap {flap_state.lower()} · "
                f"{'ESP32 online' if device_connected else 'ESP32 standby'}"
            )

        return PluginRuntimeStatus(
            id=self.id,
            name=self.name,
            event_triggered=event_triggered,
            reason=reason,
            data={
                "stream_fps": stream_fps,
                "flap_state": flap_state,
                "servo_pulse_us": servo_pulse_us,
                "device_connected": device_connected,
                "device_status": "ONLINE" if device_connected else "OFFLINE",
                "wifi_rssi": wifi_rssi,
                "frame_latency_ms": frame_latency_ms,
                "active_layout": active_layout,
                "renderer_mode": renderer_mode,
                "target_angle_pct": int(config.target_angle_pct),
                "flap_position_pct": int(device.flap_position_pct),
                "servo_attached": bool(device.servo_attached),
            },
        )


Provider = TelemetryPluginProvider
