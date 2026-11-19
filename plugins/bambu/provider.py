"""Bambu Lab LAN MQTT telemetry provider auto-discovered from `plugins/bambu/`."""

from __future__ import annotations

import inspect
import json
import os
import secrets
import select
import socket
import ssl
import struct
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter

from server.plugins.base import HudPluginProvider, PluginRuntimeStatus

try:
    import paho.mqtt.client as mqtt  # type: ignore[import-untyped]

    _HAS_PAHO_MQTT = True
except ImportError:
    mqtt = None  # type: ignore[assignment]
    _HAS_PAHO_MQTT = False

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

BAMBU_MQTT_PORT = 8883
BAMBU_MQTT_USER = "bblp"
BAMBU_VALID_STATES = ("IDLE", "PREPARE", "RUNNING", "PAUSE", "FINISH", "FAILED")

BACKOFF_SCHEDULE_S = (2.0, 4.0, 8.0, 15.0, 30.0)
MQTT_KEEPALIVE_S = 60

# Known Bambu Lab `stg_cur` stage codes from LAN MQTT `print.stg_cur`
BAMBU_STAGE_MAP: dict[int, str] = {
    0: "PRINTING",
    1: "BED LEVELING",
    2: "HEATING",
    3: "CALIBRATING",
    4: "FILAMENT CHANGE",
    5: "PAUSED",
    6: "FILAMENT RUNOUT",
    7: "HEATING",
    8: "CALIBRATING",
    9: "SCANNING BED",
    10: "INSPECTING LAYER",
    11: "IDENTIFYING PLATE",
    12: "CALIBRATING",
    13: "HOMING",
    14: "CLEANING NOZZLE",
    15: "COOLING CHECK",
    16: "PAUSED",
    17: "COVER OPEN",
    18: "CALIBRATING",
    19: "CALIBRATING FLOW",
    20: "NOZZLE ERROR",
    21: "BED ERROR",
    22: "UNLOADING",
    23: "SKIPPED STEP",
    24: "LOADING",
    25: "CALIBRATING",
    26: "AMS LOST",
    27: "LOW HEAT",
    28: "COOLING",
    29: "COOLING",
    30: "PAUSED",
    35: "NOZZLE CLOG",
}

_PAUSE_STAGE_OVERRIDES = {4, 6, 17, 20, 21, 22, 24, 26, 35}
_FAILED_STAGE_OVERRIDES = {6, 17, 20, 21, 23, 26, 35}


def _resolve_data_dir() -> Path:
    env_dir = os.getenv("HRZN_DATA_DIR")
    return Path(env_dir) if env_dir else (REPO_ROOT / "data")


def _ensure_plugin_routes_before_catchall() -> None:
    """Move any dynamically mounted `/api/plugins/*` routes ahead of SPA `/{full_path:path}`."""
    app = None
    reg_mod = sys.modules.get("server.plugins.registry")
    if reg_mod is not None:
        app = getattr(reg_mod, "_MOUNTED_APP", None)
    if app is None:
        main_mod = sys.modules.get("server.main")
        if main_mod is not None:
            app = getattr(main_mod, "app", None)
    router = getattr(app, "router", None) if app is not None else None
    routes = getattr(router, "routes", None) if router is not None else None
    if not isinstance(routes, list):
        return

    catchall_idx = next(
        (
            idx
            for idx, route in enumerate(routes)
            if getattr(route, "path", None) == "/{full_path:path}"
        ),
        None,
    )
    if catchall_idx is None:
        return

    after = routes[catchall_idx + 1 :]
    trailing_plugin_routes = [
        route for route in after if str(getattr(route, "path", "")).startswith("/api/plugins/")
    ]
    if not trailing_plugin_routes:
        return

    trailing_ids = {id(route) for route in trailing_plugin_routes}
    remaining_after = [route for route in after if id(route) not in trailing_ids]
    routes[:] = (
        routes[:catchall_idx]
        + trailing_plugin_routes
        + [routes[catchall_idx]]
        + remaining_after
    )
    if hasattr(app, "openapi_schema"):
        app.openapi_schema = None


def normalize_gcode_state(raw: Any) -> str:
    """Normalize Bambu `gcode_state` strings into canonical HUD states."""
    text = str(raw or "").strip().upper()
    if text in ("SLICING", "INIT"):
        return "PREPARE"
    if text in BAMBU_VALID_STATES:
        return text
    return "IDLE"


def format_remaining_time(minutes: Any, gcode_state: str = "RUNNING") -> str:
    """Format remaining minutes cleanly as `1h 24m` or `18m`."""
    state = normalize_gcode_state(gcode_state)
    if state == "IDLE" or minutes is None or isinstance(minutes, bool):
        return "--"
    try:
        mins = int(round(float(minutes)))
    except (TypeError, ValueError):
        return "--"
    if mins <= 0:
        return "0m"
    if mins >= 60:
        hours = mins // 60
        rem = mins % 60
        return f"{hours}h {rem}m" if rem > 0 else f"{hours}h"
    return f"{mins}m"


def derive_stage_label(gcode_state: str, stg_cur: int, print_error: int = 0) -> str:
    """Resolve a concise uppercase HUD stage label from `gcode_state` and `stg_cur`."""
    _ = print_error
    state = normalize_gcode_state(gcode_state)
    if state == "FINISH":
        return "COMPLETE"
    if state == "IDLE":
        return "IDLE"
    if state == "FAILED":
        if stg_cur in _FAILED_STAGE_OVERRIDES:
            return BAMBU_STAGE_MAP[stg_cur]
        return "FAILED"
    if state == "PAUSE":
        if stg_cur in _PAUSE_STAGE_OVERRIDES:
            return BAMBU_STAGE_MAP[stg_cur]
        return "PAUSED"
    if stg_cur not in (-1, 255) and stg_cur in BAMBU_STAGE_MAP:
        return BAMBU_STAGE_MAP[stg_cur]
    return "PREPARING" if state == "PREPARE" else "PRINTING"


def _coerce_error_int(value: Any) -> int:
    """Parse integer or hex error code (`print_error`) safely into an int."""
    if value is None or isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = str(value).strip()
    if not text:
        return 0
    try:
        if text.lower().startswith("0x"):
            return max(0, int(text, 16))
        return max(0, int(float(text)))
    except (TypeError, ValueError):
        return 0


def _coerce_nonneg_int(value: Any, default: int = 0) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return max(0, int(round(float(value))))
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, default: int = -1) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _coerce_temp(value: Any, default: float = 0.0) -> float:
    if value is None or isinstance(value, bool):
        return default
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return default


