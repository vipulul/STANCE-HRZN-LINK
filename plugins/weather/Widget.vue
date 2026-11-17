<script setup lang="ts">
import { computed } from 'vue'
import type { WeatherIconId, WeatherPluginData, WeatherSettings } from './types'
import { DEFAULT_WEATHER_SETTINGS } from './types'

const props = withDefaults(
  defineProps<{
    settings?: Partial<WeatherSettings>
    data?: WeatherPluginData
    slotIndex?: number
    layout?: string
  }>(),
  {
    settings: () => ({}),
    data: () => ({}),
    slotIndex: 0,
    layout: '1x1',
  },
)

const mergedSettings = computed<WeatherSettings>(() => ({
  ...DEFAULT_WEATHER_SETTINGS,
  ...props.settings,
}))

const cityLabel = computed(() =>
  String(props.data?.city_name || mergedSettings.value.cityName || 'BUCHAREST').toUpperCase(),
)

const tempDisplay = computed(() => {
  const t = props.data?.temperature_c
  return typeof t === 'number' && !Number.isNaN(t) ? `${Math.round(t)}°C` : '--°C'
})

const highLowDisplay = computed(() => {
  const hi = props.data?.temp_max_c
  const lo = props.data?.temp_min_c
  const hiStr = typeof hi === 'number' && !Number.isNaN(hi) ? `${Math.round(hi)}°` : '--°'
  const loStr = typeof lo === 'number' && !Number.isNaN(lo) ? `${Math.round(lo)}°` : '--°'
  return `H ${hiStr} / L ${loStr}`
})

const humidityDisplay = computed(() => {
  const h = props.data?.humidity_pct
  return typeof h === 'number' && !Number.isNaN(h) ? `${Math.round(h)}%` : '--%'
})

const windDisplay = computed(() => {
  const w = props.data?.wind_kmh
  return typeof w === 'number' && !Number.isNaN(w) ? `${Math.round(w)} km/h` : '-- km/h'
})

const conditionDisplay = computed(() =>
  String(props.data?.condition || 'SYNCING').toUpperCase(),
)

const iconId = computed<WeatherIconId>(() => props.data?.icon || 'unknown')

const isAlertActive = computed(
  () => Boolean(props.data?.severe) && Boolean(mergedSettings.value.alertOnSevereWeather),
)

const hasTelemetryRow = computed(
  () =>
    mergedSettings.value.showHighLow ||
    mergedSettings.value.showHumidity ||
    mergedSettings.value.showWind,
)
</script>

