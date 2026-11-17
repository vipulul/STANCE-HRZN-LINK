<script setup lang="ts">
import { computed } from 'vue'
import type {
  FlapDisplayState,
  TelemetryPluginData,
  TelemetrySettings,
} from './types'
import { DEFAULT_TELEMETRY_SETTINGS } from './types'

type MetricTone = 'ok' | 'warn' | 'err' | 'accent' | 'neutral'

interface TelemetryMetric {
  id: 'fps' | 'flap' | 'servo' | 'device' | 'latency' | 'layout'
  label: string
  value: string
  unit: string
  badge?: string
  subValue?: string
  tone: MetricTone
}

const props = withDefaults(
  defineProps<{
    settings?: Partial<TelemetrySettings>
    data?: TelemetryPluginData
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

const mergedSettings = computed<TelemetrySettings>(() => ({
  ...DEFAULT_TELEMETRY_SETTINGS,
  ...props.settings,
}))

const deviceConnected = computed<boolean>(() => Boolean(props.data?.device_connected))

const flapState = computed<FlapDisplayState>(() => {
  const raw = String(props.data?.flap_state ?? 'OPEN').toUpperCase()
  if (raw === 'MOVING' || raw === 'CLOSED' || raw === 'OPEN') {
    return raw
  }
  return 'OPEN'
})

const overallStatus = computed<{
  label: string
  shortLabel: string
  tone: MetricTone
}>(() => {
  if (flapState.value === 'MOVING') {
    return { label: 'ACTUATOR MOVING', shortLabel: 'MOVING', tone: 'warn' }
  }
  if (!deviceConnected.value) {
    return { label: 'LINK OFFLINE', shortLabel: 'OFFLINE', tone: 'err' }
  }
  return { label: 'LINK ONLINE', shortLabel: 'ONLINE', tone: 'ok' }
})

const enabledMetrics = computed<TelemetryMetric[]>(() => {
  const s = mergedSettings.value
  const d = props.data ?? {}
  const compact = s.compactLabels
  const list: TelemetryMetric[] = []

  if (s.showFps) {
    const fps = typeof d.stream_fps === 'number' ? d.stream_fps.toFixed(1) : '--'
    list.push({
      id: 'fps',
      label: compact ? 'FPS' : 'STREAM FPS',
      value: fps,
      unit: 'FPS',
      tone: 'accent',
    })
  }

  if (s.showFlapState) {
    const pct =
      typeof d.flap_position_pct === 'number' && deviceConnected.value
        ? `${d.flap_position_pct}%`
        : typeof d.target_angle_pct === 'number'
          ? `${d.target_angle_pct}%`
          : undefined
    list.push({
      id: 'flap',
      label: compact ? 'FLAP' : 'FLAP STATE',
      value: flapState.value,
      unit: pct ?? '',
      badge: flapState.value,
      tone:
        flapState.value === 'MOVING'
          ? 'warn'
          : flapState.value === 'OPEN'
            ? 'ok'
            : 'neutral',
    })
  }

  if (s.showServoPulse) {
    const pulse = typeof d.servo_pulse_us === 'number' ? String(Math.round(d.servo_pulse_us)) : '--'
    list.push({
      id: 'servo',
      label: compact ? 'PWM' : 'SERVO PULSE',
      value: pulse,
      unit: 'µs',
      tone: d.servo_attached ? 'warn' : 'neutral',
    })
  }

  if (s.showDeviceStatus) {
    const hasRssi = typeof d.wifi_rssi === 'number'
    list.push({
      id: 'device',
      label: compact ? 'LINK' : 'ESP32 LINK',
      value: hasRssi ? String(Math.round(d.wifi_rssi as number)) : '--',
      unit: 'dBm',
      badge: deviceConnected.value ? 'ONLINE' : 'OFFLINE',
      tone: deviceConnected.value ? 'ok' : 'err',
    })
  }

  if (s.showLatency) {
    const latency =
      typeof d.frame_latency_ms === 'number' ? String(Math.round(d.frame_latency_ms)) : '--'
    list.push({
      id: 'latency',
      label: compact ? 'LAT' : 'LATENCY',
      value: latency,
      unit: 'ms',
      tone: 'neutral',
    })
  }

  if (s.showLayout) {
    const activeLayout = String(d.active_layout || props.layout || '1x1').toUpperCase()
    list.push({
      id: 'layout',
      label: compact ? 'GRID' : 'LAYOUT',
      value: activeLayout,
      unit: '',
      tone: 'accent',
    })
  }

  return list
})

const compactMetrics = computed<TelemetryMetric[]>(() => enabledMetrics.value.slice(0, 2))
</script>

<template>
  <div
    class="telemetry-widget"
    :style="{ '--telemetry-accent': mergedSettings.accentColor }"
  >
    <!-- Tactical corner reticles (hidden in compact layouts) -->
    <span class="reticle reticle-tl" aria-hidden="true" />
    <span class="reticle reticle-tr" aria-hidden="true" />
    <span class="reticle reticle-bl" aria-hidden="true" />
    <span class="reticle reticle-br" aria-hidden="true" />

    <!-- Medium / Full Diagnostic View -->
    <div class="telemetry-full">
      <header class="telem-header">
        <div class="header-left">
          <span class="status-dot" :class="`tone-${overallStatus.tone}`" />
          <span class="header-title">
            {{ mergedSettings.compactLabels ? 'TELEM' : 'HRZN // TELEM' }}
          </span>
        </div>
        <span class="status-badge" :class="`tone-${overallStatus.tone}`">
          {{ overallStatus.label }}
        </span>
      </header>

      <div v-if="enabledMetrics.length > 0" class="metrics-grid">
        <div
          v-for="metric in enabledMetrics"
          :key="metric.id"
          class="metric-tile"
          :class="`tile-${metric.tone}`"
        >
          <div class="metric-top">
            <span class="metric-label">{{ metric.label }}</span>
            <span
              v-if="metric.badge"
              class="metric-badge"
              :class="`tone-${metric.tone}`"
            >
              {{ metric.badge }}
            </span>
          </div>

          <div class="metric-readout">
            <span
              v-if="!metric.badge || metric.id !== 'flap'"
              class="metric-value"
              :class="{ 'is-accent': metric.tone === 'accent' }"
            >
              {{ metric.value }}
            </span>
            <span
              v-else
              class="metric-value"
              :class="`text-${metric.tone}`"
            >
              {{ metric.value }}
            </span>
            <span v-if="metric.unit" class="metric-unit">{{ metric.unit }}</span>
          </div>
        </div>
      </div>

      <div v-else class="empty-metrics">
        NO METRICS ENABLED
      </div>
    </div>

    <!-- Compact Slot View (@container max-width: 155px or max-height: 135px) -->
    <div class="telemetry-compact">
      <div class="compact-status-pill">
        <span class="status-dot" :class="`tone-${overallStatus.tone}`" />
        <span class="compact-status-text" :class="`text-${overallStatus.tone}`">
          {{ overallStatus.shortLabel }}
        </span>
      </div>

      <div v-if="compactMetrics.length > 0" class="compact-metrics-list">
        <div
          v-for="metric in compactMetrics"
          :key="metric.id"
          class="compact-metric"
        >
          <span class="compact-label">{{ metric.label }}</span>
          <div class="compact-value-row">
            <span
              class="compact-value"
              :class="
                metric.badge
                  ? `text-${metric.tone}`
                  : metric.tone === 'accent'
                    ? 'is-accent'
                    : ''
              "
            >
              {{ metric.id === 'device' && metric.value === '--' ? metric.badge : metric.value }}
            </span>
            <span
              v-if="metric.unit && !(metric.id === 'device' && metric.value === '--')"
              class="compact-unit"
            >
              {{ metric.unit }}
            </span>
          </div>
        </div>
      </div>

      <div v-else class="compact-metric">
        <span class="compact-label">STATUS</span>
        <span class="compact-value" :class="`text-${overallStatus.tone}`">
          {{ overallStatus.shortLabel }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.telemetry-widget {
  position: relative;
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  background: #000000;
  color: #f8fafc;
  overflow: hidden;
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-variant-numeric: tabular-nums;
  user-select: none;
  padding: clamp(6px, 3cqmin, 14px);
}

/* Corner reticles matching Chronos tactical language */
.reticle {
  position: absolute;
  width: clamp(6px, 3.2cqmin, 12px);
  height: clamp(6px, 3.2cqmin, 12px);
  border-color: var(--telemetry-accent);
  pointer-events: none;
  opacity: 0.9;
}

.reticle-tl {
  top: 4px;
  left: 4px;
  border-top: 2px solid;
  border-left: 2px solid;
}

.reticle-tr {
  top: 4px;
  right: 4px;
  border-top: 2px solid;
  border-right: 2px solid;
}

.reticle-bl {
  bottom: 4px;
  left: 4px;
  border-bottom: 2px solid;
  border-left: 2px solid;
}

.reticle-br {
  bottom: 4px;
  right: 4px;
  border-bottom: 2px solid;
  border-right: 2px solid;
}

/* Medium / Full view */
.telemetry-full {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  gap: clamp(4px, 2.2cqh, 10px);
}

.telem-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  border-bottom: 1px solid color-mix(in srgb, var(--telemetry-accent) 45%, #334155);
  padding-bottom: clamp(3px, 1.4cqh, 6px);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: clamp(4px, 1.5cqw, 8px);
  min-width: 0;
}

.header-title {
  font-size: clamp(9px, min(3.4cqw, 5.2cqh), 13px);
  font-weight: 700;
  letter-spacing: 0.1em;
  color: #f8fafc;
  white-space: nowrap;
}

.status-dot {
  width: clamp(7px, 2.2cqmin, 10px);
  height: clamp(7px, 2.2cqmin, 10px);
  border-radius: 999px;
  flex-shrink: 0;
}

.status-dot.tone-ok {
  background: #10e18c;
  box-shadow: 0 0 8px #10e18c;
}

.status-dot.tone-warn {
  background: #fbbf24;
  box-shadow: 0 0 8px #fbbf24;
}

.status-dot.tone-err {
  background: #ff7597;
  box-shadow: 0 0 8px #ff7597;
}

.status-dot.tone-accent {
  background: var(--telemetry-accent);
}

.status-dot.tone-neutral {
  background: #cbd5e1;
}

.status-badge,
.metric-badge {
  font-size: clamp(8px, min(2.6cqw, 4.2cqh), 11px);
  font-weight: 700;
  letter-spacing: 0.08em;
  padding: 1px clamp(4px, 1.2cqw, 7px);
  border-radius: 3px;
  border: 1px solid currentColor;
  background: #000000;
  white-space: nowrap;
}

.tone-ok,
.text-ok {
  color: #34f5a8;
}

.tone-warn,
.text-warn {
  color: #fde047;
}

.tone-err,
.text-err {
  color: #ff7597;
}

.tone-accent,
.is-accent {
  color: var(--telemetry-accent);
}

.tone-neutral,
.text-neutral {
  color: #e2e8f0;
}

.metrics-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: minmax(0, 1fr);
  gap: clamp(3px, 1.5cqmin, 8px);
}

@container hud-slot (min-width: 340px) {
  .metrics-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@container hud-slot (max-width: 205px) {
  .metrics-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .metric-tile {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
  }

  .metric-badge {
    display: none;
  }
}

.metric-tile {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-width: 0;
  min-height: 0;
  padding: clamp(3px, 1.8cqmin, 8px) clamp(5px, 2cqw, 10px);
  border: 1px solid color-mix(in srgb, var(--telemetry-accent) 32%, #334155);
  border-radius: 4px;
  background: #000000;
}

.tile-warn {
  border-color: #fbbf24;
}

.tile-err {
  border-color: #ff7597;
}

.metric-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  min-width: 0;
}

.metric-label {
  font-size: clamp(8px, min(2.8cqw, 4.4cqh), 11px);
  font-weight: 600;
  letter-spacing: 0.08em;
  color: #cbd5e1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.metric-readout {
  display: flex;
  align-items: baseline;
  gap: clamp(2px, 1cqw, 5px);
  line-height: 1.05;
  min-width: 0;
}

.metric-value {
  font-size: clamp(13px, min(6.2cqw, 10.5cqh), 28px);
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #f8fafc;
  white-space: nowrap;
}

.metric-unit {
  font-size: clamp(8px, min(2.8cqw, 4.8cqh), 13px);
  font-weight: 600;
  color: #cbd5e1;
  white-space: nowrap;
}

.empty-metrics {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: clamp(10px, 3cqw, 14px);
  letter-spacing: 0.1em;
  color: #cbd5e1;
}

/* Compact view (hidden in medium/full slots) */
.telemetry-compact {
  display: none;
  width: 100%;
  height: 100%;
  align-items: center;
  justify-content: space-between;
  gap: clamp(6px, 3cqmin, 16px);
}

.compact-status-pill {
  display: flex;
  align-items: center;
  gap: clamp(4px, 1.5cqw, 8px);
  flex-shrink: 0;
}

.compact-status-text {
  font-size: clamp(9px, min(5cqw, 11cqh), 14px);
  font-weight: 700;
  letter-spacing: 0.1em;
  white-space: nowrap;
}

.compact-metrics-list {
  display: flex;
  flex: 1;
  min-width: 0;
  min-height: 0;
  align-items: center;
  justify-content: space-around;
  gap: clamp(6px, 3cqmin, 16px);
}

.compact-metric {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  min-width: 0;
  gap: clamp(1px, 1cqh, 4px);
}

.compact-label {
  font-size: clamp(8px, min(5cqw, 10cqh), 12px);
  font-weight: 600;
  letter-spacing: 0.08em;
  color: #cbd5e1;
  white-space: nowrap;
}

.compact-value-row {
  display: flex;
  align-items: baseline;
  gap: clamp(2px, 1cqw, 5px);
  line-height: 1;
}

.compact-value {
  font-size: clamp(18px, min(16cqw, 36cqh), 42px);
  font-weight: 700;
  letter-spacing: -0.03em;
  color: #f8fafc;
  white-space: nowrap;
}

.compact-unit {
  font-size: clamp(9px, min(6cqw, 13cqh), 16px);
  font-weight: 600;
  color: #cbd5e1;
  white-space: nowrap;
}

/* Wide shallow slots (e.g. 2-big-1-small compact slot or 1x2 at 320x240) */
@container hud-slot (max-height: 135px) {
  .reticle,
  .telemetry-full {
    display: none;
  }

  .telemetry-compact {
    display: flex;
    flex-direction: row;
    padding: 0 clamp(4px, 2cqw, 12px);
  }

  .compact-value {
    font-size: clamp(20px, 38cqh, 44px);
  }

  .compact-unit {
    font-size: clamp(10px, 14cqh, 16px);
  }
}

/* Narrow vertical strips (e.g. 4x1 or 3x1 at <=155px width) */
@container hud-slot (max-width: 155px) {
  .reticle,
  .telemetry-full {
    display: none;
  }

  .telemetry-compact {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
    gap: clamp(6px, 4cqh, 16px);
  }

  .compact-metrics-list {
    flex-direction: column;
    justify-content: center;
    width: 100%;
    gap: clamp(8px, 4cqh, 18px);
  }

  .compact-metric {
    align-items: center;
    width: 100%;
  }

  .compact-value {
    font-size: clamp(14px, min(18cqw, 24cqh), 28px);
  }

  .compact-unit {
    font-size: clamp(9px, 9cqw, 13px);
  }
}
</style>
