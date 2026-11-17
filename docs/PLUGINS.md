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
  "defaultSettings": {
    "accentColor": "#00f0ff",
    "compact": false
  }
}
```

- `id`: Unique identifier matching the folder name and slot assignments.
- `basePriority`: Used by Dynamic Mode when ranking active plugins (`clock` uses `1`).
- `defaultSettings`: Seeded into `ConfigStore` (`data/config.json`) on startup and on `POST /api/plugins/reload`, and passed to both `Widget.vue` and `Settings.vue`.

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

To fetch live server data or dynamically toggle `active` / `priority` for Dynamic Mode, add `plugins/<plugin_id>/provider.py` subclassing `HudPluginProvider`:

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
        is_active = bool(settings.get("enabled", True))
        return PluginRuntimeStatus(
            id=self.id,
            name=self.name,
            active=is_active,
            priority=self.base_priority if is_active else 0,
            reason="Active telemetry condition met",
            data={"value": 42},
        )
```

Metadata (`id`, `name`, `description`, `version`, `base_priority`, `default_settings`) is automatically populated from `plugin.json` on startup and on `POST /api/plugins/reload`.

### Dynamic Mode Priority & Layout Rules (`server/layout_engine.py`)

1. **Time-of-Day Schedule:** When `night_mode_enabled` is true and the current hour falls inside `[night_start_hour, night_end_hour)`, Dynamic Mode forces `1x1` with `clock` and applies `night_style_preset`.
2. **Active Plugin Count & Priority:** Active plugins are sorted by `priority` descending and mapped to a grid template:
   - `0–1` active $\rightarrow$ `1x1`
   - `2` active $\rightarrow$ `2x1`
   - `3` active $\rightarrow$ `2-big-1-small`
   - `4+` active $\rightarrow$ `2x2`

---

## 4. Runtime Endpoints & Reference Plugin (`plugins/clock/`)

- `GET /api/plugins` — Lists discovered plugin manifests (`id`, `name`, `description`, `version`, `basePriority`, `defaultSettings`, `hasWidget`, `hasSettings`) and current layout evaluation.
- `POST /api/plugins/reload` — Rescans `./plugins/`, imports new providers, seeds new `defaultSettings`, and notifies all connected UIs + Playwright.
- `GET /plugins-raw/<id>/<file>` — Serves raw `.vue`, `.ts`, `.js`, and `.json` files directly from `./plugins/<id>/` with `Cache-Control: no-store`.

The built-in [`plugins/clock/`](../plugins/clock/plugin.json) package is the canonical reference plugin.
