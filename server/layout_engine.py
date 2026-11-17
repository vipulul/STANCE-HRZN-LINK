"""Centralized Dynamic and Manual HUD layout rule/priority evaluator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from pydantic import BaseModel

from server.config_store import GridLayoutId, HrznConfig, LayoutMode
from server.plugins.base import HudPluginProvider, PluginDynamicMode, PluginRuntimeStatus
from server.plugins.registry import PLUGIN_REGISTRY, merge_plugin_configs

SLOT_COUNTS: dict[GridLayoutId, int] = {
    "1x1": 1,
    "2x1": 2,
    "1x2": 2,
    "2-big-1-small": 3,
    "3x1": 3,
    "2x2": 4,
    "4x1": 4,
}


def _is_hour_in_window(hour: int, start_hour: int, end_hour: int) -> bool:
    """Return True if `hour` falls inside `[start_hour, end_hour)` with overnight wraparound."""
    if start_hour == end_hour:
        return False
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def _to_utc(dt: datetime) -> datetime:
    """Normalize a naive or timezone-aware datetime to UTC."""
    if dt.tzinfo is None:
        return dt.astimezone().astimezone(timezone.utc)
    return dt.astimezone(timezone.utc)


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class LayoutEvaluationResult(BaseModel):
    """Resolved grid layout, slot assignments, and per-plugin live runtime payloads."""

    mode: LayoutMode
    active_layout: GridLayoutId
    slot_count: int
    slots: list[Optional[str]]
    reason: str
    night_schedule_active: bool = False
    effective_plugin_settings: dict[str, dict[str, Any]]
    plugin_data: dict[str, dict[str, Any]]
    plugin_statuses: list[PluginRuntimeStatus]


class LayoutEngine:
    """Centralized evaluator for plugin dynamicMode, userPriority, and event hold cooldown."""

    def __init__(self, registry: Optional[Mapping[str, HudPluginProvider]] = None) -> None:
        self._registry = registry if registry is not None else PLUGIN_REGISTRY
        self._last_triggered_at: dict[str, datetime] = {}
        self._test_triggered_at: dict[str, datetime] = {}

    def trigger_test_event(self, plugin_id: str, now: Optional[datetime] = None) -> None:
        """Simulate an event trigger for `plugin_id` so it holds open for `event_hold_seconds`."""
        ts = _to_utc(now) if now is not None else datetime.now(timezone.utc)
        self._last_triggered_at[plugin_id] = ts
        self._test_triggered_at[plugin_id] = ts

    def evaluate(
        self,
        config: HrznConfig,
        now: Optional[datetime] = None,
    ) -> LayoutEvaluationResult:
        current = now or datetime.now()
        now_utc = _to_utc(current)
        hold_s = float(config.dynamic_rules.event_hold_seconds)
        merged_settings = merge_plugin_configs(config.plugin_configs)

        statuses: list[PluginRuntimeStatus] = []
        effective_settings: dict[str, dict[str, Any]] = {}
        plugin_data: dict[str, dict[str, Any]] = {}

        for reg_idx, (plugin_id, provider) in enumerate(self._registry.items()):
            _ = reg_idx
            base_settings = provider.merge_settings(merged_settings.get(plugin_id))

            raw_mode = str(
                base_settings.get("dynamicMode") or provider.default_dynamic_mode or "always"
            ).strip().lower()
            dynamic_mode: PluginDynamicMode = (
                raw_mode if raw_mode in ("always", "on_event", "off") else "always"  # type: ignore[assignment]
            )
            user_priority = max(
                1,
                min(100, _coerce_int(base_settings.get("userPriority"), provider.base_priority)),
            )
            base_settings["dynamicMode"] = dynamic_mode
            base_settings["userPriority"] = user_priority

            raw_status = provider.evaluate(base_settings, now=current)
            raw_triggered = bool(raw_status.event_triggered)

            if raw_triggered and dynamic_mode != "off":
                self._last_triggered_at[plugin_id] = now_utc

            last_ts = self._last_triggered_at.get(plugin_id)
            elapsed_s = (now_utc - last_ts).total_seconds() if last_ts is not None else float("inf")
            within_hold = 0.0 <= elapsed_s < hold_s
            hold_remaining_s = round(max(0.0, hold_s - elapsed_s), 1) if within_hold else 0.0

            test_ts = self._test_triggered_at.get(plugin_id)
            in_test_hold = (
                test_ts is not None and 0.0 <= (now_utc - test_ts).total_seconds() < hold_s
            )

            if dynamic_mode == "off":
                self._last_triggered_at.pop(plugin_id, None)
                self._test_triggered_at.pop(plugin_id, None)
                is_active = False
                effective_priority = user_priority
                holding_event = False
                hold_remaining_s = 0.0
                reason = "Off in Dynamic Mode"
            elif dynamic_mode == "always":
                is_active = True
                effective_priority = user_priority
                holding_event = False
                hold_remaining_s = 0.0
                base_reason = raw_status.reason or "Always active"
                reason = f"{base_reason} (P{user_priority})"
            else:
                if raw_triggered or within_hold:
                    is_active = True
                    effective_priority = user_priority
                    holding_event = not raw_triggered
                    if raw_triggered:
                        event_detail = raw_status.reason or "Triggered"
                        reason = f"Event Active: {event_detail} (P{user_priority})"
                    else:
                        label = "Test Event Hold" if in_test_hold else "Event Hold"
                        reason = f"{label} ({hold_remaining_s:.0f}s left) · P{user_priority}"
                else:
                    is_active = False
                    effective_priority = user_priority
                    holding_event = False
                    hold_remaining_s = 0.0
                    reason = f"On Event standby (P{user_priority})"

            normalized = PluginRuntimeStatus(
                id=plugin_id,
                name=raw_status.name or provider.name or plugin_id,
                active=is_active,
                priority=effective_priority,
                dynamic_mode=dynamic_mode,
                user_priority=user_priority,
                event_triggered=raw_triggered,
                holding_event=holding_event,
                hold_remaining_s=hold_remaining_s,
                reason=reason,
                data=dict(raw_status.data),
                settings_override=dict(raw_status.settings_override),
            )
            statuses.append(normalized)
            effective_settings[plugin_id] = {
                **base_settings,
                **normalized.settings_override,
            }
            plugin_data[plugin_id] = dict(normalized.data)

        active_indexed = [
            (idx, status) for idx, status in enumerate(statuses) if status.active
        ]
        # Higher userPriority first; tie-broken by registration order ascending.
        active_indexed.sort(key=lambda item: (-item[1].priority, item[0]))
        active_plugins = [status for _, status in active_indexed]

        if config.layout_mode == "manual":
            active_layout = config.manual_layout
            slot_count = SLOT_COUNTS[active_layout]
            active_slots = (list(config.grid_slots) + [None] * 4)[:slot_count]
            return LayoutEvaluationResult(
                mode="manual",
                active_layout=active_layout,
                slot_count=slot_count,
                slots=active_slots,
                reason=f"Manual Grid ({active_layout})",
                night_schedule_active=False,
                effective_plugin_settings=effective_settings,
                plugin_data=plugin_data,
                plugin_statuses=statuses,
            )

        rules = config.dynamic_rules
        if rules.night_mode_enabled and _is_hour_in_window(
            current.hour, rules.night_start_hour, rules.night_end_hour
        ):
            clock_id = "clock" if "clock" in self._registry else (
                active_plugins[0].id if active_plugins else None
            )
            if clock_id == "clock":
                effective_settings["clock"] = {
                    **effective_settings.get("clock", {}),
                    "stylePreset": rules.night_style_preset,
                }
            reason = (
                f"Night Minimal Schedule ({rules.night_start_hour:02d}:00-"
                f"{rules.night_end_hour:02d}:00) -> 1x1 [{rules.night_style_preset}]"
            )
            return LayoutEvaluationResult(
                mode="dynamic",
                active_layout="1x1",
                slot_count=1,
                slots=[clock_id],
                reason=reason,
                night_schedule_active=True,
                effective_plugin_settings=effective_settings,
                plugin_data=plugin_data,
                plugin_statuses=statuses,
            )

        n_active = len(active_plugins)
        if n_active <= 1:
            active_layout: GridLayoutId = "1x1"
        elif n_active == 2:
            active_layout = "2x1"
        elif n_active == 3:
            active_layout = "2-big-1-small"
        else:
            active_layout = "2x2"

        slot_count = SLOT_COUNTS[active_layout]
        selected = active_plugins[:slot_count]
        active_slots: list[Optional[str]] = [p.id for p in selected]
        while len(active_slots) < slot_count:
            active_slots.append(None)

        if selected:
            summary = ", ".join(f"{p.name} [P{p.priority}]" for p in selected)
            reason = (
                f"Auto-Layout: {n_active} active plugin"
                f"{'s' if n_active != 1 else ''} ({summary}) -> {active_layout}"
            )
        else:
            reason = f"Auto-Layout: 0 active plugins -> {active_layout}"

        return LayoutEvaluationResult(
            mode="dynamic",
            active_layout=active_layout,
            slot_count=slot_count,
            slots=active_slots,
            reason=reason,
            night_schedule_active=False,
            effective_plugin_settings=effective_settings,
            plugin_data=plugin_data,
            plugin_statuses=statuses,
        )
