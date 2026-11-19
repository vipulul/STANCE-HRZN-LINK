# STANCE // HRZN-LINK — HUD Plugin Visual, Spacing & Alignment Recommendations

This guide defines the **canonical spacing tokens, container breakpoints, header/footer geometry, contrast standards, and runtime SFC rules** for `plugins/<id>/Widget.vue` and `Settings.vue`.

Following these exact numbers keeps adjacent widgets aligned pixel-for-pixel across multi-slot grids (`2x2`, `2x1`, `2-big-1-small`, `1x2`, `3x1`, `4x1`) on the `HRZN-01` optical combiner.

---

## 1. Why Alignment Matters

When two plugins render side-by-side (for example `spotify` and `bambu` in a `2x2` quarter HUD or `2x1` split), users notice immediately if:
- Corner reticles have different corner insets or arm lengths.
- The top header title and `1px` horizontal divider sit at different Y-offsets.
- Bottom progress bars have different heights, borders, or bottom margins.
- Wide-shallow (`1x2` / `2-big-1-small` bottom) text truncates with `...` instead of using a horizontal 3-zone layout.

Use `plugins/spotify/Widget.vue` and `plugins/bambu/Widget.vue` as the visual reference implementations.

---

## 2. Exact Grid Slot Dimensions (`HudGridCanvas.vue`)

`HudGridCanvas.vue` renders slots inside a CSS grid with **`gap: 2px`**, where each `.hud-slot` declares `container-type: size; container-name: hud-slot;`:

| Layout | Slot Role | `480×320` (Default) | `320×240` (Compact) | Expected Mode |
| :--- | :--- | :--- | :--- | :--- |
| `1x1` | Full Screen | `480 × 320` | `320 × 240` | Full |
| `2x1` | Left / Right | `239 × 320` | `159 × 240` | Medium (`max-width: 205px` stacks vertically at `320×240`) |
| `1x2` | Top / Bottom Split | `480 × 159` | `320 × 119` | Wide-Shallow 3-zone horizontal split |
| `2x2` | Quarter HUD | `239 × 159` | `159 × 119` | Quarter (`480×320`) / Compact (`320×240`) |
| `2-big-1-small` | Top Primary (×2) | `239 × 202` | `159 × 151` | Medium |
| `2-big-1-small` | Bottom Compact (`span 2`) | `480 × 116` | `320 × 87` | Wide-Shallow 3-zone horizontal split |
| `3x1` | Vertical Strips (×3) | `158.7 × 320` | `105.3 × 240` | Narrow-Medium (`max-width: 205px`) / Strip (`<= 155px`) |
| `4x1` | Narrow Strips (×4) | `118.5 × 320` | `78.5 × 240` | Narrow Vertical Strip (`max-width: 155px`) |
| *HUD Studio* | Settings Drawer Preview | `~380 × 144` | — | Wide-Shallow / Compact Preview |

---

## 3. Canonical Frame, Reticle, Header & Progress Bar Spacings

Use these exact CSS tokens in Full/Medium/Quarter slots so your top text, top divider line, corner brackets, and bottom progress bar line up with `spotify` and `bambu`:

