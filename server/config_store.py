"""Persistent configuration and live HRZN-01 device state models."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from server.plugins.registry import get_default_plugin_configs, merge_plugin_configs

GridLayoutId = Literal["1x1", "2x1", "1x2", "2x2", "2-big-1-small", "3x1", "4x1"]
LayoutMode = Literal["manual", "dynamic"]
ClockStylePreset = Literal["minimal", "tactical", "segmented"]

MAX_GRID_SLOTS = 4


def _normalize_slots(slots: Optional[list[Optional[str]]]) -> list[Optional[str]]:
    """Pad or truncate slot assignments to a fixed 4-slot tuple."""
    normalized = list(slots or ["clock"])[:MAX_GRID_SLOTS]
    while len(normalized) < MAX_GRID_SLOTS:
        normalized.append(None)
    return normalized


class DynamicRulesConfig(BaseModel):
    """Time-of-day and automatic rule parameters for Dynamic Mode."""

    night_mode_enabled: bool = True
    night_start_hour: int = Field(default=22, ge=0, le=23)
    night_end_hour: int = Field(default=7, ge=0, le=23)
    night_style_preset: ClockStylePreset = "minimal"
    event_hold_seconds: int = Field(default=12, ge=1, le=300)


class DynamicRulesPatch(BaseModel):
    """Partial update payload for Dynamic Mode rules."""

    night_mode_enabled: Optional[bool] = None
    night_start_hour: Optional[int] = Field(default=None, ge=0, le=23)
    night_end_hour: Optional[int] = Field(default=None, ge=0, le=23)
    night_style_preset: Optional[ClockStylePreset] = None
    event_hold_seconds: Optional[int] = Field(default=None, ge=1, le=300)


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

    # Display geometry & modular HUD grid architecture
    display_width: int = Field(default=480, ge=120, le=800)
    display_height: int = Field(default=320, ge=120, le=800)
    layout_mode: LayoutMode = "manual"
    manual_layout: GridLayoutId = "1x1"
    grid_slots: list[Optional[str]] = Field(default_factory=lambda: ["clock", None, None, None])
    plugin_configs: dict[str, dict[str, Any]] = Field(default_factory=get_default_plugin_configs)
    dynamic_rules: DynamicRulesConfig = Field(default_factory=DynamicRulesConfig)

    @field_validator("grid_slots", mode="before")
    @classmethod
    def _validate_grid_slots(cls, value: Any) -> list[Optional[str]]:
        if not isinstance(value, list):
            return ["clock", None, None, None]
        cleaned = [str(item) if isinstance(item, str) and item.strip() else None for item in value]
        return _normalize_slots(cleaned)

    @field_validator("plugin_configs", mode="before")
    @classmethod
    def _validate_plugin_configs(cls, value: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(value, dict):
            return get_default_plugin_configs()
        return merge_plugin_configs(value)

    def to_config_sync_payload(self) -> dict[str, Any]:
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

    def to_servo_limits_payload(self) -> dict[str, Any]:
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

    display_width: Optional[int] = Field(default=None, ge=120, le=800)
    display_height: Optional[int] = Field(default=None, ge=120, le=800)
    layout_mode: Optional[LayoutMode] = None
    manual_layout: Optional[GridLayoutId] = None
    grid_slots: Optional[list[Optional[str]]] = None
    plugin_configs: Optional[dict[str, dict[str, Any]]] = None
    dynamic_rules: Optional[DynamicRulesPatch] = None


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
                loaded = HrznConfig.model_validate(raw)
                loaded.plugin_configs = merge_plugin_configs(loaded.plugin_configs)
                loaded.grid_slots = _normalize_slots(loaded.grid_slots)
                return loaded
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

        if "plugin_configs" in updates:
            incoming_plugins = updates.pop("plugin_configs")
            merged_plugins = merge_plugin_configs(self.config.plugin_configs)
            for plugin_id, plugin_patch in incoming_plugins.items():
                if isinstance(plugin_patch, dict):
                    merged_plugins[plugin_id] = {
                        **merged_plugins.get(plugin_id, {}),
                        **plugin_patch,
                    }
            updates["plugin_configs"] = merged_plugins

        if "dynamic_rules" in updates:
            incoming_rules = updates.pop("dynamic_rules")
            merged_rules = {
                **self.config.dynamic_rules.model_dump(),
                **incoming_rules,
            }
            updates["dynamic_rules"] = DynamicRulesConfig.model_validate(merged_rules)

        if "grid_slots" in updates:
            updates["grid_slots"] = _normalize_slots(updates["grid_slots"])

        merged = self.config.model_copy(update=updates)
        if merged.flap_state == "open":
            merged.target_angle_pct = 100
        elif merged.flap_state == "closed":
            merged.target_angle_pct = 0
        self.config = merged
        self.save()
        return self.config

    def update_plugin_settings(self, plugin_id: str, settings_patch: dict[str, Any]) -> HrznConfig:
        """Merge and persist settings for a single plugin."""
        return self.update(HrznConfigPatch(plugin_configs={plugin_id: settings_patch}))