<template>
  <div
    class="weather-widget"
    :class="{ 'is-alert': isAlertActive }"
    :style="{ '--wx-accent': mergedSettings.accentColor }"
  >
    <!-- Tactical corner reticles (hidden in narrow/shallow slots via @container) -->
    <template v-if="mergedSettings.showCornerBrackets">
      <span class="reticle reticle-tl" aria-hidden="true" />
      <span class="reticle reticle-tr" aria-hidden="true" />
      <span class="reticle reticle-bl" aria-hidden="true" />
      <span class="reticle reticle-br" aria-hidden="true" />
    </template>

    <!-- Top Header (Large / Full slots) -->
    <header class="wx-header">
      <div class="wx-city">{{ cityLabel }}</div>
      <div class="wx-status-badge" :class="{ alert: isAlertActive }">
        {{ isAlertActive ? 'WX // ALERT' : 'WX // LIVE' }}
      </div>
    </header>

    <!-- Main Hero: Geometric SVG Icon + Temperature + Condition -->
    <div class="wx-hero">
      <svg
        class="wx-icon"
        viewBox="0 0 64 64"
        fill="none"
        stroke="currentColor"
        stroke-width="2.5"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <!-- CLEAR -->
        <g v-if="iconId === 'clear'">
          <circle cx="32" cy="32" r="11" />
          <line x1="32" y1="8" x2="32" y2="15" />
          <line x1="32" y1="49" x2="32" y2="56" />
          <line x1="8" y1="32" x2="15" y2="32" />
          <line x1="49" y1="32" x2="56" y2="32" />
          <line x1="15" y1="15" x2="20" y2="20" />
          <line x1="44" y1="44" x2="49" y2="49" />
          <line x1="49" y1="15" x2="44" y2="20" />
          <line x1="20" y1="44" x2="15" y2="49" />
        </g>

        <!-- PARTLY CLOUDY -->
        <g v-else-if="iconId === 'partly-cloudy'">
          <path d="M22 28a9 9 0 1 1 14-7" />
          <line x1="26" y1="10" x2="26" y2="14" />
          <line x1="12" y1="24" x2="16" y2="24" />
          <line x1="16" y1="14" x2="19" y2="17" />
          <path d="M20 48h26a9 9 0 0 0 1-17.9A12 12 0 0 0 24 28a10 10 0 0 0-4 20Z" />
        </g>

        <!-- OVERCAST -->
        <g v-else-if="iconId === 'overcast'">
          <path d="M18 46h28a10 10 0 0 0 1-19.9A13 13 0 0 0 22 24a11 11 0 0 0-4 22Z" />
        </g>

        <!-- FOG -->
        <g v-else-if="iconId === 'fog'">
          <path d="M16 34h32a8 8 0 0 0 1-15.9A11 11 0 0 0 27 16a9 9 0 0 0-11 18Z" />
          <line x1="12" y1="41" x2="52" y2="41" />
          <line x1="16" y1="48" x2="48" y2="48" />
          <line x1="20" y1="55" x2="44" y2="55" />
        </g>

        <!-- DRIZZLE -->
        <g v-else-if="iconId === 'drizzle'">
          <path d="M18 36h28a9 9 0 0 0 1-17.9A12 12 0 0 0 24 16a10 10 0 0 0-6 20Z" />
          <line x1="22" y1="43" x2="20" y2="48" />
          <line x1="32" y1="43" x2="30" y2="48" />
          <line x1="42" y1="43" x2="40" y2="48" />
        </g>

        <!-- RAIN -->
        <g v-else-if="iconId === 'rain'">
          <path d="M18 35h28a9 9 0 0 0 1-17.9A12 12 0 0 0 24 15a10 10 0 0 0-6 20Z" />
          <line x1="21" y1="42" x2="17" y2="53" />
          <line x1="32" y1="42" x2="28" y2="53" />
          <line x1="43" y1="42" x2="39" y2="53" />
        </g>

        <!-- SNOW -->
        <g v-else-if="iconId === 'snow'">
          <path d="M18 34h28a9 9 0 0 0 1-17.9A12 12 0 0 0 24 14a10 10 0 0 0-6 20Z" />
          <line x1="22" y1="42" x2="22" y2="54" />
          <line x1="17" y1="45" x2="27" y2="51" />
          <line x1="27" y1="45" x2="17" y2="51" />
          <line x1="42" y1="42" x2="42" y2="54" />
          <line x1="37" y1="45" x2="47" y2="51" />
          <line x1="47" y1="45" x2="37" y2="51" />
        </g>

        <!-- STORM -->
        <g v-else-if="iconId === 'storm'">
          <path d="M18 34h28a9 9 0 0 0 1-17.9A12 12 0 0 0 24 14a10 10 0 0 0-6 20Z" />
          <polyline points="35 38 27 48 34 48 29 58" />
        </g>

        <!-- UNKNOWN / OFFLINE -->
        <g v-else>
          <circle cx="32" cy="32" r="16" stroke-dasharray="5 4" />
          <line x1="24" y1="32" x2="40" y2="32" />
        </g>
      </svg>

      <div class="wx-temp-block">
        <div class="wx-temp">{{ tempDisplay }}</div>
        <div v-if="mergedSettings.showCondition" class="wx-condition">
          {{ conditionDisplay }}
        </div>
        <div v-if="mergedSettings.showHighLow" class="wx-hl-inline">
          {{ highLowDisplay }}
        </div>
      </div>
    </div>

    <!-- Bottom Telemetry Strip (Large / Full slots) -->
    <footer v-if="hasTelemetryRow" class="wx-telemetry">
      <div v-if="mergedSettings.showHighLow" class="wx-metric">
        <span class="wx-metric-label">RANGE</span>
        <span class="wx-metric-value">{{ highLowDisplay }}</span>
      </div>
      <div v-if="mergedSettings.showHumidity" class="wx-metric">
        <span class="wx-metric-label">HUM</span>
        <span class="wx-metric-value">{{ humidityDisplay }}</span>
      </div>
      <div v-if="mergedSettings.showWind" class="wx-metric">
        <span class="wx-metric-label">WIND</span>
        <span class="wx-metric-value">{{ windDisplay }}</span>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.weather-widget {
  position: relative;
  width: 100%;
  height: 100%;
  background: #000000;
  color: #f8fafc;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  overflow: hidden;
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  user-select: none;
  padding: clamp(8px, 4cqmin, 20px);
  box-sizing: border-box;
}

.weather-widget.is-alert {
  --wx-accent: #ff4d6d;
}

/* Corner reticles */
.reticle {
  position: absolute;
  width: clamp(8px, 4cqmin, 14px);
  height: clamp(8px, 4cqmin, 14px);
  border-color: var(--wx-accent);
  pointer-events: none;
}

.reticle-tl {
  top: 6px;
  left: 6px;
  border-top: 2px solid;
  border-left: 2px solid;
}

.reticle-tr {
  top: 6px;
  right: 6px;
  border-top: 2px solid;
  border-right: 2px solid;
}

.reticle-bl {
  bottom: 6px;
  left: 6px;
  border-bottom: 2px solid;
  border-left: 2px solid;
}

