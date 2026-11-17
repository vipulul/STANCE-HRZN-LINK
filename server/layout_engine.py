"""Dynamic and manual HUD layout rule/priority evaluator."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional

from pydantic import BaseModel

from server.config_store import GridLayoutId, HrznConfig, LayoutMode
from server.plugins.base import HudPluginProvider, PluginRuntimeStatus
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
    """Evaluates registered plugin priorities and time-of-day rules to select a HUD grid."""

    def __init__(self, registry: Optional[Mapping[str, HudPluginProvider]] = None) -> None:
        self._registry = registry if registry is not None else PLUGIN_REGISTRY

    def evaluate(
        self,
        config: HrznConfig,
        now: Optional[datetime] = None,
    ) -> LayoutEvaluationResult:
        current = now or datetime.now()
        merged_settings = merge_plugin_configs(config.plugin_configs)

        statuses: list[PluginRuntimeStatus] = []
        effective_settings: dict[str, dict[str, Any]] = {}
        plugin_data: dict[str, dict[str, Any]] = {}

        for reg_idx, (plugin_id, provider) in enumerate(self._registry.items()):
            base_settings = provider.merge_settings(merged_settings.get(plugin_id))
            status = provider.evaluate(base_settings, now=current)
            statuses.append(status)
            effective_settings[plugin_id] = {
                **base_settings,
                **status.settings_override,
            }
            plugin_data[plugin_id] = dict(status.data)
            # Attach registration order index stably via tuple sorting below
            _ = reg_idx

        active_indexed = [
            (idx, status) for idx, status in enumerate(statuses) if status.active
        ]
        # Higher priority first; tie-broken by registration order ascending.
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