```css
/* 1. Widget Root — NEVER override outer padding in max-height: 175px (2x2 quarter HUD) */
.widget-root {
  position: relative;
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  background: #000000;
  color: #ffffff;
  overflow: hidden;
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-variant-numeric: tabular-nums;
  user-select: none;
  padding: clamp(8px, 3.6cqmin, 18px);
}

/* 2. Tactical Corner Reticles (toggleable via `showCornerBrackets: true`) */
.reticle {
  position: absolute;
  width: clamp(7px, 3.4cqmin, 13px);
  height: clamp(7px, 3.4cqmin, 13px);
  border-color: var(--plugin-accent);
  pointer-events: none;
  opacity: 0.9;
  z-index: 2;
}
.reticle-tl { top: 5px;    left: 5px;  border-top: 2px solid;    border-left: 2px solid; }
.reticle-tr { top: 5px;    right: 5px; border-top: 2px solid;    border-right: 2px solid; }
.reticle-bl { bottom: 5px; left: 5px;  border-bottom: 2px solid; border-left: 2px solid; }
.reticle-br { bottom: 5px; right: 5px; border-bottom: 2px solid; border-right: 2px solid; }

/* 3. Full / Quarter Flex Frame */
.widget-full {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  width: 100%;
  height: 100%;
  gap: clamp(6px, 3cqh, 14px);
}

/* 4. Header Row & Divider Line (locked to 25.5px bottom edge at 2x2 239x159) */
.widget-header {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: clamp(4px, 1.8cqh, 8px);
  min-height: calc(clamp(12px, 6cqh, 22px) + clamp(4px, 1.8cqh, 8px) + 1px);
  border-bottom: 1px solid color-mix(in srgb, var(--plugin-accent) 42%, #334155);
  flex-shrink: 0;
  min-width: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: clamp(5px, 1.8cqw, 9px);
  min-width: 0;
}

.status-dot {
  width: clamp(7px, 2.2cqmin, 10px);
  height: clamp(7px, 2.2cqmin, 10px);
  border-radius: 999px;
  flex-shrink: 0;
}

.header-title {
  font-size: clamp(9px, min(3.4cqw, 5cqh), 13px);
  font-weight: 700;
  letter-spacing: 0.11em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Keep right-side header pills compact so they never push .widget-header taller */
.header-badge {
  font-size: clamp(7.5px, min(2.5cqw, 4cqh), 11px);
  font-weight: 700;
  line-height: 1;
  letter-spacing: 0.08em;
  padding: 1px clamp(4px, 1.2cqw, 7px);
  border-radius: 3px;
  border: 1px solid currentColor;
  background: #000000;
  white-space: nowrap;
  flex-shrink: 0;
}

/* 5. Bottom Linear Progress Bar */
.progress-track {
  position: relative;
  width: 100%;
  height: clamp(6px, 2.6cqh, 11px);
  background: #1e293b;
  border: 1px solid color-mix(in srgb, var(--plugin-accent) 40%, #334155);
  border-radius: 3px;
  overflow: hidden;
  flex-shrink: 0;
}

.progress-ticks {
  position: absolute;
  inset: 0;
  background-image: repeating-linear-gradient(
    to right,
    transparent,
    transparent calc(10% - 2px),
    #000000 calc(10% - 2px),
    #000000 10%
  );
  pointer-events: none;
}
```

> [!IMPORTANT]
> Never reduce `.widget-root` `padding` inside `@container hud-slot (max-height: 175px)` for `2x2` quarter slots (`239×159`). Tighten only internal gaps (`.widget-full { gap: clamp(3px, 1.8cqh, 7px); }` and body gaps) so the outer `8px` frame, `5px` reticles, header divider, and bottom progress bar stay flush with adjacent plugins.

---

## 4. Canonical `@container hud-slot` Breakpoints

Order container queries from broadest to most specific, keeping **`max-width: 155px` last** so ultra-narrow vertical strips always win over `max-height` queries:

1. **Quarter HUD (`2x2` at `480×320` -> `239×159`)**
   - `@container hud-slot (max-height: 175px)`: keep outer `padding: clamp(8px, 3.6cqmin, 18px);`, tighten internal body gap (`clamp(2px, 1.4cqh, 6px)`), cap radial graphic height to `min(34cqw, 54cqh)`.
   - `@container hud-slot (max-width: 265px) and (max-height: 175px)`: switch 3–4 item metric tiles to short mnemonics (`N1`, `N2`, `B`, `C`) and single-number values (`220°`) so nothing crowds horizontally.
2. **Narrow-Medium Vertical Stack (`3x1` at `480×320` -> `158.7×320`, `2x1` at `320×240` -> `159×240`)**
   - `@container hud-slot (max-width: 205px)`: stack primary visual above metrics (`flex-direction: column`), switch multi-column metric grids to `minmax(0, 1fr)` or compact 2-column rows.
3. **Wide-Shallow / Top-Bottom Split (`1x2` at `480×159` or `320×119`, `2-big-1-small` bottom at `480×116` or `320×87`, Settings mini-preview)**
   - `@container hud-slot (max-height: 165px) and (min-width: 260px)` and `@container hud-slot (max-height: 135px)`:
     - Use a **3-zone horizontal layout**:
       - **Left**: Compact radial gauge / primary icon (`flex-shrink: 0`).
       - **Center**: Full status/stage text stacked vertically *above* wrapping metric/temperature chips (`flex: 1; min-width: 0;`). Allow wrapping (`white-space: normal`) rather than truncating status text with `...`.
       - **Right**: Right-aligned `ETA` / time / primary counter (`flex-shrink: 0`).
   - Hide `.reticle` only at `@container hud-slot (max-height: 110px)` (so `1x2` at `159px` / `119px` keeps brackets cleanly when `showCornerBrackets` is on).
