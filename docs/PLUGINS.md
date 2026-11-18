# STANCE // HRZN-LINK — Modular HUD Plugin Guide

All HUD plugins live in a single top-level **`plugins/<plugin_id>/`** directory at the repository root and are **loaded dynamically at runtime**.

- **No Vite rebuild or Docker image rebuild** is required when adding, removing, or editing a plugin's `.vue` UI or `plugin.json` manifest—just refresh the browser or click **Reload Plugins** in HUD Studio (`POST /api/plugins/reload`).
- In Docker, `./plugins:/app/plugins` is volume-mounted into the container so host changes appear immediately. *(Restart the server/container only if modifying Python code inside an existing `provider.py`, or click **Reload Plugins** to load newly added `provider.py` modules.)*

---

## 1. Plugin Folder Structure

Create a folder `plugins/<plugin_id>/`:

```text
plugins/
└── <plugin_id>/
    ├── plugin.json     # Required: id, name, description, version, basePriority, defaultSettings
    ├── Widget.vue      # Required: container-responsive HUD display SFC (compiled at runtime)
    ├── Settings.vue    # Optional: settings drawer UI SFC (v-model, compiled at runtime)
    ├── provider.py     # Optional: backend live data & Dynamic Mode status provider
    └── types.ts        # Optional: local TypeScript interfaces shared by Widget & Settings
```

### `plugin.json` (Single Source of Truth)

```json
{
  "id": "my-plugin",
  "name": "My HUD Widget",
  "description": "Short summary shown in HUD Studio.",
  "version": "1.0.0",
  "basePriority": 5,
  "defaultDynamicMode": "on_event",
  "supportsOnEvent": true,
  "defaultSettings": {
    "accentColor": "#00f0ff",
    "triggerThreshold": 30,
    "compact": false
  }
}
```

- `id`: Unique identifier matching the folder name and slot assignments.
- `basePriority`: Default slot priority (`1–100`) used when seeding `userPriority` (`clock` defaults to `10`, `weather` to `8`, `telemetry` to `6`). Higher priority claims earlier slots (`Slot 0`, `Slot 1`, etc.).
- `defaultDynamicMode`: Default Dynamic Mode behavior (`"always" | "on_event" | "off"`). Defaults to `"always"` for manifest-only plugins unless specified (`"on_event"` for `weather` and `telemetry`).
- `supportsOnEvent`: Boolean indicating whether the plugin emits event triggers for Dynamic Mode. When omitted, defaults to `true` only if `defaultDynamicMode` is `"on_event"`, otherwise `false`. When `false` (for example `clock`), the **`On Event`** mode button is disabled/grayed out in HUD Studio and `LayoutEngine` coerces any `"on_event"` override to `"always"`.
- `defaultSettings`: Seeded into `ConfigStore` (`data/config.json`) along with universal `dynamicMode`, `userPriority`, and any plugin-specific **On-Event Trigger Condition** fields on startup and on `POST /api/plugins/reload`, and passed to both `Widget.vue` and `Settings.vue`.

---

## 2. Runtime `.vue` Components (`Widget.vue` & `Settings.vue`)

The frontend fetches `/plugins-raw/<id>/Widget.vue` (and `Settings.vue` when present) directly from FastAPI and compiles `<script setup>` (JS or TypeScript), `<template>`, and `<style scoped>` in-browser using `@vue/compiler-sfc` + `sucrase`.

### Supported Imports in Runtime SFCs
- `'vue'` (`computed`, `ref`, `watch`, `onMounted`, etc.)
- Relative imports inside your plugin directory (`./types`, `./helper.ts`, `./plugin.json`, `./SubComponent.vue`)
- *(Note: External npm packages or files outside `plugins/<id>/` are not available to runtime-loaded drop-in plugins.)*

### `Widget.vue` Props
Receives from `HudGridCanvas.vue`:
- `settings`: Merged settings object (`defaultSettings` + saved user overrides + Dynamic Mode overrides)
- `data`: Live JSON dictionary returned by `provider.py` (`layout.plugin_data[id]`)
- `slotIndex`: Zero-based slot index (`0..3`)
- `layout`: Active grid template (`'1x1' | '2x1' | '1x2' | '2x2' | '2-big-1-small' | '3x1' | '4x1'`)

