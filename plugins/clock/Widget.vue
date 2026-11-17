<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ClockPluginData, ClockSettings } from './types'
import { DEFAULT_CLOCK_SETTINGS } from './types'

const props = withDefaults(
  defineProps<{
    settings?: Partial<ClockSettings>
    data?: ClockPluginData
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

const mergedSettings = computed<ClockSettings>(() => ({
  ...DEFAULT_CLOCK_SETTINGS,
  ...props.settings,
}))

const now = ref<Date>(new Date())
let timerId: number | null = null

function syncWithServerData(data?: ClockPluginData) {
  if (data?.iso) {
    const parsed = new Date(data.iso)
    if (!Number.isNaN(parsed.getTime())) {
      now.value = parsed
    }
  }
}

watch(
  () => props.data?.iso,
  () => {
    syncWithServerData(props.data)
  },
  { immediate: true },
)

onMounted(() => {
  timerId = window.setInterval(() => {
    now.value = new Date()
  }, 250)
})

onBeforeUnmount(() => {
  if (timerId !== null) {
    window.clearInterval(timerId)
  }
})

const timeParts = computed(() => {
  const d = now.value
  const hours24 = d.getHours()
  const hours12 = hours24 % 12 || 12
  const displayHour = mergedSettings.value.format24h ? hours24 : hours12
  const minutes = d.getMinutes()
  const seconds = d.getSeconds()

  return {
    hh: String(displayHour).padStart(2, '0'),
    mm: String(minutes).padStart(2, '0'),
    ss: String(seconds).padStart(2, '0'),
    ampm: hours24 >= 12 ? 'PM' : 'AM',
    secondsNum: seconds,
    minutesNum: minutes,
  }
})

const dateText = computed(() => {
  if (props.data?.weekday && props.data?.date_display) {
    return `${props.data.weekday} ${props.data.date_display}`
  }
  const d = now.value
  const weekdays = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${weekdays[d.getDay()]} ${yyyy}-${mm}-${dd}`
})

const shortDateText = computed(() => {
  const d = now.value
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${mm}-${dd}`
})

const secondProgress = computed(() => {
  if (typeof props.data?.minute_progress_pct === 'number' && !mergedSettings.value.showSeconds) {
    return Math.max(0, Math.min(1, props.data.minute_progress_pct / 100))
  }
  return timeParts.value.secondsNum / 60
})

const arcRadius = 86
const arcCircumference = 2 * Math.PI * arcRadius
const arcDashOffset = computed(() => arcCircumference * (1 - secondProgress.value))

const tickAngles = Array.from({ length: 12 }, (_, idx) => idx * 30)
const activeSegmentCount = computed(() => Math.max(1, Math.ceil((timeParts.value.secondsNum / 60) * 12)))

const presetClass = computed(() => `preset-${mergedSettings.value.stylePreset}`)
</script>

<template>
  <div
    class="clock-widget"
    :class="[
      presetClass,
      { 'has-arc-ring': mergedSettings.showArcRing && mergedSettings.stylePreset !== 'minimal' },
    ]"
    :style="{ '--clock-accent': mergedSettings.accentColor }"
  >
    <!-- Tactical corner reticles (hidden automatically in compact/minimal modes via @container) -->
    <template v-if="mergedSettings.stylePreset === 'tactical'">
      <span class="reticle reticle-tl" />
      <span class="reticle reticle-tr" />
      <span class="reticle reticle-bl" />
      <span class="reticle reticle-br" />
      <div class="tactical-tag tactical-tag-tl">
        CHRONOS // {{ mergedSettings.format24h ? '24H' : '12H' }}
      </div>
      <div class="tactical-tag tactical-tag-tr">
        LOC
      </div>
    </template>

    <!-- Adaptive Radial Analog / Arc Ring -->
    <svg
      v-if="mergedSettings.showArcRing && mergedSettings.stylePreset !== 'minimal'"
      class="clock-arc-svg"
      viewBox="0 0 200 200"
      aria-hidden="true"
    >
      <circle
        class="arc-track"
        cx="100"
        cy="100"
        :r="arcRadius"
        fill="none"
        stroke-width="2.5"
      />
      <g class="arc-ticks">
        <line
          v-for="angle in tickAngles"
          :key="angle"
          x1="100"
          y1="10"
          x2="100"
          y2="17"
          stroke-width="1.5"
          :transform="`rotate(${angle} 100 100)`"
        />
      </g>
      <circle
        class="arc-progress"
        cx="100"
        cy="100"
        :r="arcRadius"
        fill="none"
        stroke-width="4"
        stroke-linecap="round"
        :stroke-dasharray="arcCircumference"
        :stroke-dashoffset="arcDashOffset"
        transform="rotate(-90 100 100)"
      />
    </svg>

    <!-- Core Readout -->
    <div class="clock-core">
      <div class="time-row">
        <div class="digits-wrap">
          <span
            v-if="mergedSettings.stylePreset === 'segmented'"
            class="digits-ghost"
            aria-hidden="true"
          >
            88:88
          </span>
          <span class="digits-main">{{ timeParts.hh }}:{{ timeParts.mm }}</span>
        </div>

        <div v-if="mergedSettings.showSeconds || !mergedSettings.format24h" class="side-meta">
          <span v-if="!mergedSettings.format24h" class="ampm-badge">{{ timeParts.ampm }}</span>
          <span v-if="mergedSettings.showSeconds" class="seconds-badge">:{{ timeParts.ss }}</span>
        </div>
      </div>

      <!-- Segmented 12-tick progress bar (visible in segmented mode or wide/compact views) -->
      <div
        v-if="mergedSettings.stylePreset === 'segmented'"
        class="seg-bar"
        aria-hidden="true"
      >
        <span
          v-for="idx in 12"
          :key="idx"
          class="seg-cell"
          :class="{ active: idx <= activeSegmentCount }"
        />
      </div>

      <!-- Minimal accent hairline -->
      <div
        v-else-if="mergedSettings.stylePreset === 'minimal'"
        class="minimal-line"
        aria-hidden="true"
      />

      <!-- Date line -->
      <div v-if="mergedSettings.showDate" class="date-row">
        <span class="date-full">{{ dateText }}</span>
        <span class="date-short">{{ shortDateText }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.clock-widget {
  box-sizing: border-box;
  position: relative;
  width: 100%;
  height: 100%;
  background: #000000;
  color: #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  user-select: none;
  padding: clamp(4px, 3cqmin, 14px);
}

.clock-arc-svg {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: min(90cqw, 90cqh);
  height: min(90cqw, 90cqh);
  pointer-events: none;
}

.arc-track {
  stroke: color-mix(in srgb, var(--clock-accent) 20%, transparent);
}

.arc-ticks line {
  stroke: color-mix(in srgb, var(--clock-accent) 45%, transparent);
}

.arc-progress {
  stroke: var(--clock-accent);
  transition: stroke-dashoffset 0.2s linear;
}

.clock-core {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: clamp(2px, 2.2cqh, 10px);
  max-width: 100%;
}

/* Constrain core readout cleanly inside the inner tick radius when arc ring is visible */
@container hud-slot (min-width: 171px) and (min-height: 171px) {
  .has-arc-ring .clock-core {
    gap: clamp(2px, 1.5cqmin, 8px);
    max-width: 64cqmin;
  }

  .has-arc-ring .digits-main,
  .has-arc-ring .digits-ghost {
    font-size: clamp(16px, 14.5cqmin, 68px);
  }

  .has-arc-ring .seconds-badge {
    font-size: clamp(9px, 5.2cqmin, 22px);
  }

  .has-arc-ring .ampm-badge {
    font-size: clamp(7px, 3cqmin, 12px);
  }

  .has-arc-ring .seg-bar {
    width: clamp(56px, 44cqmin, 155px);
  }

  .has-arc-ring .date-row {
    font-size: clamp(8px, 3.6cqmin, 14px);
  }
}

.time-row {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: clamp(3px, 1.8cqw, 10px);
  line-height: 1;
}

.digits-wrap {
  position: relative;
  display: inline-flex;
  align-items: baseline;
}

.digits-main,
.digits-ghost {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  letter-spacing: -0.03em;
  font-size: clamp(18px, min(20cqw, 30cqh), 72px);
}

.digits-ghost {
  position: absolute;
  inset: 0;
  color: color-mix(in srgb, var(--clock-accent) 12%, transparent);
  pointer-events: none;
}

.preset-segmented .digits-main {
  color: var(--clock-accent);
  text-shadow: 0 0 10px color-mix(in srgb, var(--clock-accent) 45%, transparent);
}

.preset-minimal .digits-main {
  font-weight: 500;
  letter-spacing: -0.02em;
  color: #f8fafc;
}

.preset-tactical .digits-main {
  color: #f8fafc;
}

.side-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  gap: 2px;
}

.seconds-badge {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: var(--clock-accent);
  font-size: clamp(11px, min(7.5cqw, 12cqh), 26px);
}

.ampm-badge {
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--clock-accent);
  font-size: clamp(8px, min(4.2cqw, 6.5cqh), 13px);
}

