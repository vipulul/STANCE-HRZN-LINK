"""Dynamic runtime auto-discovery registry for top-level `plugins/` packages."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from server.plugins.base import HudPluginProvider, ManifestPluginProvider

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def resolve_plugins_dir(plugins_dir: Optional[Path] = None) -> Path:
    """Resolve the top-level plugins folder path."""
    if plugins_dir is not None:
        return plugins_dir
    env_dir = os.getenv("HRZN_PLUGINS_DIR")
    return Path(env_dir) if env_dir else (REPO_ROOT / "plugins")


def _load_provider_from_file(provider_path: Path, plugin_key: str) -> Optional[HudPluginProvider]:
    importlib.invalidate_caches()
    module_name = f"hrzn_external_plugin_{plugin_key}"
    sys.modules.pop(module_name, None)

    spec = importlib.util.spec_from_file_location(module_name, provider_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    explicit = getattr(module, "Provider", None)
    if (
        isinstance(explicit, type)
        and issubclass(explicit, HudPluginProvider)
        and explicit is not HudPluginProvider
        and explicit is not ManifestPluginProvider
    ):
        return explicit()

    for attr in vars(module).values():
        if (
            isinstance(attr, type)
            and issubclass(attr, HudPluginProvider)
            and attr is not HudPluginProvider
            and attr is not ManifestPluginProvider
            and attr.__module__ == module.__name__
        ):
            return attr()
    return None


def discover_plugins(plugins_dir: Optional[Path] = None) -> dict[str, HudPluginProvider]:
    """Scan `<REPO_ROOT>/plugins/*/plugin.json` and instantiate providers."""
    root = resolve_plugins_dir(plugins_dir)
    if not root.is_dir():
        return {}

    candidates = [
        d for d in root.iterdir()
        if d.is_dir() and not d.name.startswith(".") and (d / "plugin.json").is_file()
    ]
    # Keep `clock` first as the base reference plugin, then alphabetical.
    candidates.sort(key=lambda d: (0 if d.name == "clock" else 1, d.name.lower()))

    registry: dict[str, HudPluginProvider] = {}
    for plugin_dir in candidates:
        manifest_path = plugin_dir / "plugin.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[PLUGINS] Failed to parse {manifest_path}: {exc}")
            continue

        plugin_id = str(manifest.get("id") or plugin_dir.name).strip()
        if not plugin_id:
            continue

        name = str(manifest.get("name") or plugin_id)
        description = str(manifest.get("description") or "")
        version = str(manifest.get("version") or "1.0.0")
        raw_priority = manifest.get("basePriority", manifest.get("base_priority", 1))
        base_priority = int(raw_priority)
        raw_defaults = manifest.get("defaultSettings", manifest.get("default_settings"))
        default_settings = dict(raw_defaults) if isinstance(raw_defaults, dict) else {}

        has_widget = (plugin_dir / "Widget.vue").is_file()
        has_settings = (plugin_dir / "Settings.vue").is_file()

        provider_path = plugin_dir / "provider.py"
        provider: Optional[HudPluginProvider] = None
        if provider_path.is_file():
            try:
                provider = _load_provider_from_file(provider_path, plugin_id)
            except Exception as exc:
                print(f"[PLUGINS] Failed to load provider {provider_path}: {exc}")

        if provider is None:
            provider = ManifestPluginProvider(
                plugin_id=plugin_id,
                name=name,
                description=description,
                version=version,
                base_priority=base_priority,
                default_settings=default_settings,
                has_widget=has_widget,
                has_settings=has_settings,
                folder_name=plugin_dir.name,
            )
        else:
            provider.id = plugin_id
            provider.name = name
            provider.description = description
            provider.version = version
            provider.base_priority = base_priority
            provider.has_widget = has_widget
            provider.has_settings = has_settings
            provider.folder_name = plugin_dir.name
            if default_settings:
                provider.default_settings = {
                    **dict(provider.default_settings),
                    **default_settings,
                }

        registry[plugin_id] = provider

    return registry


PLUGIN_REGISTRY: dict[str, HudPluginProvider] = discover_plugins()


def reload_plugins(plugins_dir: Optional[Path] = None) -> dict[str, HudPluginProvider]:
    """Re-scan the plugins directory and refresh `PLUGIN_REGISTRY` in place."""
    fresh = discover_plugins(plugins_dir)
    PLUGIN_REGISTRY.clear()
    PLUGIN_REGISTRY.update(fresh)
    return PLUGIN_REGISTRY


def resolve_plugin_file(
    plugin_id: str,
    file_path: str,
    plugins_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Safely resolve a file inside a discovered plugin's directory."""
    plugins_root = resolve_plugins_dir(plugins_dir).resolve()
    provider = PLUGIN_REGISTRY.get(plugin_id)
    folder = provider.folder_name if (provider and provider.folder_name) else plugin_id
    candidate = (plugins_root / folder / file_path).resolve()
    if candidate.is_file() and candidate.is_relative_to(plugins_root):
        return candidate
    return None


def get_plugin_provider(plugin_id: str) -> Optional[HudPluginProvider]:
    """Look up a registered plugin provider by ID."""
    return PLUGIN_REGISTRY.get(plugin_id)


def get_plugin_manifests() -> list[dict[str, Any]]:
    """Return serializable manifests for all registered plugins."""
    return [provider.to_manifest() for provider in PLUGIN_REGISTRY.values()]


def get_default_plugin_configs() -> dict[str, dict[str, Any]]:
    """Return a fresh mapping of default settings per registered plugin."""
    return {
        plugin_id: dict(provider.default_settings)
        for plugin_id, provider in PLUGIN_REGISTRY.items()
    }


def merge_plugin_configs(
    saved: Optional[dict[str, dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """Merge saved per-plugin settings with registered plugin defaults."""
    merged = get_default_plugin_configs()
    if not saved:
        return merged
    for plugin_id, overrides in saved.items():
        if not isinstance(overrides, dict):
            continue
        base = merged.get(plugin_id, {})
        merged[plugin_id] = {**base, **overrides}
    return merged