4. **Narrow Vertical Strip (`4x1` at `480×320` -> `118.5×320`, `3x1`/`4x1` at `320×240`) — MUST BE LAST**
   - `@container hud-slot (max-width: 155px)`: hide `.reticle` and full header/footer; center-stack compact graphic, short mnemonic label, primary ETA/counter, and micro chips vertically.

---

## 5. Optical Combiner Colors & Contrast (`>= 7:1` on `#000000`)

Black pixels (`#000000`) render **transparent** on the `HRZN-01` optical combiner film. Avoid dim grays (`#64748b`, `#475569`) for readable text.

| Role | Hex | Contrast vs `#000000` | Usage |
| :--- | :--- | :--- | :--- |
| Background | `#000000` | — | Combiner transparent canvas |
| Primary Text | `#ffffff` / `#f8fafc` | `21.0:1` / `20.1:1` | Hero readouts, values, filenames |
| Secondary Text | `#e2e8f0` | `16.9:1` | Subtitles, layer counters |
| Tertiary Labels | `#cbd5e1` | `13.5:1` | Metric keys (`ETA`, `NOZZLE`, `BED`) |
| Default Accent | `#00f0ff` | `15.1:1` | Active state, progress, reticles |
| Complete / OK | `#34f5a8` | `14.8:1` | Finished / online indicators |
| Warning / Pause | `#fde047` | `16.5:1` | `PAUSE` / moving / caution states |
| Error / Alert | `#ff6b8b` | `7.7:1` | `FAILED` / `print_error != 0` / offline alerts |

- **Zero hover-only information**: `HRZN-01` is a passive display; never hide critical status behind `:hover` or `title` tooltips alone.

---

## 6. Runtime SFC & `Settings.vue` Conventions

Because `.vue` plugins are compiled **in-browser at runtime** (`web/src/plugins/sfcLoader.ts`) without re-running Vite or Tailwind:

- **Imports**: Only import from `'vue'` and relative files inside `plugins/<id>/` (`./types`, `./plugin.json`, local `.vue`/`.ts` helpers). Never import external npm packages or `web/src/*` paths.
- **`Widget.vue` Styling**: Write layout and theme styles in `<style scoped>` CSS using `clamp()`, `cqw`/`cqh`/`cqmin`, and `@container hud-slot` queries.
- **`Settings.vue` Styling**: Use only Tailwind utility classes already compiled into `web/dist/assets/*.css` (follow existing `Settings.vue` components in `clock`, `telemetry`, `weather`, `spotify`, `bambu`).
- **`Settings.vue` Structure**:
  1. **Status / Connection card** (when backed by a live service/device, exposing `/status` via `get_router()`).
  2. **Connection / Configuration inputs** (password-mask secrets with a Show/Hide button).
  3. **Simulation / Mock Mode controls** (if applicable for testing without hardware).
  4. **Display Elements checkboxes** — include **`Show Corner Brackets` (`showCornerBrackets: true`)** whenever the widget draws `.reticle` corners.
  5. **On-Event Trigger Conditions** (when `supportsOnEvent: true`).
  6. **Accent Color swatches + color picker** (`#00f0ff`, `#10e18c`, `#f5a623`, `#ff2a6d`, `#a855f7`, `#f8fafc`).

---

## 7. Pre-Flight Checklist for New Plugins

- [ ] `plugin.json` matches `HudPluginProvider` fields (`id`, `name`, `description`, `version`, `basePriority`, `defaultDynamicMode`, `supportsOnEvent`, `defaultSettings`).
- [ ] `Widget.vue` uses `#000000` background, `clamp(8px, 3.6cqmin, 18px)` outer padding, canonical header/reticle/progress-bar tokens, and `>= 7:1` contrast text.
- [ ] Tested visually in `1x1`, `2x2` (aligned alongside `spotify`/`clock`), `1x2` / `2-big-1-small` bottom (untruncated text), and `4x1` (`<= 155px`).
- [ ] `Settings.vue` implements `v-model` (`modelValue` / `update:modelValue`), exposes `showCornerBrackets` if reticles are used, and compiles cleanly with `@vue/compiler-sfc` + `sucrase`.
- [ ] `provider.py` (if present) stops any replaced background worker threads on `POST /api/plugins/reload` and clears non-test holds cleanly when returning to idle.