.minimal-line {
  width: clamp(28px, 32cqw, 110px);
  height: 2px;
  border-radius: 999px;
  background: var(--clock-accent);
  opacity: 0.85;
}

.seg-bar {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: clamp(2px, 0.8cqw, 4px);
  width: clamp(64px, 52cqw, 190px);
}

.seg-cell {
  height: clamp(3px, 1.6cqh, 6px);
  border-radius: 1px;
  background: color-mix(in srgb, var(--clock-accent) 16%, transparent);
}

.seg-cell.active {
  background: var(--clock-accent);
}

.date-row {
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--clock-accent);
  font-size: clamp(9px, min(4.6cqw, 7.5cqh), 15px);
  white-space: nowrap;
}

.preset-minimal .date-row {
  color: #94a3b8;
  letter-spacing: 0.08em;
}

.date-short {
  display: none;
}

/* Tactical corner brackets & tags */
.reticle {
  position: absolute;
  width: clamp(8px, 4.5cqmin, 16px);
  height: clamp(8px, 4.5cqmin, 16px);
  border-color: var(--clock-accent);
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

.tactical-tag {
  position: absolute;
  top: 8px;
  font-size: 9px;
  letter-spacing: 0.12em;
  color: color-mix(in srgb, var(--clock-accent) 75%, #94a3b8);
  pointer-events: none;
}

.tactical-tag-tl {
  left: 14px;
}

.tactical-tag-tr {
  right: 14px;
}

/* Hide arc ring when either dimension is too small for a legible inner dial */
@container hud-slot (max-height: 170px), (max-width: 170px) {
  .clock-arc-svg {
    display: none;
  }
}

/* Wide compact strip (e.g. 2-big-1-small bottom slot or 1x2) */
@container hud-slot (max-height: 165px) and (min-width: 300px) {
  .tactical-tag {
    display: none;
  }

  .clock-core {
    flex-direction: row;
    gap: clamp(8px, 4cqw, 20px);
  }

  .digits-main,
  .digits-ghost {
    font-size: clamp(20px, 44cqh, 54px);
  }

  .seg-bar {
    display: none;
  }

  .minimal-line {
    width: 2px;
    height: clamp(16px, 34cqh, 36px);
  }

  .date-row {
    font-size: clamp(10px, 14cqh, 14px);
  }
}

/* Narrow strip (e.g. 3x1 or 4x1) */
@container hud-slot (max-width: 165px) {
  .tactical-tag,
  .reticle {
    display: none;
  }

  .time-row {
    flex-direction: column;
    align-items: center;
    gap: 2px;
  }

  .side-meta {
    flex-direction: row;
    align-items: center;
    gap: 4px;
  }

  .digits-main,
  .digits-ghost {
    font-size: clamp(16px, 24cqw, 32px);
  }

  .seconds-badge {
    font-size: clamp(10px, 14cqw, 16px);
  }

  .date-full {
    display: none;
  }

  .date-short {
    display: inline;
  }

  .seg-bar {
    width: 78cqw;
  }
}

/* Small quadrant (e.g. 2x2) */
@container hud-slot (max-width: 250px) and (max-height: 170px) {
  .tactical-tag {
    display: none;
  }
}
</style>