### Container-Responsive CSS Guidelines

Every slot in `HudGridCanvas.vue` defines:

```css
container-type: size;
container-name: hud-slot;
```

Style your `Widget.vue` using `<style scoped>` CSS (rather than new custom Tailwind utilities not already compiled in the core UI) so styles apply immediately at runtime:

- Use **`#000000` pure black backgrounds** — black pixels appear transparent on the `HRZN-01` optical combiner film.
- Size typography and graphics using **`clamp()`** combined with **`cqw`**, **`cqh`**, and **`cqmin`** rather than fixed pixel sizes.
- Use **`@container hud-slot (...)`** queries to adapt from `1x1` (`480×320`) down to `4x1` (`~118×320`) or `2-big-1-small` compact slots (`~480×110`):
  - `@container hud-slot (max-width: 155px)` — narrow vertical strips (`3x1`, `4x1`)
  - `@container hud-slot (max-height: 135px)` — wide shallow slots (`1x2`, compact slot in `2-big-1-small`)
- Keep high contrast (`>= 7:1`) and avoid hover-only information in `Widget.vue`.

### `Settings.vue` (Optional)

Rendered inside the HUD Studio settings drawer. Accepts `modelValue` and emits `update:modelValue` (`v-model`), persisting updates through `POST /api/plugins/<id>/settings`.

---

## 3. Optional Backend Provider (`provider.py`)

If your plugin only displays client-side UI, omit `provider.py`—the server automatically creates a `ManifestPluginProvider` from `plugin.json`.

To fetch live server data or report event triggers for Dynamic Mode, add `plugins/<plugin_id>/provider.py` subclassing `HudPluginProvider`. Providers do **not** need to compute `userPriority`, `active`, or hold cooldowns—simply evaluate user-configured trigger settings from `settings` (exposed in `Settings.vue` and seeded via `defaultSettings`) to set `event_triggered` and `data`, and `LayoutEngine` applies the centralized `dynamicMode` / `userPriority` / `event_hold_seconds` pipeline uniformly across all plugins:

```python
from datetime import datetime
from typing import Any, Optional

from server.plugins.base import HudPluginProvider, PluginRuntimeStatus


class MyPluginProvider(HudPluginProvider):
    def evaluate(
        self,
        settings: dict[str, Any],
        now: Optional[datetime] = None,
    ) -> PluginRuntimeStatus:
        current_value = 42
        threshold = int(settings.get("triggerThreshold", 30))
        alert_active = bool(settings.get("enableAlert", True)) and current_value >= threshold
        return PluginRuntimeStatus(
            id=self.id,
            name=self.name,
            event_triggered=alert_active,
            reason=f"Value {current_value} >= {threshold}" if alert_active else "Nominal",
            data={"value": current_value, "alertReasons": ["Threshold"] if alert_active else []},
        )
```

Metadata (`id`, `name`, `description`, `version`, `base_priority`, `default_dynamic_mode`, `supports_on_event`, `default_settings`) is automatically populated from `plugin.json` on startup and on `POST /api/plugins/reload`. Set `"supportsOnEvent": true` in `plugin.json` whenever a provider supports `"on_event"` trigger conditions.

### Custom Plugin API Routes (`get_router()`)

If a plugin needs custom backend endpoints (e.g., for `Settings.vue` search/autocomplete or webhook actions) without modifying `server/main.py`, override `get_router(self) -> Optional[APIRouter]` on your `HudPluginProvider` subclass:

```python
from fastapi import APIRouter

class MyPluginProvider(HudPluginProvider):
    def get_router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/ping")
        async def ping():
            return {"ok": True}

        return router
```

Whenever plugins are loaded (at startup or via `POST /api/plugins/reload`), `server/plugins/registry.py` automatically mounts any returned `APIRouter` under `/api/plugins/<plugin_id>` with tag `plugin:<plugin_id>` (e.g., `/api/plugins/my-plugin/ping`).

### Centralized Dynamic Mode, Priority & Cooldown Rules (`server/layout_engine.py`)

