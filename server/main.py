"""STANCE // HRZN-LINK FastAPI server, Playwright HUD capture, and WebSocket hub."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from server.config_store import (
    BrightnessCommand,
    ConfigStore,
    DeviceStatus,
    FlapCommand,
    HrznConfigPatch,
)
from server.layout_engine import LayoutEngine, LayoutEvaluationResult
from server.plugins import (
    get_plugin_manifests,
    get_plugin_provider,
    merge_plugin_configs,
    reload_plugins,
    resolve_plugin_file,
)
from server.renderer import HUD_HEIGHT, HUD_WIDTH, HudRenderer, PlaywrightHudCapture

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIST_DIR = REPO_ROOT / "web" / "dist"
MAX_WS_LOG_ENTRIES = 100


class LinkState:
    """In-memory runtime coordinator for device/UI sockets, layout engine, and frames."""

    def __init__(self) -> None:
        self.store = ConfigStore()
        self.layout_engine = LayoutEngine()
        self.renderer = HudRenderer(
            self.store.config.display_width or HUD_WIDTH,
            self.store.config.display_height or HUD_HEIGHT,
        )
        self.playwright_capture = PlaywrightHudCapture()
        self.device_status = DeviceStatus()
        self.device_ws: Optional[WebSocket] = None
        self.ui_clients: set[WebSocket] = set()
        self.frame_seq: int = 0
        self.plugin_reload_token: int = 1
        self.latest_preview_png: bytes = b""
        self.latest_preview_data_url: str = ""
        self.latest_layout: LayoutEvaluationResult = self.layout_engine.evaluate(self.store.config)
        self.ws_logs: deque[dict[str, Any]] = deque(maxlen=MAX_WS_LOG_ENTRIES)
        self._last_layout_signature: tuple[str, tuple[Optional[str], ...], str] = (
            self.latest_layout.active_layout,
            tuple(self.latest_layout.slots),
            self.latest_layout.reason,
        )
        self._lock = asyncio.Lock()
        self._ws_send_lock = asyncio.Lock()
        self.add_log("system", "server_init", "HRZN-LINK coordinator initialized")
        self.refresh_preview_cache()

    def add_log(
        self,
        source: str,
        event: str,
        detail: str,
        level: str = "info",
    ) -> None:
        """Append a structured entry to the bounded WebSocket/runtime event log."""
        self.ws_logs.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "source": source,
                "event": event,
                "detail": detail,
                "level": level,
            }
        )

    def refresh_layout(self) -> LayoutEvaluationResult:
        """Re-evaluate the layout engine against the current configuration."""
        result = self.layout_engine.evaluate(self.store.config)
        signature = (result.active_layout, tuple(result.slots), result.reason)
        if signature != self._last_layout_signature:
            self._last_layout_signature = signature
            self.add_log("layout", result.mode, result.reason)
        self.latest_layout = result
        return result

    def refresh_preview_cache(self) -> None:
        """Render the latest un-mirrored fallback frame and cache its PNG bytes/data URL."""
        layout_eval = self.refresh_layout()
        img = self.renderer.render_unmirrored(self.store.config, self.device_status, layout_eval)
        self.latest_preview_png = self.renderer.encode_png_bytes(img)
        self.latest_preview_data_url = self.renderer.encode_png_data_url(img)

    async def update_preview_frame(self):
        """Capture `/hud-render` via Playwright (with Pillow fallback) and update cached preview."""
        cfg = self.store.config
        layout_eval = self.refresh_layout()
        render_state = {
            "config": cfg.model_dump(),
            "device": self.device_status.model_dump(),
            "layout": layout_eval.model_dump(),
            "plugins": get_plugin_manifests(),
            "plugin_reload_token": self.plugin_reload_token,
        }
        captured = await self.playwright_capture.capture_frame(
            width=cfg.display_width,
            height=cfg.display_height,
            state_payload=render_state,
        )
        unmirrored = (
            captured
            if captured is not None
            else self.renderer.render_unmirrored(cfg, self.device_status, layout_eval)
        )
        self.latest_preview_png = self.renderer.encode_png_bytes(unmirrored)
        self.latest_preview_data_url = self.renderer.encode_png_data_url(unmirrored)
        return unmirrored

    def build_ui_snapshot(self, include_preview: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "state_update",
            "config": self.store.config.model_dump(),
            "device": self.device_status.model_dump(),
            "layout": self.latest_layout.model_dump(),
            "plugins": get_plugin_manifests(),
            "plugin_reload_token": self.plugin_reload_token,
            "renderer_mode": "playwright" if self.playwright_capture.is_ready else "pillow-fallback",
            "logs": list(self.ws_logs),
        }
        if include_preview:
            payload["preview_data_url"] = self.latest_preview_data_url
        return payload

    async def send_device_json(self, message: dict[str, Any]) -> bool:
        ws = self.device_ws
        if ws is None:
            return False
        try:
            async with self._ws_send_lock:
                if self.device_ws is not ws:
                    return False
                await ws.send_text(json.dumps(message))
            self.add_log("device_tx", str(message.get("type", "cmd")), json.dumps(message))
            return True
        except Exception as exc:
            self.add_log("device_tx", "send_error", str(exc), level="error")
            if self.device_ws is ws:
                self.device_ws = None
                self.device_status.connected = False
            return False

    async def broadcast_ui(self, include_preview: bool = True) -> None:
        if not self.ui_clients:
            return
        payload = json.dumps(self.build_ui_snapshot(include_preview=include_preview))
        stale: list[WebSocket] = []
        for client in list(self.ui_clients):
            try:
                await client.send_text(payload)
            except Exception:
                stale.append(client)
        for client in stale:
            self.ui_clients.discard(client)

    async def apply_flap(self, cmd: FlapCommand) -> dict[str, Any]:
        if cmd.state == "open":
            target_pct = 100
        elif cmd.state == "closed":
            target_pct = 0
        else:
            target_pct = (
                cmd.position_pct
                if cmd.position_pct is not None
                else self.store.config.target_angle_pct
            )

        patch = HrznConfigPatch(flap_state=cmd.state, target_angle_pct=target_pct)
        self.store.update(patch)
        self.refresh_layout()

        ws_cmd: dict[str, Any] = {
            "type": "flap_move",
            "state": cmd.state,
            "position_pct": target_pct,
        }
        if cmd.duration_ms is not None and cmd.duration_ms > 0:
            ws_cmd["duration_ms"] = cmd.duration_ms

        self.add_log("ui", "flap_move", f"state={cmd.state} target={target_pct}%")
        await self.send_device_json(ws_cmd)
        await self.broadcast_ui()
        return self.build_ui_snapshot(include_preview=False)

    async def apply_brightness(self, cmd: BrightnessCommand) -> dict[str, Any]:
        self.store.update(HrznConfigPatch(brightness=cmd.brightness))
        self.refresh_layout()
        self.add_log("ui", "set_brightness", f"brightness={cmd.brightness}/255")
        await self.send_device_json({"type": "set_brightness", "brightness": cmd.brightness})
        await self.broadcast_ui()
        return self.build_ui_snapshot(include_preview=False)

    async def apply_config_patch(self, patch: HrznConfigPatch) -> dict[str, Any]:
        prev = self.store.config
        updated = self.store.update(patch)
        self.refresh_layout()

        if (
            updated.servo_closed_us != prev.servo_closed_us
            or updated.servo_open_us != prev.servo_open_us
            or updated.sweep_duration_ms != prev.sweep_duration_ms
            or updated.settle_detach_ms != prev.settle_detach_ms
        ):
            await self.send_device_json(updated.to_servo_limits_payload())

        if updated.brightness != prev.brightness:
            await self.send_device_json(
                {"type": "set_brightness", "brightness": updated.brightness}
            )

        if (
            updated.flap_state != prev.flap_state
            or updated.target_angle_pct != prev.target_angle_pct
        ):
            await self.send_device_json(
                {
                    "type": "flap_move",
                    "state": updated.flap_state,
                    "position_pct": updated.target_angle_pct,
                }
            )

        if (
            updated.mirror_vertical != prev.mirror_vertical
            or updated.frame_format != prev.frame_format
            or updated.display_width != prev.display_width
            or updated.display_height != prev.display_height
        ):
            self.renderer.reset_diff_state()

        changed_keys = list(patch.model_dump(exclude_none=True).keys())
        self.add_log("ui", "update_config", f"updated {', '.join(changed_keys) or 'config'}")
        await self.update_preview_frame()
        await self.broadcast_ui()
        return self.build_ui_snapshot(include_preview=False)

    async def apply_plugin_settings(
        self,
        plugin_id: str,
        settings_patch: dict[str, Any],
    ) -> dict[str, Any]:
        provider = get_plugin_provider(plugin_id)
        if provider is None:
            raise HTTPException(status_code=404, detail=f"Unknown plugin: {plugin_id}")

        self.store.update_plugin_settings(plugin_id, settings_patch)
        self.refresh_layout()
        self.add_log(
            "ui",
            "plugin_settings",
            f"plugin={plugin_id} keys={','.join(settings_patch.keys())}",
        )
        await self.update_preview_frame()
        await self.broadcast_ui()
        return self.build_ui_snapshot(include_preview=False)

    async def reload_all_plugins(self) -> dict[str, Any]:
        """Rescan the top-level plugins directory, seed defaults, and broadcast updates."""
        discovered = reload_plugins()
        self.store.config.plugin_configs = merge_plugin_configs(self.store.config.plugin_configs)
        self.store.save()
        self.plugin_reload_token += 1
        self.refresh_layout()
        self.renderer.reset_diff_state()
        self.add_log(
            "plugins",
            "plugins_reloaded",
            f"discovered={','.join(discovered.keys())} token={self.plugin_reload_token}",
        )
        await self.update_preview_frame()
        await self.broadcast_ui()
        return self.build_ui_snapshot(include_preview=False)


state = LinkState()


async def frame_stream_loop() -> None:
    """Capture `/hud-render` via Playwright, flip in NumPy, and stream changed strips to HRZN-01."""
    while True:
        cfg = state.store.config
        interval = 1.0 / max(0.5, cfg.target_fps)
        try:
            unmirrored = await state.update_preview_frame()

            ws = state.device_ws
            if ws is not None:
                packets = state.renderer.build_frame_packets(
                    unmirrored=unmirrored,
                    seq=state.frame_seq,
                    fmt=cfg.frame_format,
                    mirror_vertical=cfg.mirror_vertical,
                )
                if packets:
                    state.frame_seq = (state.frame_seq + 1) & 0xFF
                    try:
                        async with state._ws_send_lock:
                            if state.device_ws is ws:
                                for packet in packets:
                                    await ws.send_bytes(packet)
                    except Exception:
                        if state.device_ws is ws:
                            state.device_ws = None
                            state.device_status.connected = False

            if state.ui_clients:
                await state.broadcast_ui(include_preview=True)
        except Exception as exc:
            print(f"[STREAM] Frame loop error: {exc}")

        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(frame_stream_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await state.playwright_capture.stop()


app = FastAPI(
    title="STANCE // HRZN-LINK",
    version="0.2.0",
    description="STANCE Labs HRZN-01 modular HUD grid, layout engine, and WebSocket streamer.",
    lifespan=lifespan,
)


# ----------------------------------------------------------------------------
# REST Endpoints
# ----------------------------------------------------------------------------
@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "stance-hrzn-link",
        "hw_target": "HRZN-01",
        "device_connected": state.device_status.connected,
        "renderer_mode": "playwright" if state.playwright_capture.is_ready else "pillow-fallback",
    }


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    state.refresh_layout()
    return state.build_ui_snapshot(include_preview=False)


@app.get("/api/plugins")
async def get_plugins() -> dict[str, Any]:
    layout_eval = state.refresh_layout()
    return {
        "plugins": get_plugin_manifests(),
        "plugin_reload_token": state.plugin_reload_token,
        "layout": layout_eval.model_dump(),
    }


@app.post("/api/plugins/reload")
async def reload_plugins_endpoint() -> dict[str, Any]:
    return await state.reload_all_plugins()


@app.get("/plugins-raw/{plugin_id}/{file_path:path}")
async def serve_plugin_raw_file(plugin_id: str, file_path: str) -> FileResponse:
    target = resolve_plugin_file(plugin_id, file_path)
    if target is None:
        raise HTTPException(status_code=404, detail="Plugin asset not found")
    return FileResponse(target, headers={"Cache-Control": "no-store"})


@app.post("/api/plugins/{plugin_id}/settings")
async def update_plugin_settings(
    plugin_id: str,
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    settings_patch = payload.get("settings") if isinstance(payload.get("settings"), dict) else payload
    if not isinstance(settings_patch, dict):
        raise HTTPException(status_code=422, detail="Settings payload must be a JSON object")
    return await state.apply_plugin_settings(plugin_id, settings_patch)


@app.post("/api/config")
async def update_config(patch: HrznConfigPatch) -> dict[str, Any]:
    return await state.apply_config_patch(patch)


@app.post("/api/flap")
async def move_flap(cmd: FlapCommand) -> dict[str, Any]:
    return await state.apply_flap(cmd)


@app.post("/api/brightness")
async def set_brightness(cmd: BrightnessCommand) -> dict[str, Any]:
    return await state.apply_brightness(cmd)


@app.get("/api/preview.png")
async def get_preview_png() -> Response:
    return Response(
        content=state.latest_preview_png,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


# ----------------------------------------------------------------------------
# WebSocket: ESP32-S3 HRZN-01 Device Endpoint (/ws/device)
# ----------------------------------------------------------------------------
@app.websocket("/ws/device")
async def device_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    state.add_log("device_ws", "connect", "Incoming connection on /ws/device")
    async with state._lock:
        if state.device_ws is not None:
            with suppress(Exception):
                await state.device_ws.close()
            state.device_ws = None
            state.device_status.connected = False

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")
            state.device_status.last_seen = datetime.now(timezone.utc).isoformat()

            if msg_type == "device_hello":
                disp = msg.get("display") or {}
                state.device_status.device_id = msg.get("device_id")
                state.device_status.hw_version = msg.get("hw_version", "HRZN-01")
                state.device_status.fw_version = msg.get("fw_version")
                state.device_status.display_width = int(disp.get("width", HUD_WIDTH))
                state.device_status.display_height = int(disp.get("height", HUD_HEIGHT))

                sync_payload = state.store.config.to_config_sync_payload()
                async with state._ws_send_lock:
                    await websocket.send_text(json.dumps(sync_payload))
                state.renderer.reset_diff_state()
                async with state._lock:
                    state.device_ws = websocket
                    state.device_status.connected = True
                state.add_log(
                    "device_rx",
                    "device_hello",
                    f"{state.device_status.device_id or 'HRZN-01'} "
                    f"({state.device_status.display_width}x{state.device_status.display_height}) -> config_sync sent",
                )
                await state.broadcast_ui()

            elif msg_type == "telemetry_report":
                state.device_status.uptime_s = int(msg.get("uptime_s", 0))
                state.device_status.rssi_dbm = msg.get("rssi_dbm")
                state.device_status.free_heap = msg.get("free_heap")
                state.device_status.flap_position_pct = int(
                    msg.get("flap_position_pct", state.device_status.flap_position_pct)
                )
                state.device_status.servo_us = int(
                    msg.get("servo_us", state.device_status.servo_us)
                )
                state.device_status.servo_attached = bool(msg.get("servo_attached", False))
                state.device_status.brightness = int(
                    msg.get("brightness", state.device_status.brightness)
                )
                state.device_status.fps = float(msg.get("fps", 0.0))
                state.add_log(
                    "device_rx",
                    "telemetry_report",
                    f"rssi={state.device_status.rssi_dbm}dBm "
                    f"flap={state.device_status.flap_position_pct}% "
                    f"fps={state.device_status.fps:.1f}",
                )
                await state.broadcast_ui(include_preview=False)
    except WebSocketDisconnect:
        pass
    finally:
        if state.device_ws is websocket:
            state.device_ws = None
            state.device_status.connected = False
            state.add_log("device_ws", "disconnect", "HRZN-01 disconnected", level="warn")
            await state.broadcast_ui()


# ----------------------------------------------------------------------------
# WebSocket: Vue 3 Companion Dashboard Endpoint (/ws/ui)
# ----------------------------------------------------------------------------
@app.websocket("/ws/ui")
async def ui_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    state.ui_clients.add(websocket)
    state.add_log("ui_ws", "connect", f"UI client connected (total={len(state.ui_clients)})")
    await websocket.send_text(json.dumps(state.build_ui_snapshot(include_preview=True)))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")
            if msg_type == "flap_move":
                await state.apply_flap(FlapCommand.model_validate(msg))
            elif msg_type == "set_brightness":
                await state.apply_brightness(BrightnessCommand.model_validate(msg))
            elif msg_type == "update_config":
                patch_data = msg.get("config", msg)
                await state.apply_config_patch(HrznConfigPatch.model_validate(patch_data))
            elif msg_type == "update_plugin_settings":
                plugin_id = str(msg.get("plugin_id", ""))
                settings_patch = msg.get("settings")
                if plugin_id and isinstance(settings_patch, dict):
                    await state.apply_plugin_settings(plugin_id, settings_patch)
    except WebSocketDisconnect:
        pass
    finally:
        state.ui_clients.discard(websocket)
        state.add_log("ui_ws", "disconnect", f"UI client disconnected (total={len(state.ui_clients)})")


# ----------------------------------------------------------------------------
# Single-Port Static Frontend Serving (`web/dist/`)
# ----------------------------------------------------------------------------
if (WEB_DIST_DIR / "assets").is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(WEB_DIST_DIR / "assets")),
        name="web-assets",
    )


@app.get("/{full_path:path}")
async def serve_spa(full_path: str) -> FileResponse:
    if (
        full_path.startswith("api/")
        or full_path.startswith("ws/")
        or full_path.startswith("plugins-raw/")
    ):
        raise HTTPException(status_code=404, detail="Not found")

    index_file = WEB_DIST_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(
            status_code=404,
            detail="Frontend not built yet. Run `cd web && npm install && npm run build`.",
        )

    candidate = (WEB_DIST_DIR / full_path).resolve()
    if full_path and candidate.is_file() and candidate.is_relative_to(WEB_DIST_DIR.resolve()):
        return FileResponse(candidate)

    return FileResponse(index_file)
