"""Persistent configuration and live HRZN-01 device state models."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field


class HrznConfig(BaseModel):
    """Server-side persisted configuration synced to HRZN-01 on connect."""

    servo_closed_us: int = Field(default=1000, ge=500, le=2500)
    servo_open_us: int = Field(default=2000, ge=500, le=2500)
    sweep_duration_ms: int = Field(default=800, ge=100, le=5000)
    settle_detach_ms: int = Field(default=250, ge=50, le=2000)
    brightness: int = Field(default=200, ge=0, le=255)
    flap_state: Literal["open", "closed", "custom"] = "open"
    target_angle_pct: int = Field(default=100, ge=0, le=100)
    mirror_vertical: bool = True
    frame_format: Literal["RGB565", "JPEG"] = "RGB565"
    target_fps: float = Field(default=2.5, ge=0.5, le=15.0)
    hud_title: str = Field(default="STANCE // HRZN-01", max_length=32)
    hud_subtitle: str = Field(default="OPTICAL HUD LINK", max_length=40)

    def to_config_sync_payload(self) -> dict:
        """Return the JSON payload expected by HRZN-01 firmware."""
        return {
            "type": "config_sync",
            "servo_closed_us": self.servo_closed_us,
            "servo_open_us": self.servo_open_us,
            "sweep_duration_ms": self.sweep_duration_ms,
            "settle_detach_ms": self.settle_detach_ms,
            "brightness": self.brightness,
            "flap_state": self.flap_state,
            "target_angle_pct": self.target_angle_pct,
        }

    def to_servo_limits_payload(self) -> dict:
        """Return the `set_servo_limits` command payload."""
        return {
            "type": "set_servo_limits",
            "closed_us": self.servo_closed_us,
            "open_us": self.servo_open_us,
            "sweep_duration_ms": self.sweep_duration_ms,
            "settle_detach_ms": self.settle_detach_ms,
        }


class HrznConfigPatch(BaseModel):
    """Partial configuration update payload."""

    servo_closed_us: Optional[int] = Field(default=None, ge=500, le=2500)
    servo_open_us: Optional[int] = Field(default=None, ge=500, le=2500)
    sweep_duration_ms: Optional[int] = Field(default=None, ge=100, le=5000)
    settle_detach_ms: Optional[int] = Field(default=None, ge=50, le=2000)
    brightness: Optional[int] = Field(default=None, ge=0, le=255)
    flap_state: Optional[Literal["open", "closed", "custom"]] = None
    target_angle_pct: Optional[int] = Field(default=None, ge=0, le=100)
    mirror_vertical: Optional[bool] = None
    frame_format: Optional[Literal["RGB565", "JPEG"]] = None
    target_fps: Optional[float] = Field(default=None, ge=0.5, le=15.0)
    hud_title: Optional[str] = Field(default=None, max_length=32)
    hud_subtitle: Optional[str] = Field(default=None, max_length=40)


class FlapCommand(BaseModel):
    """Flap actuation command from REST or WebSocket UI."""

    state: Literal["open", "closed", "custom"]
    position_pct: Optional[int] = Field(default=None, ge=0, le=100)
    duration_ms: Optional[int] = Field(default=None, ge=0, le=5000)


class BrightnessCommand(BaseModel):
    """Backlight PWM update command."""

    brightness: int = Field(ge=0, le=255)


class DeviceStatus(BaseModel):
    """Live telemetry and connection status for HRZN-01."""

    connected: bool = False
    device_id: Optional[str] = None
    hw_version: str = "HRZN-01"
    fw_version: Optional[str] = None
    display_width: int = 480
    display_height: int = 320
    uptime_s: int = 0
    rssi_dbm: Optional[int] = None
    free_heap: Optional[int] = None
    flap_position_pct: int = 0
    servo_us: int = 1000
    servo_attached: bool = False
    brightness: int = 200
    fps: float = 0.0
    last_seen: Optional[str] = None


class ConfigStore:
    """Thread-safe JSON persistence for HRZN-01 calibration and HUD layout."""

    def __init__(self, data_dir: Optional[str] = None) -> None:
        resolved_dir = data_dir or os.getenv("HRZN_DATA_DIR", "./data")
        self._dir = Path(resolved_dir)
        self._path = self._dir / "config.json"
        self.config = self._load()

    def _load(self) -> HrznConfig:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                return HrznConfig.model_validate(raw)
            except Exception:
                # Fall back to safe defaults if config file is corrupted.
                return HrznConfig()
        return HrznConfig()

    def save(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_text(
            self.config.model_dump_json(indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(self._path)

    def update(self, patch: HrznConfigPatch) -> HrznConfig:
        updates = patch.model_dump(exclude_none=True)
        merged = self.config.model_copy(update=updates)
        if merged.flap_state == "open":
            merged.target_angle_pct = 100
        elif merged.flap_state == "closed":
            merged.target_angle_pct = 0
        self.config = merged
        self.save()
        return self.config