Every plugin exposes two user-configurable fields (`dynamicMode` and `userPriority`), editable in HUD Studio's **Dynamic Mode & Priority** manager or in the plugin's **Settings** drawer:

- `dynamicMode`:
  - `"always"` — Always active in Dynamic Mode with effective priority `userPriority`.
  - `"on_event"` — Selectable only when `supportsOnEvent` is `true` (disabled/grayed out in HUD Studio when `false`, and coerced to `"always"` in `LayoutEngine`). Active only while `provider.evaluate()` reports `event_triggered=True` (based on the plugin's configured On-Event Trigger Conditions) **or** within `dynamic_rules.event_hold_seconds` (default `12s`) after `last_triggered_at` (including simulated triggers via `POST /api/plugins/<id>/test-event`).
  - `"off"` — Never surfaced in Dynamic Mode.
- `userPriority` (`1–100`) — Determines slot ordering when multiple plugins are active (higher priority claims earlier slots).

Layout resolution order:
1. **Time-of-Day Schedule:** When `night_mode_enabled` is true and the current hour falls inside `[night_start_hour, night_end_hour)`, Dynamic Mode forces `1x1` with `clock` and applies `night_style_preset`.
2. **Active Plugin Count & Priority:** Active plugins are sorted by `userPriority` descending and mapped to a grid template:
   - `0–1` active $\rightarrow$ `1x1`
   - `2` active $\rightarrow$ `2x1`
   - `3` active $\rightarrow$ `2-big-1-small`
   - `4+` active $\rightarrow$ `2x2`

---

## 4. Runtime Endpoints & Reference Plugins (`plugins/clock/`, `weather/`, `telemetry/`)

- `GET /api/plugins` — Lists discovered plugin manifests (`id`, `name`, `description`, `version`, `basePriority`, `defaultDynamicMode`, `supportsOnEvent`, `defaultSettings`, `hasWidget`, `hasSettings`) and current layout evaluation.
- `POST /api/plugins/reload` — Rescans `./plugins/`, imports new providers, seeds new `defaultSettings`, and notifies all connected UIs + Playwright.
- `POST /api/plugins/<id>/test-event` — Simulates an `event_triggered` pulse for `<id>` so it holds open for `event_hold_seconds` in Dynamic Mode.
- `GET /plugins-raw/<id>/<file>` — Serves raw `.vue`, `.ts`, `.js`, and `.json` files directly from `./plugins/<id>/` with `Cache-Control: no-store`.

### Built-In Reference Plugins & Configurable Event Triggers

- **[`plugins/clock/`](../plugins/clock/plugin.json)** (`supportsOnEvent: false`, `basePriority: 10`): Canonical display plugin supporting **`Always`** and **`Off`** modes (`On Event` is disabled in HUD Studio).
- **[`plugins/weather/`](../plugins/weather/plugin.json)** (`supportsOnEvent: true`, `basePriority: 8`, default `"on_event"`): Configurable weather trigger conditions in `Settings.vue` / `defaultSettings`:
  - Condition toggles: `triggerOnRain` (`true`), `triggerOnStorm` (`true`, Thunderstorm / Hail), `triggerOnSnow` (`true`), `triggerOnFog` (`false`), `triggerOnDrizzle` (`false`).
  - Threshold triggers: `triggerOnHighWind` (`true`) with `windThresholdKmh` (`30` km/h), and `triggerOnExtremeTemp` (`false`) with `tempLowThresholdC` (`0` °C) / `tempHighThresholdC` (`35` °C).
- **[`plugins/telemetry/`](../plugins/telemetry/plugin.json)** (`supportsOnEvent: true`, `basePriority: 6`, default `"on_event"`): Configurable hardware & link anomaly triggers in `Settings.vue` / `defaultSettings`:
  - Hardware & flap triggers: `triggerOnFlapMove` (`true`), `triggerOnFlapOpen` (`false`), `triggerOnDeviceDisconnect` (`false`).
  - Link & performance thresholds: `triggerOnWeakWifi` (`true`) with `rssiThresholdDbm` (`-75` dBm), `triggerOnHighLatency` (`false`) with `latencyThresholdMs` (`60` ms), and `triggerOnLowFps` (`false`) with `minFpsThreshold` (`1.5` FPS).
