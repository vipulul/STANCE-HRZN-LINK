"""Backend HUD plugin contract and runtime evaluation models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class PluginRuntimeStatus(BaseModel):
    """Runtime activation, priority, and live telemetry data for a HUD plugin."""

    id: str
    name: str
    active: bool = True
    priority: int = 1
    reason: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    settings_override: dict[str, Any] = Field(default_factory=dict)


class HudPluginProvider(ABC):
    """Base contract implemented by every backend HUD plugin provider."""

    id: str = ""
    name: str = ""
    description: str = ""
    base_priority: int = 1
    default_settings: dict[str, Any] = {}

    @abstractmethod
    def evaluate(
        self,
        settings: dict[str, Any],
        now: Optional[datetime] = None,
    ) -> PluginRuntimeStatus:
        """Evaluate current plugin state, priority, and live widget payload."""

    def merge_settings(self, saved: Optional[dict[str, Any]]) -> dict[str, Any]:
        """Merge persisted user settings onto this plugin's defaults."""
        merged = dict(self.default_settings)
        if saved:
            merged.update(saved)
        return merged

    def to_manifest(self) -> dict[str, Any]:
        """Serialize static metadata and default settings for API consumers."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "base_priority": self.base_priority,
            "default_settings": dict(self.default_settings),
        }


class ManifestPluginProvider(HudPluginProvider):
    """Default provider used for plugins that only ship a `plugin.json` without `provider.py`."""

    def __init__(
        self,
        plugin_id: str,
        name: str,
        description: str = "",
        base_priority: int = 1,
        default_settings: Optional[dict[str, Any]] = None,
    ) -> None:
        self.id = plugin_id
        self.name = name
        self.description = description
        self.base_priority = base_priority
        self.default_settings = dict(default_settings or {})

    def evaluate(
        self,
        settings: dict[str, Any],
        now: Optional[datetime] = None,
    ) -> PluginRuntimeStatus:
        _ = (settings, now)
        return PluginRuntimeStatus(
            id=self.id,
            name=self.name,
            active=True,
            priority=self.base_priority,
            reason=f"Manifest-only plugin (priority {self.base_priority})",
            data={},
        )