def _coerce_optional_temp(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def _unpack_bambu_temp(raw: Any) -> tuple[Optional[float], Optional[float]]:
    """Unpack a Bambu temperature value (plain float or 32-bit packed `target << 16 | current`)."""
    if raw is None or isinstance(raw, bool):
        return (None, None)

    int_val: Optional[int] = None
    if isinstance(raw, int):
        int_val = raw
    elif isinstance(raw, float):
        return (round(raw, 1), None) if -20.0 <= raw <= 500.0 else (None, None)
    else:
        text = str(raw).strip()
        if not text:
            return (None, None)
        try:
            if text.lower().startswith("0x"):
                int_val = int(text, 16)
            elif "." in text or "e" in text.lower():
                fval = float(text)
                return (round(fval, 1), None) if -20.0 <= fval <= 500.0 else (None, None)
            else:
                int_val = int(text)
        except (TypeError, ValueError):
            return (None, None)

    if int_val < 0:
        return (round(float(int_val), 1), None) if int_val >= -20 else (None, None)

    if int_val == 0xFFFF or int_val == 0xFFFFFFFF:
        return (None, None)

    low = int_val & 0xFFFF
    high = (int_val >> 16) & 0xFFFF
    cur = round(float(low), 1) if low != 0xFFFF and low <= 500 else None
    tgt = round(float(high), 1) if high != 0xFFFF and high <= 500 else None
    return (cur, tgt)


def _build_bambu_ssl_context() -> ssl.SSLContext:
    """Create a TLS context matching Bambu LAN MQTT self-signed printer certificates."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _default_telemetry_state() -> dict[str, Any]:
    return {
        "gcode_state": "IDLE",
        "mc_percent": 0,
        "mc_remaining_time": 0,
        "layer_num": 0,
        "total_layer_num": 0,
        "nozzle_temper": 0.0,
        "nozzle_target_temper": 0.0,
        "nozzle2_temper": None,
        "nozzle2_target_temper": None,
        "has_second_nozzle": False,
        "bed_temper": 0.0,
        "bed_target_temper": 0.0,
        "chamber_temper": None,
        "chamber_target_temper": None,
        "has_chamber": False,
        "subtask_name": "",
        "stg_cur": -1,
        "print_error": 0,
    }


def _encode_mqtt_remaining_length(length: int) -> bytes:
    out = bytearray()
    value = max(0, length)
    while True:
        byte = value % 128
        value //= 128
        if value > 0:
            byte |= 0x80
        out.append(byte)
        if value == 0:
            break
    return bytes(out)


def _encode_mqtt_str(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("!H", len(raw)) + raw


class _StdlibMqttSession:
    """Minimal stdlib MQTT 3.1.1 over TLS client used only if `paho-mqtt` is unavailable."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        client_id: str,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client_id = client_id
        self._sock: Optional[ssl.SSLSocket] = None
        self._rx_buf = bytearray()
        self._packet_id = 1
        self._last_ping = time.monotonic()

    def connect(self, timeout: float = 6.0) -> None:
        raw_sock = socket.create_connection((self.host, self.port), timeout=timeout)
        ctx = _build_bambu_ssl_context()
        tls_sock = ctx.wrap_socket(raw_sock, server_hostname=self.host)
        tls_sock.settimeout(timeout)
        self._sock = tls_sock

        var_header = (
            _encode_mqtt_str("MQTT")
            + bytes([4, 0xC2])
            + struct.pack("!H", MQTT_KEEPALIVE_S)
        )
        payload = (
            _encode_mqtt_str(self.client_id)
            + _encode_mqtt_str(self.username)
            + _encode_mqtt_str(self.password)
        )
        pkt = (
            bytes([0x10])
            + _encode_mqtt_remaining_length(len(var_header) + len(payload))
            + var_header
            + payload
        )
        tls_sock.sendall(pkt)

        pkt_type, body = self._read_packet(timeout=timeout)
        if (pkt_type >> 4) != 2 or len(body) < 2 or body[1] != 0:
            code = body[1] if len(body) >= 2 else -1
            raise ConnectionError(f"MQTT CONNACK rejected (code={code})")
        tls_sock.settimeout(0.5)
        self._last_ping = time.monotonic()

    def subscribe(self, topic: str) -> None:
        if self._sock is None:
            return
        pid = self._next_packet_id()
        body = struct.pack("!H", pid) + _encode_mqtt_str(topic) + bytes([0])
        pkt = bytes([0x82]) + _encode_mqtt_remaining_length(len(body)) + body
        self._sock.sendall(pkt)

    def publish(self, topic: str, payload_text: str) -> None:
        if self._sock is None:
            return
        body = _encode_mqtt_str(topic) + payload_text.encode("utf-8")
        pkt = bytes([0x30]) + _encode_mqtt_remaining_length(len(body)) + body
        self._sock.sendall(pkt)

    def poll_messages(self, timeout: float = 0.5) -> list[bytes]:
        if self._sock is None:
            raise ConnectionError("MQTT socket closed")

        now = time.monotonic()
        if now - self._last_ping >= 30.0:
            self._sock.sendall(b"\xC0\x00")
            self._last_ping = now

        readable, _, _ = select.select([self._sock], [], [], max(0.05, timeout))
        if readable:
            chunk = self._sock.recv(16384)
            if not chunk:
                raise ConnectionError("MQTT broker closed connection")
            self._rx_buf.extend(chunk)

        messages: list[bytes] = []
        while True:
            parsed = self._try_pop_packet()
            if parsed is None:
                break
            pkt_type, body = parsed
            msg_kind = pkt_type >> 4
            if msg_kind == 3 and len(body) >= 2:
                topic_len = struct.unpack("!H", body[:2])[0]
                idx = 2 + topic_len
                qos = (pkt_type >> 1) & 0x03
                if qos > 0 and len(body) >= idx + 2:
                    pid = struct.unpack("!H", body[idx : idx + 2])[0]
                    idx += 2
                    if qos == 1:
                        self._sock.sendall(bytes([0x40, 0x02]) + struct.pack("!H", pid))
                messages.append(bytes(body[idx:]))
        return messages

    def close(self) -> None:
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.sendall(b"\xE0\x00")
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def _next_packet_id(self) -> int:
        pid = self._packet_id
        self._packet_id = 1 if self._packet_id >= 65535 else self._packet_id + 1
        return pid

    def _read_packet(self, timeout: float) -> tuple[int, bytes]:
        if self._sock is None:
            raise ConnectionError("MQTT socket closed")
        deadline = time.monotonic() + timeout
        while True:
            parsed = self._try_pop_packet()
            if parsed is not None:
                return parsed
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Timed out waiting for MQTT packet")
            readable, _, _ = select.select([self._sock], [], [], min(0.5, remaining))
            if not readable:
                continue
            chunk = self._sock.recv(8192)
            if not chunk:
                raise ConnectionError("MQTT socket closed during handshake")
            self._rx_buf.extend(chunk)

    def _try_pop_packet(self) -> Optional[tuple[int, bytes]]:
        if len(self._rx_buf) < 2:
            return None
        multiplier = 1
        rem_len = 0
        idx = 1
        while True:
            if idx >= len(self._rx_buf):
                return None
            encoded = self._rx_buf[idx]
            rem_len += (encoded & 0x7F) * multiplier
            idx += 1
            if (encoded & 0x80) == 0:
                break
            multiplier *= 128
            if multiplier > 128 * 128 * 128:
                raise ValueError("Malformed MQTT remaining length")
        total = idx + rem_len
        if len(self._rx_buf) < total:
            return None
        pkt_type = self._rx_buf[0]
        body = bytes(self._rx_buf[idx:total])
        del self._rx_buf[:total]
        return pkt_type, body


class BambuPluginProvider(HudPluginProvider):
    """Live Bambu Lab 3D Printer LAN MQTT telemetry provider with built-in Mock Mode."""

    id = "bambu"
    name = "Bambu Lab Printer"
    description = (
        "Live print progress, nozzle & bed temperatures, layer count, ETA, "
        "and automatic print-start split screen."
    )
    version = "1.0.0"
    base_priority = 8
    default_dynamic_mode = "on_event"
    supports_on_event = True
    default_settings: dict[str, Any] = {
        "dynamicMode": "on_event",
        "userPriority": 8,
        "accentColor": "#00f0ff",
        "printerIp": "",
        "serialNumber": "",
        "accessCode": "",
        "printerName": "BAMBU LAB",
        "mockMode": False,
        "mockState": "RUNNING",
        "showTemperatures": True,
        "showChamberTemp": True,
        "showSecondNozzle": True,
        "showLayerCount": True,
        "showRemainingTime": True,
        "showPrintStage": True,
        "showCornerBrackets": True,
        "triggerOnPrintStart": True,
        "triggerWhilePrinting": True,
        "triggerOnPrintFinish": True,
        "triggerOnErrorOrPause": True,
    }

    def __init__(self, start_worker: bool = True) -> None:
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._reconnect_event = threading.Event()

        self._last_settings: Optional[dict[str, Any]] = None
        self._last_live_cfg: Optional[dict[str, Any]] = None
        self._last_conn_signature: Optional[tuple[str, str, str, bool]] = None

        self._telemetry: dict[str, Any] = _default_telemetry_state()
        self._extruder_info_seen: bool = False
        self._connection_state: str = "DISCONNECTED"
        self._connected: bool = False
        self._last_error: Optional[str] = None
        self._last_update_at: Optional[str] = None

        self._mock_anchor_mono: Optional[float] = None
        self._mock_anchor_state: Optional[str] = None

        self._last_evaluated_gcode_state: str = "IDLE"
        self._worker_thread: Optional[threading.Thread] = None

        if start_worker:
            self._register_and_start_worker()

    def _register_and_start_worker(self) -> None:
        """Stop any previously reloaded Bambu MQTT worker thread before launching a fresh one."""
        reg_mod = sys.modules.get("server.plugins.registry")
        if reg_mod is not None:
            prev_stop = getattr(reg_mod, "_bambu_mqtt_stop", None)
            prev_wake = getattr(reg_mod, "_bambu_mqtt_wake", None)
            if isinstance(prev_stop, threading.Event):
                prev_stop.set()
            if isinstance(prev_wake, threading.Event):
                prev_wake.set()
            setattr(reg_mod, "_bambu_mqtt_stop", self._stop_event)
            setattr(reg_mod, "_bambu_mqtt_wake", self._wake_event)

        thread = threading.Thread(
            target=self._worker_loop,
            name="bambu-mqtt-worker",
            daemon=True,
        )
        self._worker_thread = thread
        thread.start()

    def stop(self) -> None:
        """Stop the background LAN MQTT connection thread cleanly."""
        self._stop_event.set()
        self._wake_event.set()
        if self._worker_thread is not None and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.5)

    def _read_live_store_settings(self) -> Optional[dict[str, Any]]:
        for mod_name in ("server.main", "__main__"):
            mod = sys.modules.get(mod_name)
            candidate = getattr(mod, "state", None) if mod is not None else None
            store = getattr(candidate, "store", None) if candidate is not None else None
            cfg = getattr(store, "config", None) if store is not None else None
            plugin_configs = getattr(cfg, "plugin_configs", None) if cfg is not None else None
            if isinstance(plugin_configs, dict):
                bambu_cfg = plugin_configs.get(self.id) or plugin_configs.get("bambu")
                return dict(bambu_cfg) if isinstance(bambu_cfg, dict) else {}
        return None

    def _read_disk_settings(self) -> dict[str, Any]:
        cfg_path = _resolve_data_dir() / "config.json"
        if not cfg_path.is_file():
            return {}
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        plugin_configs = raw.get("plugin_configs") if isinstance(raw, dict) else None
        if isinstance(plugin_configs, dict):
            bambu_cfg = plugin_configs.get(self.id) or plugin_configs.get("bambu")
            if isinstance(bambu_cfg, dict):
                return dict(bambu_cfg)
        return {}

    def _resolve_saved_settings(self) -> dict[str, Any]:
        """Resolve latest user settings from live store, disk config, or evaluate cache."""
        merged = self.merge_settings(None)
        live_cfg = self._read_live_store_settings()

        with self._lock:
            last_settings = dict(self._last_settings) if self._last_settings is not None else None
            last_live = dict(self._last_live_cfg) if self._last_live_cfg is not None else None

            if live_cfg is not None:
                if last_settings is not None and last_live == live_cfg:
                    merged.update(live_cfg)
                    merged.update(last_settings)
                else:
                    self._last_live_cfg = dict(live_cfg)
                    merged.update(live_cfg)
                return merged

        disk_cfg = self._read_disk_settings()
        if disk_cfg:
            merged.update(disk_cfg)
        if last_settings is not None:
            merged.update(last_settings)
        return merged

    def _notify_main_layout_refresh(self) -> None:
        mod = sys.modules.get("server.main")
        state_obj = getattr(mod, "state", None) if mod is not None else None
        if state_obj is not None and hasattr(state_obj, "refresh_layout"):
            try:
                state_obj.refresh_layout()
            except Exception:
                pass

    def _clear_layout_hold(self, force: bool = False) -> None:
        """Clear hold cooldown on active LayoutEngine(s) when printer returns to IDLE."""
        engines: list[Any] = []
        mod = sys.modules.get("server.main")
        state_obj = getattr(mod, "state", None) if mod is not None else None
        main_engine = getattr(state_obj, "layout_engine", None) if state_obj is not None else None
        if main_engine is not None:
            engines.append(main_engine)

        frame = inspect.currentframe()
        try:
            cursor = frame.f_back if frame is not None else None
            while cursor is not None:
                local_self = cursor.f_locals.get("self")
                if (
                    local_self is not None
                    and local_self not in engines
                    and hasattr(local_self, "_last_triggered_at")
                    and hasattr(local_self, "_test_triggered_at")
                ):
                    engines.append(local_self)
                cursor = cursor.f_back
        finally:
            del frame

        for engine in engines:
            last_map = getattr(engine, "_last_triggered_at", None)
            test_map = getattr(engine, "_test_triggered_at", None)
            if not isinstance(last_map, dict):
                continue
            last_ts = last_map.get(self.id)
            if last_ts is None:
                continue
            test_ts = test_map.get(self.id) if isinstance(test_map, dict) else None
            if force or test_ts is None or last_ts != test_ts:
                last_map.pop(self.id, None)
                if force and isinstance(test_map, dict):
                    test_map.pop(self.id, None)

    def apply_report_payload(self, raw_payload: bytes | str | dict[str, Any]) -> bool:
        """Merge a Bambu `device/<serial>/report` JSON delta payload into cached telemetry."""
        payload: Any = raw_payload
        if isinstance(raw_payload, (bytes, bytearray)):
            try:
                payload = json.loads(raw_payload.decode("utf-8", errors="replace"))
            except ValueError:
                return False
        elif isinstance(raw_payload, str):
            try:
                payload = json.loads(raw_payload)
            except ValueError:
                return False

        if not isinstance(payload, dict):
            return False

        print_obj = payload.get("print")
        if not isinstance(print_obj, dict):
            return False

        state_or_err_changed = False
        now_utc = datetime.now(timezone.utc).isoformat()

        with self._lock:
            prev_state = self._telemetry["gcode_state"]
            prev_err = self._telemetry["print_error"]

            if "gcode_state" in print_obj and print_obj["gcode_state"] is not None:
                self._telemetry["gcode_state"] = normalize_gcode_state(print_obj["gcode_state"])

            if "mc_percent" in print_obj and print_obj["mc_percent"] is not None:
                pct = _coerce_nonneg_int(print_obj["mc_percent"], self._telemetry["mc_percent"])
                self._telemetry["mc_percent"] = max(0, min(100, pct))

            if "mc_remaining_time" in print_obj and print_obj["mc_remaining_time"] is not None:
                self._telemetry["mc_remaining_time"] = _coerce_nonneg_int(
                    print_obj["mc_remaining_time"],
                    self._telemetry["mc_remaining_time"],
                )

            if "layer_num" in print_obj and print_obj["layer_num"] is not None:
                self._telemetry["layer_num"] = _coerce_nonneg_int(
                    print_obj["layer_num"],
                    self._telemetry["layer_num"],
                )

            if "total_layer_num" in print_obj and print_obj["total_layer_num"] is not None:
                self._telemetry["total_layer_num"] = _coerce_nonneg_int(
                    print_obj["total_layer_num"],
                    self._telemetry["total_layer_num"],
                )

            if "nozzle_temper" in print_obj and print_obj["nozzle_temper"] is not None:
                if not self._extruder_info_seen:
                    self._telemetry["nozzle_temper"] = _coerce_temp(
                        print_obj["nozzle_temper"],
                        self._telemetry["nozzle_temper"],
                    )

            if "nozzle_target_temper" in print_obj and print_obj["nozzle_target_temper"] is not None:
                if not self._extruder_info_seen:
                    self._telemetry["nozzle_target_temper"] = _coerce_temp(
                        print_obj["nozzle_target_temper"],
                        self._telemetry["nozzle_target_temper"],
                    )

            for raw_n2_key in ("nozzle_temper_1", "nozzle2_temper"):
                if raw_n2_key in print_obj and print_obj[raw_n2_key] is not None:
                    n2_cur = _coerce_optional_temp(print_obj[raw_n2_key])
                    if n2_cur is not None:
                        self._telemetry["nozzle2_temper"] = n2_cur
                        self._telemetry["has_second_nozzle"] = True

            for raw_n2_tgt_key in ("nozzle_target_temper_1", "nozzle2_target_temper"):
                if raw_n2_tgt_key in print_obj and print_obj[raw_n2_tgt_key] is not None:
                    n2_tgt = _coerce_optional_temp(print_obj[raw_n2_tgt_key])
                    if n2_tgt is not None:
                        self._telemetry["nozzle2_target_temper"] = n2_tgt
                        self._telemetry["has_second_nozzle"] = True

            if "bed_temper" in print_obj and print_obj["bed_temper"] is not None:
                self._telemetry["bed_temper"] = _coerce_temp(
                    print_obj["bed_temper"],
                    self._telemetry["bed_temper"],
                )

            if "bed_target_temper" in print_obj and print_obj["bed_target_temper"] is not None:
                self._telemetry["bed_target_temper"] = _coerce_temp(
                    print_obj["bed_target_temper"],
                    self._telemetry["bed_target_temper"],
                )

            if "chamber_temper" in print_obj and print_obj["chamber_temper"] is not None:
                ch_cur = _coerce_optional_temp(print_obj["chamber_temper"])
                if ch_cur is not None:
                    self._telemetry["chamber_temper"] = ch_cur
                    self._telemetry["has_chamber"] = True

            if "chamber_target_temper" in print_obj and print_obj["chamber_target_temper"] is not None:
                ch_tgt = _coerce_optional_temp(print_obj["chamber_target_temper"])
                if ch_tgt is not None:
                    self._telemetry["chamber_target_temper"] = ch_tgt

            device_obj = print_obj.get("device") if isinstance(print_obj.get("device"), dict) else {}

            # Newer Bambu firmware (H2D / X1E / P2S) packs dual-nozzle, chamber (CTC), & bed under device.*
            extruder_obj = (
                device_obj.get("extruder")
                if isinstance(device_obj.get("extruder"), dict)
                else (print_obj.get("extruder") if isinstance(print_obj.get("extruder"), dict) else None)
            )
            if isinstance(extruder_obj, dict) and isinstance(extruder_obj.get("info"), list):
                info_list = [item for item in extruder_obj["info"] if isinstance(item, dict)]
                if len(info_list) >= 2 or any(_coerce_int(item.get("id"), -1) == 1 for item in info_list):
                    self._extruder_info_seen = True
                    self._telemetry["has_second_nozzle"] = True
                for item in info_list:
                    ext_id = _coerce_int(item.get("id"), -1)
                    if "temp" not in item or item["temp"] is None:
                        continue
                    cur, tgt = _unpack_bambu_temp(item["temp"])
                    if ext_id == 0:
                        if cur is not None:
                            self._telemetry["nozzle_temper"] = cur
                        if tgt is not None:
                            self._telemetry["nozzle_target_temper"] = tgt
                    elif ext_id == 1:
                        self._telemetry["has_second_nozzle"] = True
                        if cur is not None:
                            self._telemetry["nozzle2_temper"] = cur
                        if tgt is not None:
                            self._telemetry["nozzle2_target_temper"] = tgt

            ctc_obj = (
                device_obj.get("ctc")
                if isinstance(device_obj.get("ctc"), dict)
                else (print_obj.get("ctc") if isinstance(print_obj.get("ctc"), dict) else None)
            )
            if isinstance(ctc_obj, dict):
                ctc_info = ctc_obj.get("info") if isinstance(ctc_obj.get("info"), dict) else {}
                if "temp" in ctc_info and ctc_info["temp"] is not None:
                    ch_cur, ch_tgt = _unpack_bambu_temp(ctc_info["temp"])
                    self._telemetry["has_chamber"] = True
                    if ch_cur is not None:
                        self._telemetry["chamber_temper"] = ch_cur
                    if ch_tgt is not None:
                        self._telemetry["chamber_target_temper"] = ch_tgt
                for raw_ctc_tgt in (ctc_info.get("target"), ctc_obj.get("target_temp")):
                    if raw_ctc_tgt is not None:
                        tgt_val, _ = _unpack_bambu_temp(raw_ctc_tgt)
                        if tgt_val is not None:
                            self._telemetry["chamber_target_temper"] = tgt_val
                            self._telemetry["has_chamber"] = True

            if "bed_temper" not in print_obj or print_obj.get("bed_temper") is None:
                bed_obj = device_obj.get("bed") if isinstance(device_obj.get("bed"), dict) else None
                bed_info = (
                    bed_obj.get("info")
                    if isinstance(bed_obj, dict) and isinstance(bed_obj.get("info"), dict)
                    else None
                )
                if isinstance(bed_info, dict) and "temp" in bed_info and bed_info["temp"] is not None:
                    bed_cur, bed_tgt = _unpack_bambu_temp(bed_info["temp"])
                    if bed_cur is not None:
                        self._telemetry["bed_temper"] = bed_cur
                    if bed_tgt is not None and (
                        "bed_target_temper" not in print_obj
                        or print_obj.get("bed_target_temper") is None
                    ):
                        self._telemetry["bed_target_temper"] = bed_tgt

            if "subtask_name" in print_obj and print_obj["subtask_name"] is not None:
                subtask = str(print_obj["subtask_name"]).strip()
                if subtask:
                    self._telemetry["subtask_name"] = subtask
                elif print_obj.get("gcode_file"):
                    self._telemetry["subtask_name"] = Path(str(print_obj["gcode_file"])).name
                elif self._telemetry["gcode_state"] == "IDLE":
                    self._telemetry["subtask_name"] = ""
            elif "gcode_file" in print_obj and print_obj["gcode_file"] and not self._telemetry["subtask_name"]:
                self._telemetry["subtask_name"] = Path(str(print_obj["gcode_file"])).name

            if "stg_cur" in print_obj and print_obj["stg_cur"] is not None:
                self._telemetry["stg_cur"] = _coerce_int(
                    print_obj["stg_cur"],
                    self._telemetry["stg_cur"],
                )

            if "print_error" in print_obj and print_obj["print_error"] is not None:
                self._telemetry["print_error"] = _coerce_error_int(print_obj["print_error"])

            self._last_update_at = now_utc
            state_or_err_changed = (
                self._telemetry["gcode_state"] != prev_state
                or self._telemetry["print_error"] != prev_err
            )

        if state_or_err_changed:
            self._notify_main_layout_refresh()
        return True

    def _build_mock_telemetry(
        self,
        mock_state: str,
        now_mono: Optional[float] = None,
    ) -> dict[str, Any]:
        """Generate realistic live telemetry for HUD & Dynamic Mode simulation."""
        state = normalize_gcode_state(mock_state)
        current_mono = time.monotonic() if now_mono is None else float(now_mono)

        with self._lock:
            if self._mock_anchor_mono is None or self._mock_anchor_state != state:
                self._mock_anchor_mono = current_mono
                self._mock_anchor_state = state
            elapsed = max(0.0, current_mono - self._mock_anchor_mono)

        if state == "RUNNING":
            tick_steps = int(elapsed // 2.0) % 52  # 48% -> 99% cycling smoothly
            mc_percent = 48 + tick_steps
            total_layers = 310
            layer_num = min(
                total_layers,
                148 + round((tick_steps / 51.0) * (total_layers - 148)),
            )
            remaining_min = max(1, round(((100 - mc_percent) / 52.0) * 34.0))
            return {
                "gcode_state": "RUNNING",
                "mc_percent": mc_percent,
                "mc_remaining_time": remaining_min,
                "layer_num": layer_num,
                "total_layer_num": total_layers,
                "nozzle_temper": 220.0,
                "nozzle_target_temper": 220.0,
                "nozzle2_temper": 145.0,
                "nozzle2_target_temper": 0.0,
                "has_second_nozzle": True,
                "bed_temper": 60.0,
                "bed_target_temper": 60.0,
                "chamber_temper": 38.0,
                "chamber_target_temper": 45.0,
                "has_chamber": True,
                "subtask_name": "HRZN01_Chassis_v4.3mf",
                "stg_cur": 0,
                "print_error": 0,
            }

        if state == "PREPARE":
            leveling_phase = (int(elapsed // 6.0) % 2) == 1
            return {
                "gcode_state": "PREPARE",
                "mc_percent": 0,
                "mc_remaining_time": 84,
                "layer_num": 0,
                "total_layer_num": 310,
                "nozzle_temper": 220.0 if leveling_phase else 185.0,
                "nozzle_target_temper": 220.0,
                "nozzle2_temper": 180.0,
                "nozzle2_target_temper": 215.0,
                "has_second_nozzle": True,
                "bed_temper": 60.0 if leveling_phase else 55.0,
                "bed_target_temper": 60.0,
                "chamber_temper": 34.0,
                "chamber_target_temper": 45.0,
                "has_chamber": True,
                "subtask_name": "HRZN01_Chassis_v4.3mf",
                "stg_cur": 1 if leveling_phase else 2,
                "print_error": 0,
            }

        if state == "PAUSE":
            return {
                "gcode_state": "PAUSE",
                "mc_percent": 68,
                "mc_remaining_time": 18,
                "layer_num": 211,
                "total_layer_num": 310,
                "nozzle_temper": 220.0,
                "nozzle_target_temper": 220.0,
                "nozzle2_temper": 160.0,
                "nozzle2_target_temper": 0.0,
                "has_second_nozzle": True,
                "bed_temper": 60.0,
                "bed_target_temper": 60.0,
                "chamber_temper": 39.0,
                "chamber_target_temper": 45.0,
                "has_chamber": True,
                "subtask_name": "HRZN01_Chassis_v4.3mf",
                "stg_cur": 16,
                "print_error": 0,
            }

        if state == "FINISH":
            return {
                "gcode_state": "FINISH",
                "mc_percent": 100,
                "mc_remaining_time": 0,
                "layer_num": 310,
                "total_layer_num": 310,
                "nozzle_temper": 42.0,
                "nozzle_target_temper": 0.0,
                "nozzle2_temper": 38.0,
                "nozzle2_target_temper": 0.0,
                "has_second_nozzle": True,
                "bed_temper": 36.0,
                "bed_target_temper": 0.0,
                "chamber_temper": 32.0,
                "chamber_target_temper": 0.0,
                "has_chamber": True,
                "subtask_name": "HRZN01_Chassis_v4.3mf",
                "stg_cur": -1,
                "print_error": 0,
            }

        if state == "FAILED":
            return {
                "gcode_state": "FAILED",
                "mc_percent": 64,
                "mc_remaining_time": 24,
                "layer_num": 198,
                "total_layer_num": 310,
                "nozzle_temper": 195.0,
                "nozzle_target_temper": 0.0,
                "nozzle2_temper": 150.0,
                "nozzle2_target_temper": 0.0,
                "has_second_nozzle": True,
                "bed_temper": 58.0,
                "bed_target_temper": 0.0,
                "chamber_temper": 37.0,
                "chamber_target_temper": 0.0,
                "has_chamber": True,
                "subtask_name": "HRZN01_Chassis_v4.3mf",
                "stg_cur": 6,
                "print_error": 50348044,
            }

        return {
            "gcode_state": "IDLE",
            "mc_percent": 0,
            "mc_remaining_time": 0,
            "layer_num": 0,
            "total_layer_num": 0,
            "nozzle_temper": 28.0,
            "nozzle_target_temper": 0.0,
            "nozzle2_temper": 27.0,
            "nozzle2_target_temper": 0.0,
            "has_second_nozzle": True,
            "bed_temper": 25.0,
            "bed_target_temper": 0.0,
            "chamber_temper": 24.0,
            "chamber_target_temper": 0.0,
            "has_chamber": True,
            "subtask_name": "",
            "stg_cur": -1,
            "print_error": 0,
        }

    def _enrich_telemetry_snapshot(
        self,
        raw: dict[str, Any],
        settings: dict[str, Any],
        *,
        connection_state: str,
        connected: bool,
        configured: bool,
        mock_mode: bool,
        last_update_at: Optional[str],
        error: Optional[str],
    ) -> dict[str, Any]:
        gcode_state = normalize_gcode_state(raw.get("gcode_state"))
        stg_cur = _coerce_int(raw.get("stg_cur"), -1)
        print_error = _coerce_error_int(raw.get("print_error"))
        rem_mins = _coerce_nonneg_int(raw.get("mc_remaining_time"), 0)
        printer_name = str(settings.get("printerName") or "BAMBU LAB").strip() or "BAMBU LAB"

        nozzle2_cur = _coerce_optional_temp(raw.get("nozzle2_temper"))
        nozzle2_tgt = _coerce_optional_temp(raw.get("nozzle2_target_temper"))
        has_second_nozzle = bool(raw.get("has_second_nozzle")) or nozzle2_cur is not None

        chamber_cur = _coerce_optional_temp(raw.get("chamber_temper"))
        chamber_tgt = _coerce_optional_temp(raw.get("chamber_target_temper"))
        has_chamber = bool(raw.get("has_chamber")) or chamber_cur is not None

        return {
            "connection_state": connection_state,
            "connected": connected,
            "configured": configured,
            "mock_mode": mock_mode,
            "printer_name": printer_name,
            "gcode_state": gcode_state,
            "mc_percent": max(0, min(100, _coerce_nonneg_int(raw.get("mc_percent"), 0))),
            "mc_remaining_time": rem_mins,
            "eta_display": format_remaining_time(rem_mins, gcode_state),
            "layer_num": _coerce_nonneg_int(raw.get("layer_num"), 0),
            "total_layer_num": _coerce_nonneg_int(raw.get("total_layer_num"), 0),
            "nozzle_temper": _coerce_temp(raw.get("nozzle_temper"), 0.0),
            "nozzle_target_temper": _coerce_temp(raw.get("nozzle_target_temper"), 0.0),
            "nozzle2_temper": nozzle2_cur,
            "nozzle2_target_temper": nozzle2_tgt,
            "has_second_nozzle": has_second_nozzle,
            "bed_temper": _coerce_temp(raw.get("bed_temper"), 0.0),
            "bed_target_temper": _coerce_temp(raw.get("bed_target_temper"), 0.0),
            "chamber_temper": chamber_cur,
            "chamber_target_temper": chamber_tgt,
            "has_chamber": has_chamber,
            "subtask_name": str(raw.get("subtask_name") or "").strip(),
            "stg_cur": stg_cur,
            "stage_label": derive_stage_label(gcode_state, stg_cur, print_error),
            "print_error": print_error,
            "has_error": bool(print_error != 0 or gcode_state == "FAILED"),
            "last_update_at": last_update_at,
            "error": error,
        }

    def _current_conn_signature(self, settings: dict[str, Any]) -> tuple[str, str, str, bool]:
        return (
            str(settings.get("printerIp") or "").strip(),
            str(settings.get("serialNumber") or "").strip(),
            str(settings.get("accessCode") or "").strip(),
            bool(settings.get("mockMode", False)),
        )

    def _build_paho_client(
        self,
        ip: str,
        serial: str,
        access_code: str,
        target_sig: tuple[str, str, str, bool],
    ) -> Any:
        """Instantiate and configure a `paho-mqtt` client for Bambu LAN TLS."""
        client_id = f"hrzn-bambu-{secrets.token_hex(4)}"
        if hasattr(mqtt, "CallbackAPIVersion"):
            client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
            )
        else:
            client = mqtt.Client(client_id=client_id)

        tls_ctx = _build_bambu_ssl_context()
        client.tls_set_context(tls_ctx)
        client.username_pw_set(BAMBU_MQTT_USER, access_code)

        report_topic = f"device/{serial}/report"
        request_topic = f"device/{serial}/request"

        def on_connect(client_obj: Any, _userdata: Any, _flags: Any, rc_or_reason: Any, _props: Any = None) -> None:
            is_failure = (
                bool(getattr(rc_or_reason, "is_failure", False))
                if hasattr(rc_or_reason, "is_failure")
                else int(rc_or_reason) != 0
            )
            if is_failure:
                with self._lock:
                    self._connected = False
                    self._connection_state = "DISCONNECTED"
                    self._last_error = f"MQTT connection refused ({rc_or_reason})"
                return

            client_obj.subscribe(report_topic, qos=0)
            client_obj.publish(
                request_topic,
                json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}),
                qos=0,
            )
            with self._lock:
                self._connected = True
                self._connection_state = "CONNECTED"
                self._last_error = None
            self._notify_main_layout_refresh()

        def on_message(_client_obj: Any, _userdata: Any, msg: Any) -> None:
            self.apply_report_payload(msg.payload)

        def on_disconnect(*args: Any) -> None:
            # Handle both paho v1 (client, userdata, rc) and v2 (client, userdata, flags, rc, props)
            rc_val = args[-2] if len(args) >= 5 else (args[2] if len(args) >= 3 else 0)
            unexpected = (
                bool(getattr(rc_val, "is_failure", False))
                if hasattr(rc_val, "is_failure")
                else bool(rc_val)
            )
            with self._lock:
                self._connected = False
                if self._current_conn_signature(self._resolve_saved_settings()) == target_sig:
                    self._connection_state = "DISCONNECTED"
                    if unexpected:
                        self._last_error = f"Disconnected from printer ({rc_val})"

        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect
        return client

    def _run_paho_session(
        self,
        ip: str,
        serial: str,
        access_code: str,
        target_sig: tuple[str, str, str, bool],
    ) -> bool:
        """Connect with `paho-mqtt` and service network events until stopped or disconnected."""
        with self._lock:
            self._connection_state = "CONNECTING"
            self._connected = False
            self._last_error = None

        client = self._build_paho_client(ip, serial, access_code, target_sig)
        had_success = False
        try:
            client.connect(ip, BAMBU_MQTT_PORT, keepalive=MQTT_KEEPALIVE_S)
            while not self._stop_event.is_set():
                if self._reconnect_event.is_set():
                    self._reconnect_event.clear()
                    self._wake_event.clear()
                    break
                if self._wake_event.is_set():
                    self._wake_event.clear()
                    if self._current_conn_signature(self._resolve_saved_settings()) != target_sig:
                        break
                rc = client.loop(timeout=0.5)
                if self._connected:
                    had_success = True
                if rc != 0:
                    with self._lock:
                        self._connected = False
                        self._connection_state = "DISCONNECTED"
                        if not self._last_error:
                            self._last_error = f"MQTT socket loop exited (rc={rc})"
                    break
        except Exception as exc:
            with self._lock:
                self._connected = False
                self._connection_state = "DISCONNECTED"
                self._last_error = f"MQTT connect error: {exc}"
        finally:
            try:
                client.disconnect()
            except Exception:
                pass
            with self._lock:
                self._connected = False
                if self._connection_state == "CONNECTING":
                    self._connection_state = "DISCONNECTED"
        return had_success

    def _run_stdlib_session(
        self,
        ip: str,
        serial: str,
        access_code: str,
        target_sig: tuple[str, str, str, bool],
    ) -> bool:
        """Fallback stdlib MQTT TLS session when `paho-mqtt` is absent."""
        with self._lock:
            self._connection_state = "CONNECTING"
            self._connected = False
            self._last_error = None

        session = _StdlibMqttSession(
            host=ip,
            port=BAMBU_MQTT_PORT,
            username=BAMBU_MQTT_USER,
            password=access_code,
            client_id=f"hrzn-bambu-{secrets.token_hex(4)}",
        )
        had_success = False
        try:
            session.connect(timeout=6.0)
            session.subscribe(f"device/{serial}/report")
            session.publish(
                f"device/{serial}/request",
                json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}),
            )
            with self._lock:
                self._connected = True
                self._connection_state = "CONNECTED"
                self._last_error = None
            had_success = True
            self._notify_main_layout_refresh()

            while not self._stop_event.is_set():
                if self._reconnect_event.is_set():
                    self._reconnect_event.clear()
                    self._wake_event.clear()
                    break
                if self._wake_event.is_set():
                    self._wake_event.clear()
                    if self._current_conn_signature(self._resolve_saved_settings()) != target_sig:
                        break
                for payload in session.poll_messages(timeout=0.5):
                    self.apply_report_payload(payload)
        except Exception as exc:
            with self._lock:
                self._connected = False
                self._connection_state = "DISCONNECTED"
                self._last_error = f"MQTT connect error: {exc}"
        finally:
            session.close()
            with self._lock:
                self._connected = False
                if self._connection_state == "CONNECTING":
                    self._connection_state = "DISCONNECTED"
        return had_success

    def _worker_loop(self) -> None:
        backoff_idx = 0
        while not self._stop_event.is_set():
            settings = self._resolve_saved_settings()
            sig = self._current_conn_signature(settings)
            ip, serial, access_code, mock_mode = sig

            if mock_mode:
                with self._lock:
                    self._connected = False
                    self._connection_state = "MOCK_ACTIVE"
                    self._last_error = None
                backoff_idx = 0
                self._wake_event.wait(timeout=1.0)
                self._wake_event.clear()
                continue

            if not ip or not serial or not access_code:
                with self._lock:
                    self._connected = False
                    self._connection_state = "DISCONNECTED"
                    self._last_error = None
                backoff_idx = 0
                self._wake_event.wait(timeout=1.5)
                self._wake_event.clear()
                continue

            if _HAS_PAHO_MQTT:
                had_success = self._run_paho_session(ip, serial, access_code, sig)
            else:
                had_success = self._run_stdlib_session(ip, serial, access_code, sig)

            if self._stop_event.is_set():
                break

            if self._reconnect_event.is_set():
                self._reconnect_event.clear()
                backoff_idx = 0
                continue

            if had_success:
                backoff_idx = 0

            latest_sig = self._current_conn_signature(self._resolve_saved_settings())
            if latest_sig != sig:
                backoff_idx = 0
                continue

            delay_s = BACKOFF_SCHEDULE_S[min(backoff_idx, len(BACKOFF_SCHEDULE_S) - 1)]
            backoff_idx = min(backoff_idx + 1, len(BACKOFF_SCHEDULE_S) - 1)
            self._wake_event.wait(timeout=delay_s)
            self._wake_event.clear()

    def _snapshot_for_settings(
        self,
        settings: dict[str, Any],
        now_mono: Optional[float] = None,
    ) -> dict[str, Any]:
        mock_mode = bool(settings.get("mockMode", False))
        ip = str(settings.get("printerIp") or "").strip()
        serial = str(settings.get("serialNumber") or "").strip()
        access_code = str(settings.get("accessCode") or "").strip()
        configured = bool(ip and serial and access_code)

        if mock_mode:
            mock_state = str(settings.get("mockState") or "RUNNING")
            raw_mock = self._build_mock_telemetry(mock_state, now_mono=now_mono)
            return self._enrich_telemetry_snapshot(
                raw_mock,
                settings,
                connection_state="MOCK_ACTIVE",
                connected=True,
                configured=configured,
                mock_mode=True,
                last_update_at=datetime.now(timezone.utc).isoformat(),
                error=None,
            )

        with self._lock:
            self._mock_anchor_mono = None
            self._mock_anchor_state = None
            raw_live = dict(self._telemetry)
            conn_state = self._connection_state
            connected = self._connected
            last_update_at = self._last_update_at
            error = self._last_error

        if conn_state == "MOCK_ACTIVE":
            conn_state = "DISCONNECTED"
            connected = False

        return self._enrich_telemetry_snapshot(
            raw_live,
            settings,
            connection_state=conn_state,
            connected=connected,
            configured=configured,
            mock_mode=False,
            last_update_at=last_update_at,
            error=error,
        )

    def evaluate(
        self,
        settings: dict[str, Any],
        now: Optional[datetime] = None,
    ) -> PluginRuntimeStatus:
        _ = now
        _ensure_plugin_routes_before_catchall()
        merged = self.merge_settings(settings)
        new_sig = self._current_conn_signature(merged)
        sig_changed = False

        with self._lock:
            self._last_settings = dict(merged)
            if self._last_conn_signature is None:
                self._last_conn_signature = new_sig
                sig_changed = bool(new_sig[0] and new_sig[1] and new_sig[2]) or new_sig[3]
            elif new_sig != self._last_conn_signature:
                self._last_conn_signature = new_sig
                sig_changed = True

        if sig_changed:
            self._wake_event.set()

        snapshot = self._snapshot_for_settings(merged)
        gcode_state = snapshot["gcode_state"]
        print_error = snapshot["print_error"]
        stage_label = snapshot["stage_label"]
        pct = snapshot["mc_percent"]
        eta = snapshot["eta_display"]
        subtask = snapshot["subtask_name"] or snapshot["printer_name"]

        with self._lock:
            prev_state = self._last_evaluated_gcode_state
            self._last_evaluated_gcode_state = gcode_state

        trigger_on_start = bool(merged.get("triggerOnPrintStart", True))
        trigger_while_printing = bool(merged.get("triggerWhilePrinting", True))
        trigger_on_finish = bool(merged.get("triggerOnPrintFinish", True))
        trigger_on_error_or_pause = bool(merged.get("triggerOnErrorOrPause", True))

        if gcode_state == "IDLE":
            if prev_state != "IDLE":
                self._clear_layout_hold(force=False)
            event_triggered = False
            reason = (
                f"Mock IDLE · {snapshot['printer_name']}"
                if snapshot["mock_mode"]
                else (
                    f"{snapshot['printer_name']} idle"
                    if snapshot["connected"]
                    else (
                        "Bambu LAN disconnected"
                        if snapshot["configured"]
                        else "Bambu Lab standby"
                    )
                )
            )
        else:
            just_started = gcode_state in ("RUNNING", "PREPARE") and prev_state != gcode_state
            just_finished = gcode_state == "FINISH" and prev_state != "FINISH"

            active_reasons: list[str] = []
            if trigger_on_error_or_pause and (
                gcode_state in ("PAUSE", "FAILED") or print_error != 0
            ):
                if gcode_state == "FAILED" or print_error != 0:
                    err_tag = f" (err {print_error})" if print_error else ""
                    active_reasons.append(f"Printer alert: {stage_label}{err_tag}")
                else:
                    active_reasons.append(f"Print paused ({pct}% · {subtask})")
            elif trigger_on_finish and just_finished:
                active_reasons.append(f"Print complete ({subtask})")
            elif trigger_on_start and just_started:
                active_reasons.append(f"Print started ({stage_label} · {subtask})")
            elif trigger_while_printing and gcode_state in ("PREPARE", "RUNNING"):
                active_reasons.append(f"{stage_label} {pct}% · ETA {eta}")

            event_triggered = len(active_reasons) > 0
            if event_triggered:
                reason = active_reasons[0]
            elif gcode_state == "FINISH":
                reason = f"Print complete ({subtask})"
            else:
                reason = f"{stage_label} {pct}%"

        return PluginRuntimeStatus(
            id=self.id,
            name=self.name,
            event_triggered=event_triggered,
            reason=reason,
            data=snapshot,
        )

    def get_router(self) -> APIRouter:
        """Expose `/api/plugins/bambu/status` and `/api/plugins/bambu/reconnect`."""
        timer = threading.Timer(0.02, _ensure_plugin_routes_before_catchall)
        timer.daemon = True
        timer.start()

        router = APIRouter()

        @router.get("/status")
        async def get_status() -> dict[str, Any]:
            settings = self._resolve_saved_settings()
            snapshot = self._snapshot_for_settings(settings)
            return {
                "connection_state": snapshot["connection_state"],
                "connected": snapshot["connected"],
                "configured": snapshot["configured"],
                "mock_mode": snapshot["mock_mode"],
                "printer_ip": str(settings.get("printerIp") or "").strip(),
                "printer_name": snapshot["printer_name"],
                "mqtt_backend": "paho-mqtt" if _HAS_PAHO_MQTT else "stdlib-tls",
                "telemetry": snapshot,
                "last_update_at": snapshot["last_update_at"],
                "error": snapshot["error"],
            }

        @router.post("/reconnect")
        async def reconnect_printer() -> dict[str, Any]:
            settings = self._resolve_saved_settings()
            self._reconnect_event.set()
            self._wake_event.set()
            snapshot = self._snapshot_for_settings(settings)
            return {
                "ok": True,
                "connection_state": snapshot["connection_state"],
                "mock_mode": snapshot["mock_mode"],
            }

        return router


Provider = BambuPluginProvider
