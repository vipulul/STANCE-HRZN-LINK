# STANCE // HRZN-LINK — Modular HUD Plugin Guide

All HUD plugins live in a single top-level **`plugins/<plugin_id>/`** folder at the repository root. Both the Vue 3 frontend (via Vite `import.meta.glob`) and the FastAPI backend (via `server/plugins/registry.py`) **auto-discover** plugins from this directory—you never have to register files inside `web/` or `server/` manually.

---

## 1. Plugin Folder Structure

Create a folder `plugins/<plugin_id>/` containing:

```text
plugins/
└── <plugin_id>/
    ├── plugin.json     # Required: id, name, description, basePriority, defaultSettings
    ├── Widget.vue      # Required: container-responsive HUD display component
    ├── Settings.vue    # Optional: settings drawer UI (v-model)
    ├── provider.py     # Optional: backend live data & Dynamic Mode status provider
    └── types.ts        # Optional: local TypeScript interfaces
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
- `defaultSettings`: Automatically seeded into `ConfigStore` (`data/config.json`) and passed to both `Widget.vue` and `Settings.vue`.

---

## 2. Frontend Components (`Widget.vue` & `Settings.vue`)

### `Widget.vue`

Receives these props from `HudGridCanvas.vue`:
- `settings`: Merged settings object (`defaultSettings` + saved user overrides + Dynamic Mode overrides)
- `data`: Live JSON dictionary returned by `provider.py` (`layout.plugin_data[id]`)
- `slotIndex`: Zero-based slot index (`0..3`)
- `layout`: Active grid template (`'1x1' | '2x1' | '1x2' | '2x2' | '2-big-1-small' | '3x1' | '4x1'`)

#### Container-Responsive CSS Guidelines

Every slot in `HudGridCanvas.vue` defines:

```css
container-type: size;
container-name: hud-slot;
```

Follow these rules so your widget adapts smoothly from a full `1x1` screen (`480×320`) down to a narrow `4x1` strip (`~118×320`) or compact bottom slot (`~480×110`):

- Use **`#000000` pure black backgrounds** — black pixels appear transparent on the `HRZN-01` optical combiner film.
- Size typography and graphics using **`clamp()`** combined with **`cqw`**, **`cqh`**, and **`cqmin`** rather than fixed pixel sizes.
- Use **`@container hud-slot (...)`** queries to hide secondary ornaments or switch layout direction in constrained slots:
  - `@container hud-slot (max-width: 155px)` — narrow vertical strips (`3x1`, `4x1`)
  - `@container hud-slot (max-height: 135px)` — wide shallow slots (`1x2`, compact slot in `2-big-1-small`)
- Keep high contrast (`>= 7:1`) and avoid hover-only information in `Widget.vue`.

### `Settings.vue` (Optional)

Rendered inside the HUD Studio settings drawer. Accepts `modelValue` and emits `update:modelValue` (`v-model`), persisting updates through `POST /api/plugins/<id>/settings`:

```vue
<script setup lang="ts">
const props = defineProps<{ modelValue?: Record<string, unknown> }>()
const emit = defineEmits<{ (e: 'update:modelValue', val: Record<string, unknown>): void }>()
</script>
```

---

## 3. Optional Backend Provider (`provider.py`)

If your plugin only displays static/client-side UI, omit `provider.py`—the server automatically creates a `ManifestPluginProvider` from `plugin.json`.

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

Metadata (`id`, `name`, `description`, `base_priority`, `default_settings`) is automatically populated from `plugin.json` on startup.

### Dynamic Mode Priority & Layout Rules (`server/layout_engine.py`)

1. **Time-of-Day Schedule:** When `night_mode_enabled` is true and the current hour falls inside `[night_start_hour, night_end_hour)`, Dynamic Mode forces `1x1` with `clock` and applies `night_style_preset`.
2. **Active Plugin Count & Priority:** Active plugins are sorted by `priority` descending and mapped to a grid template:
   - `0–1` active $\rightarrow$ `1x1`
   - `2` active $\rightarrow$ `2x1`
   - `3` active $\rightarrow$ `2-big-1-small`
   - `4+` active $\rightarrow$ `2x2`

---

## 4. Reference Plugin (`plugins/clock/`)

The built-in [`plugins/clock/`](../plugins/clock/plugin.json) package is the canonical reference implementation:
- Base priority `1` (always active as the base timekeeping widget).
- Settings: `format24h`, `showSeconds`, `showDate`, `showArcRing`, `accentColor`, and `stylePreset` (`minimal`, `tactical`, `segmented`).
- Adapts its radial SVG arc ring, corner reticles, segmented bar, and date readout across all 7 grid layouts.