.reticle-br {
  bottom: 6px;
  right: 6px;
  border-bottom: 2px solid;
  border-right: 2px solid;
}

/* Header */
.wx-header {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 6px;
  z-index: 2;
}

.wx-city {
  font-size: clamp(10px, min(4cqw, 6cqh), 15px);
  font-weight: 700;
  letter-spacing: 0.14em;
  color: #f8fafc;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.wx-status-badge {
  font-size: clamp(9px, min(3cqw, 4.8cqh), 12px);
  font-weight: 700;
  letter-spacing: 0.12em;
  color: var(--wx-accent);
  white-space: nowrap;
}

.wx-status-badge.alert {
  color: #ff4d6d;
}

/* Hero */
.wx-hero {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: clamp(10px, 4.5cqw, 26px);
  z-index: 2;
  max-width: 100%;
}

.wx-icon {
  width: clamp(34px, min(22cqw, 34cqh), 92px);
  height: clamp(34px, min(22cqw, 34cqh), 92px);
  color: var(--wx-accent);
  flex-shrink: 0;
}

.wx-temp-block {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  gap: clamp(2px, 1.5cqh, 6px);
  min-width: 0;
}

.wx-temp {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  line-height: 1;
  letter-spacing: -0.03em;
  color: #ffffff;
  font-size: clamp(20px, min(18cqw, 28cqh), 64px);
}

.wx-condition {
  font-size: clamp(10px, min(4.2cqw, 6.5cqh), 16px);
  font-weight: 700;
  letter-spacing: 0.12em;
  color: var(--wx-accent);
  white-space: nowrap;
}

.wx-hl-inline {
  display: none;
  font-variant-numeric: tabular-nums;
  font-size: clamp(10px, min(4cqw, 6cqh), 14px);
  font-weight: 600;
  letter-spacing: 0.06em;
  color: #cbd5e1;
  white-space: nowrap;
}

/* Bottom Telemetry */
.wx-telemetry {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-around;
  gap: clamp(6px, 2.5cqw, 16px);
  border-top: 1px solid color-mix(in srgb, var(--wx-accent) 28%, transparent);
  padding-top: clamp(6px, 2.5cqh, 12px);
  z-index: 2;
}

.wx-metric {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.wx-metric-label {
  font-size: clamp(8px, min(2.8cqw, 4.4cqh), 11px);
  font-weight: 600;
  letter-spacing: 0.14em;
  color: #94a3b8;
}

.wx-metric-value {
  font-variant-numeric: tabular-nums;
  font-size: clamp(10px, min(3.8cqw, 6cqh), 15px);
  font-weight: 700;
  color: #f8fafc;
  white-space: nowrap;
}

/* Medium slots (2x1 tall-medium or 2x2 quadrant) */
@container hud-slot (max-width: 270px) {
  .wx-header,
  .wx-telemetry {
    display: none;
  }

  .weather-widget {
    justify-content: center;
  }

  .wx-hero {
    flex-direction: column;
    gap: clamp(4px, 3cqh, 12px);
    text-align: center;
  }

  .wx-temp-block {
    align-items: center;
  }

  .wx-hl-inline {
    display: block;
  }
}

@container hud-slot (max-height: 200px) {
  .wx-header,
  .wx-telemetry {
    display: none;
  }

  .weather-widget {
    justify-content: center;
  }

  .wx-hl-inline {
    display: block;
  }
}

/* Shallow slots (1x2, 2-big-1-small compact bottom slot) */
@container hud-slot (max-height: 135px) {
  .reticle,
  .wx-header,
  .wx-condition,
  .wx-hl-inline,
  .wx-telemetry {
    display: none;
  }

  .weather-widget {
    justify-content: center;
    padding: clamp(4px, 3cqmin, 10px);
  }

  .wx-hero {
    flex-direction: row;
    gap: clamp(8px, 4cqw, 18px);
  }

  .wx-icon {
    width: clamp(28px, 52cqh, 58px);
    height: clamp(28px, 52cqh, 58px);
  }

  .wx-temp {
    font-size: clamp(20px, 46cqh, 52px);
  }
}

/* Narrow vertical strips (3x1, 4x1) */
@container hud-slot (max-width: 155px) {
  .reticle,
  .wx-header,
  .wx-condition,
  .wx-hl-inline,
  .wx-telemetry {
    display: none;
  }

  .weather-widget {
    justify-content: center;
    padding: clamp(4px, 3cqmin, 10px);
  }

  .wx-hero {
    flex-direction: column;
    gap: clamp(6px, 4cqh, 14px);
  }

  .wx-temp-block {
    align-items: center;
  }

  .wx-icon {
    width: clamp(30px, 44cqw, 56px);
    height: clamp(30px, 44cqw, 56px);
  }

  .wx-temp {
    font-size: clamp(18px, 24cqw, 34px);
  }
}
</style>
