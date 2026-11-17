"""Reference Clock plugin provider auto-discovered from `plugins/clock/`."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from server.plugins.base import HudPluginProvider, PluginRuntimeStatus


class ClockPluginProvider(HudPluginProvider):
    """Base-priority avionic clock data and status provider."""

    id = "clock"
    name = "Chronos Avionic Clock"
    description = (
        "High-contrast cyberpunk/avionic HUD clock with adaptive radial arc gauge, "
        "date, and style presets."
    )
    base_priority = 10
    default_dynamic_mode = "always"
    default_settings: dict[str, Any] = {
        "dynamicMode": "always",
        "userPriority": 10,
        "format24h": True,
        "showSeconds": True,
        "showDate": True,
        "showArcRing": True,
        "accentColor": "#00f0ff",
        "stylePreset": "tactical",
    }

    def evaluate(
        self,
        settings: dict[str, Any],
        now: Optional[datetime] = None,
    ) -> PluginRuntimeStatus:
        current = now or datetime.now()
        merged = self.merge_settings(settings)

        seconds_in_day = current.hour * 3600 + current.minute * 60 + current.second
        day_progress_pct = round((seconds_in_day / 86400.0) * 100.0, 2)
        minute_progress_pct = round(
            ((current.second + current.microsecond / 1_000_000.0) / 60.0) * 100.0,
            2,
        )

        hour_12 = current.hour % 12 or 12
        return PluginRuntimeStatus(
            id=self.id,
            name=self.name,
            event_triggered=False,
            reason="Base HUD timekeeping",
            data={
                "iso": current.isoformat(),
                "time_24h": current.strftime("%H:%M:%S"),
                "time_12h": f"{hour_12:02d}:{current.minute:02d}:{current.second:02d}",
                "ampm": "PM" if current.hour >= 12 else "AM",
                "hours": current.hour if merged.get("format24h", True) else hour_12,
                "hours_24": current.hour,
                "hours_12": hour_12,
                "minutes": current.minute,
                "seconds": current.second,
                "date_display": current.strftime("%Y-%m-%d"),
                "weekday": current.strftime("%a").upper(),
                "day_progress_pct": day_progress_pct,
                "minute_progress_pct": minute_progress_pct,
            },
        )
