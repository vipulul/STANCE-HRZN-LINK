<script setup lang="ts">
import { computed } from 'vue'
import type {
  BambuConnectionState,
  BambuGcodeState,
  BambuPluginData,
  BambuSettings,
} from './types'
import { DEFAULT_BAMBU_SETTINGS } from './types'

type ToneKind = 'accent' | 'ok' | 'warn' | 'err' | 'neutral'

interface TempItem {
  id: 'n1' | 'n2' | 'bed' | 'chamber'
  label: string
  compactKey: string
  shortKey: string
  full: string
  short: string
}

const props = withDefaults(
  defineProps<{
    settings?: Partial<BambuSettings>
    data?: BambuPluginData
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

const mergedSettings = computed<BambuSettings>(() => ({
  ...DEFAULT_BAMBU_SETTINGS,
  ...props.settings,
}))

function normalizeState(raw: unknown): BambuGcodeState {
  const val = String(raw ?? 'IDLE').trim().toUpperCase()
  if (val === 'SLICING' || val === 'INIT') return 'PREPARE'
  if (
    val === 'IDLE' ||
    val === 'PREPARE' ||
    val === 'RUNNING' ||
    val === 'PAUSE' ||
    val === 'FINISH' ||
    val === 'FAILED'
  ) {
    return val
  }
  return 'IDLE'
}

function buildMockPreviewFallback(state: BambuGcodeState): BambuPluginData {
  switch (state) {
    case 'PREPARE':
      return {
        connection_state: 'MOCK_ACTIVE',
        connected: true,
        mock_mode: true,
        gcode_state: 'PREPARE',
        mc_percent: 0,
        mc_remaining_time: 84,
        eta_display: '1h 24m',
        layer_num: 0,
        total_layer_num: 310,
        nozzle_temper: 220,
        nozzle_target_temper: 220,
        nozzle2_temper: 180,
        nozzle2_target_temper: 215,
        has_second_nozzle: true,
        bed_temper: 60,
        bed_target_temper: 60,
        chamber_temper: 34,
        chamber_target_temper: 45,
        has_chamber: true,
        subtask_name: 'HRZN01_Chassis_v4.3mf',
        stage_label: 'HEATING',
        print_error: 0,
        has_error: false,
      }
    case 'PAUSE':
      return {
        connection_state: 'MOCK_ACTIVE',
        connected: true,
        mock_mode: true,
        gcode_state: 'PAUSE',
        mc_percent: 68,
        mc_remaining_time: 18,
        eta_display: '18m',
        layer_num: 211,
        total_layer_num: 310,
        nozzle_temper: 220,
        nozzle_target_temper: 220,
        nozzle2_temper: 160,
        nozzle2_target_temper: 0,
        has_second_nozzle: true,
        bed_temper: 60,
        bed_target_temper: 60,
        chamber_temper: 39,
        chamber_target_temper: 45,
        has_chamber: true,
        subtask_name: 'HRZN01_Chassis_v4.3mf',
        stage_label: 'PAUSED',
        print_error: 0,
        has_error: false,
      }
    case 'FINISH':
      return {
        connection_state: 'MOCK_ACTIVE',
        connected: true,
        mock_mode: true,
        gcode_state: 'FINISH',
        mc_percent: 100,
        mc_remaining_time: 0,
        eta_display: '0m',
        layer_num: 310,
        total_layer_num: 310,
        nozzle_temper: 42,
        nozzle_target_temper: 0,
        nozzle2_temper: 38,
        nozzle2_target_temper: 0,
        has_second_nozzle: true,
        bed_temper: 36,
        bed_target_temper: 0,
        chamber_temper: 32,
        chamber_target_temper: 0,
        has_chamber: true,
        subtask_name: 'HRZN01_Chassis_v4.3mf',
        stage_label: 'COMPLETE',
        print_error: 0,
        has_error: false,
      }
    case 'FAILED':
      return {
        connection_state: 'MOCK_ACTIVE',
        connected: true,
        mock_mode: true,
        gcode_state: 'FAILED',
        mc_percent: 64,
        mc_remaining_time: 24,
        eta_display: '24m',
        layer_num: 198,
        total_layer_num: 310,
        nozzle_temper: 195,
        nozzle_target_temper: 0,
        nozzle2_temper: 150,
        nozzle2_target_temper: 0,
        has_second_nozzle: true,
        bed_temper: 58,
        bed_target_temper: 0,
        chamber_temper: 37,
        chamber_target_temper: 0,
        has_chamber: true,
        subtask_name: 'HRZN01_Chassis_v4.3mf',
        stage_label: 'FILAMENT RUNOUT',
        print_error: 50348044,
        has_error: true,
      }
    case 'IDLE':
      return {
        connection_state: 'MOCK_ACTIVE',
        connected: true,
        mock_mode: true,
        gcode_state: 'IDLE',
        mc_percent: 0,
        mc_remaining_time: 0,
        eta_display: '--',
        layer_num: 0,
        total_layer_num: 0,
        nozzle_temper: 28,
        nozzle_target_temper: 0,
        nozzle2_temper: 27,
        nozzle2_target_temper: 0,
        has_second_nozzle: true,
        bed_temper: 25,
        bed_target_temper: 0,
        chamber_temper: 24,
        chamber_target_temper: 0,
        has_chamber: true,
        subtask_name: '',
        stage_label: 'IDLE',
        print_error: 0,
        has_error: false,
      }
    case 'RUNNING':
    default:
      return {
        connection_state: 'MOCK_ACTIVE',
        connected: true,
        mock_mode: true,
        gcode_state: 'RUNNING',
        mc_percent: 48,
        mc_remaining_time: 34,
        eta_display: '34m',
        layer_num: 148,
        total_layer_num: 310,
        nozzle_temper: 220,
        nozzle_target_temper: 220,
        nozzle2_temper: 145,
        nozzle2_target_temper: 0,
        has_second_nozzle: true,
        bed_temper: 60,
        bed_target_temper: 60,
        chamber_temper: 38,
        chamber_target_temper: 45,
        has_chamber: true,
        subtask_name: 'HRZN01_Chassis_v4.3mf',
        stage_label: 'PRINTING',
        print_error: 0,
        has_error: false,
      }
  }
}

const effectiveData = computed<BambuPluginData>(() => {
  const incoming = props.data ?? {}
  if (mergedSettings.value.mockMode) {
    const desiredMockState = normalizeState(mergedSettings.value.mockState || 'RUNNING')
    if (!incoming.mock_mode || normalizeState(incoming.gcode_state) !== desiredMockState) {
      return buildMockPreviewFallback(desiredMockState)
    }
  }
  return incoming
})

const gcodeState = computed<BambuGcodeState>(() => normalizeState(effectiveData.value.gcode_state))

const connectionState = computed<BambuConnectionState>(() => {
  const raw = String(effectiveData.value.connection_state ?? 'DISCONNECTED').toUpperCase()
  if (raw === 'CONNECTED' || raw === 'CONNECTING' || raw === 'MOCK_ACTIVE') {
    return raw
  }
  return 'DISCONNECTED'
})

const isMock = computed<boolean>(() => Boolean(effectiveData.value.mock_mode || mergedSettings.value.mockMode))
const isConnected = computed<boolean>(() => Boolean(effectiveData.value.connected || isMock.value))
const printError = computed<number>(() => Number(effectiveData.value.print_error ?? 0) || 0)
const hasError = computed<boolean>(() => gcodeState.value === 'FAILED' || printError.value !== 0)

const printerLabel = computed<string>(() => {
  const custom = String(mergedSettings.value.printerName || '').trim()
  if (custom) return custom.toUpperCase()
  const fromData = String(effectiveData.value.printer_name || '').trim()
  return fromData ? fromData.toUpperCase() : 'BAMBU LAB'
})

const fileLabel = computed<string>(() => {
  const raw = String(effectiveData.value.subtask_name ?? '').trim()
  if (raw) return raw
  if (!isConnected.value && !mergedSettings.value.printerIp) return 'LAN NOT CONFIGURED'
  if (!isConnected.value) return 'LINK OFFLINE'
  return gcodeState.value === 'IDLE' ? 'READY TO PRINT' : 'ACTIVE JOB'
})

const progressPct = computed<number>(() => {
  if (gcodeState.value === 'IDLE') return 0
  if (gcodeState.value === 'FINISH') return 100
  const raw = Number(effectiveData.value.mc_percent ?? 0)
  if (!Number.isFinite(raw)) return 0
  return Math.max(0, Math.min(100, Math.round(raw)))
})

const stageLabel = computed<string>(() => {
  const raw = String(effectiveData.value.stage_label ?? '').trim().toUpperCase()
  if (raw) return raw
  if (gcodeState.value === 'FINISH') return 'COMPLETE'
  if (gcodeState.value === 'PAUSE') return 'PAUSED'
  if (gcodeState.value === 'FAILED') return 'FAILED'
  if (gcodeState.value === 'PREPARE') return 'PREPARING'
  if (gcodeState.value === 'RUNNING') return 'PRINTING'
  return isConnected.value ? 'IDLE' : 'OFFLINE'
})

const shortStageLabel = computed<string>(() => {
  const s = stageLabel.value
  if (s === 'BED LEVELING') return 'LEVELING'
  if (s === 'FILAMENT CHANGE') return 'FILAMENT'
  if (s === 'FILAMENT RUNOUT') return 'RUNOUT'
  if (s === 'CLEANING NOZZLE') return 'CLEANING'
  if (s === 'CALIBRATING FLOW') return 'CALIBRATING'
  return s
})

const etaText = computed<string>(() => {
  if (gcodeState.value === 'IDLE') return '--'
  const rawDisplay = String(effectiveData.value.eta_display ?? '').trim()
  if (rawDisplay) return rawDisplay
  const mins = Number(effectiveData.value.mc_remaining_time ?? 0)
  if (!Number.isFinite(mins) || mins < 0) return '--'
  const rounded = Math.round(mins)
  if (rounded >= 60) {
    const h = Math.floor(rounded / 60)
    const m = rounded % 60
    return m > 0 ? `${h}h ${m}m` : `${h}h`
  }
  return `${rounded}m`
})

const layerNum = computed<number>(() => Math.max(0, Math.round(Number(effectiveData.value.layer_num ?? 0) || 0)))
const totalLayerNum = computed<number>(() => Math.max(0, Math.round(Number(effectiveData.value.total_layer_num ?? 0) || 0)))

const layerText = computed<string>(() => {
  if (totalLayerNum.value > 0) {
    return `${layerNum.value} / ${totalLayerNum.value}`
  }
  return layerNum.value > 0 ? `${layerNum.value}` : '-- / --'
})

const compactLayerText = computed<string>(() => {
  if (totalLayerNum.value > 0) {
    return `${layerNum.value}/${totalLayerNum.value}`
  }
  return layerNum.value > 0 ? `${layerNum.value}` : '--'
})

const hasSecondNozzle = computed<boolean>(
  () =>
    Boolean(effectiveData.value.has_second_nozzle) ||
    (effectiveData.value.nozzle2_temper !== undefined && effectiveData.value.nozzle2_temper !== null),
)

const hasChamber = computed<boolean>(
  () =>
    Boolean(effectiveData.value.has_chamber) ||
    (effectiveData.value.chamber_temper !== undefined && effectiveData.value.chamber_temper !== null),
)

const showSecondNozzleRow = computed<boolean>(() => Boolean(mergedSettings.value.showSecondNozzle && hasSecondNozzle.value))
const showChamberRow = computed<boolean>(() => Boolean(mergedSettings.value.showChamberTemp && hasChamber.value))

const tempItems = computed<TempItem[]>(() => {
  if (!mergedSettings.value.showTemperatures) return []

  const items: TempItem[] = []
  const d = effectiveData.value
  const dual = showSecondNozzleRow.value

  const n1Cur = Number(d.nozzle_temper ?? 0)
  const n1Tgt = Number(d.nozzle_target_temper ?? 0)
  const n1Offline = !isConnected.value && n1Cur <= 0 && n1Tgt <= 0
  items.push({
    id: 'n1',
    label: dual ? 'NOZZLE 1' : 'NOZZLE',
    compactKey: dual ? 'N1' : 'NOZ',
    shortKey: dual ? 'N1' : 'N',
    full: n1Offline ? '--°/--°' : `${Math.round(n1Cur)}°/${Math.round(n1Tgt)}°`,
    short: n1Offline ? '--°' : `${Math.round(n1Cur)}°`,
  })

  if (dual) {
    const n2Cur = d.nozzle2_temper
    const n2Tgt = d.nozzle2_target_temper
    const hasN2 = n2Cur !== undefined && n2Cur !== null
    const curVal = hasN2 ? Number(n2Cur) : 0
    const tgtVal = n2Tgt !== undefined && n2Tgt !== null ? Number(n2Tgt) : 0
    items.push({
      id: 'n2',
      label: 'NOZZLE 2',
      compactKey: 'N2',
      shortKey: 'N2',
      full: !hasN2 ? '--°/--°' : `${Math.round(curVal)}°/${Math.round(tgtVal)}°`,
      short: !hasN2 ? '--°' : `${Math.round(curVal)}°`,
    })
  }

  const bCur = Number(d.bed_temper ?? 0)
  const bTgt = Number(d.bed_target_temper ?? 0)
  const bOffline = !isConnected.value && bCur <= 0 && bTgt <= 0
  items.push({
    id: 'bed',
    label: 'BED',
    compactKey: 'BED',
    shortKey: 'B',
    full: bOffline ? '--°/--°' : `${Math.round(bCur)}°/${Math.round(bTgt)}°`,
    short: bOffline ? '--°' : `${Math.round(bCur)}°`,
  })

  if (showChamberRow.value) {
    const cCur = d.chamber_temper
    const cTgt = d.chamber_target_temper
    const hasC = cCur !== undefined && cCur !== null
    const cCurNum = hasC ? Number(cCur) : 0
    const cTgtNum = cTgt !== undefined && cTgt !== null ? Number(cTgt) : 0
    items.push({
      id: 'chamber',
      label: 'CHAMBER',
      compactKey: 'CHM',
      shortKey: 'C',
      full: !hasC
        ? '--°'
        : cTgtNum > 0
          ? `${Math.round(cCurNum)}°/${Math.round(cTgtNum)}°`
          : `${Math.round(cCurNum)}°`,
      short: !hasC ? '--°' : `${Math.round(cCurNum)}°`,
    })
  }

  return items
})

const statusTone = computed<ToneKind>(() => {
  if (hasError.value) return 'err'
  if (gcodeState.value === 'PAUSE') return 'warn'
  if (gcodeState.value === 'FINISH') return 'ok'
  if (gcodeState.value === 'RUNNING' || gcodeState.value === 'PREPARE') return 'accent'
  if (!isConnected.value && connectionState.value === 'DISCONNECTED') return 'neutral'
  return 'neutral'
})

const showCenterPercent = computed<boolean>(() => gcodeState.value !== 'IDLE')
const centerReadout = computed<string>(() => {
  if (gcodeState.value !== 'IDLE') return `${progressPct.value}%`
  return isConnected.value ? 'IDLE' : 'OFF'
})

const arcRadius = 48
const arcCircumference = 2 * Math.PI * arcRadius
const arcDashOffset = computed<number>(() => {
  const ratio = gcodeState.value === 'IDLE' ? 0 : progressPct.value / 100
  return arcCircumference * (1 - Math.max(0, Math.min(1, ratio)))
})
const tickAngles = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]
</script>

<template>
  <div
    class="bambu-widget"
    :class="[`tone-root-${statusTone}`, { 'is-alert': statusTone === 'warn' || statusTone === 'err' }]"
    :style="{ '--bambu-accent': mergedSettings.accentColor || '#00f0ff' }"
  >
    <!-- Tactical corner reticles (hidden in ultra-shallow or narrow strips via @container) -->
    <template v-if="mergedSettings.showCornerBrackets">
      <span class="reticle reticle-tl" aria-hidden="true" />
      <span class="reticle reticle-tr" aria-hidden="true" />
      <span class="reticle reticle-bl" aria-hidden="true" />
      <span class="reticle reticle-br" aria-hidden="true" />
    </template>

    <!-- Medium & Full Slot Layout -->
    <div class="bambu-full">
      <header class="bambu-header">
        <div class="header-id">
          <span class="status-dot" :class="`dot-${statusTone}`" />
          <span class="printer-name">{{ printerLabel }}</span>
          <span v-if="isMock" class="mock-pill">MOCK</span>
        </div>

        <span
          v-if="mergedSettings.showPrintStage"
          class="stage-badge"
          :class="`badge-${statusTone}`"
        >
          {{ stageLabel }}
        </span>
      </header>

      <div class="bambu-body">
        <!-- Radial Progress Gauge -->
        <div class="ring-panel">
          <div class="ring-box">
            <svg class="ring-svg" viewBox="0 0 120 120" aria-hidden="true">
              <circle
                class="ring-track"
                cx="60"
                cy="60"
                :r="arcRadius"
                fill="none"
                stroke-width="8"
              />
              <g class="ring-ticks">
                <line
                  v-for="angle in tickAngles"
                  :key="angle"
                  x1="60"
                  y1="4"
                  x2="60"
                  y2="9"
                  stroke-width="1.5"
                  :transform="`rotate(${angle} 60 60)`"
                />
              </g>
              <circle
                class="ring-progress"
                :class="`stroke-${statusTone}`"
                cx="60"
                cy="60"
                :r="arcRadius"
                fill="none"
                stroke-width="8"
                stroke-linecap="round"
                :stroke-dasharray="arcCircumference"
                :stroke-dashoffset="arcDashOffset"
                transform="rotate(-90 60 60)"
              />
            </svg>
            <div class="ring-center">
              <span
                class="ring-pct"
                :class="[`text-${statusTone}`, { 'is-word': !showCenterPercent }]"
              >
                {{ centerReadout }}
              </span>
            </div>
          </div>
        </div>

        <!-- Job Meta, Layer Count, ETA & Dynamic Temperatures -->
        <div class="info-panel">
          <div class="job-title" :title="fileLabel">{{ fileLabel }}</div>

          <div
            v-if="mergedSettings.showLayerCount || mergedSettings.showRemainingTime"
            class="meta-row"
          >
            <div v-if="mergedSettings.showLayerCount" class="meta-cell">
              <span class="meta-k">L</span>
              <span class="meta-v">{{ layerText }}</span>
            </div>
            <div v-if="mergedSettings.showRemainingTime" class="meta-cell meta-eta">
              <span class="meta-k">ETA</span>
              <span class="meta-v" :class="`text-${statusTone}`">{{ etaText }}</span>
            </div>
          </div>

          <div
            v-if="tempItems.length > 0"
            class="temp-grid"
            :class="`temp-count-${tempItems.length}`"
          >
            <div v-for="item in tempItems" :key="item.id" class="temp-tile">
              <span class="temp-k temp-k-full">{{ item.label }}</span>
              <span class="temp-k temp-k-short">{{ item.shortKey }}</span>
              <span class="temp-v temp-v-full">{{ item.full }}</span>
              <span class="temp-v temp-v-short">{{ item.short }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Segmented Linear Progress Bar -->
      <div
        class="progress-track"
        :class="`border-${statusTone}`"
        role="progressbar"
        :aria-valuenow="progressPct"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        <div
          class="progress-fill"
          :class="`fill-${statusTone}`"
          :style="{ width: `${progressPct}%` }"
        />
        <div class="progress-ticks" aria-hidden="true" />
      </div>
    </div>

    <!-- Compact / Split Slot Layout (1x2, 2-big-1-small compact, 3x1/4x1 strips) -->
    <div class="bambu-compact">
      <!-- Left: Radial Ring -->
      <div class="compact-ring-wrap">
        <svg class="compact-ring-svg" viewBox="0 0 120 120" aria-hidden="true">
          <circle
            class="ring-track"
            cx="60"
            cy="60"
            :r="arcRadius"
            fill="none"
            stroke-width="10"
          />
          <circle
            class="ring-progress"
            :class="`stroke-${statusTone}`"
            cx="60"
            cy="60"
            :r="arcRadius"
            fill="none"
            stroke-width="10"
            stroke-linecap="round"
            :stroke-dasharray="arcCircumference"
            :stroke-dashoffset="arcDashOffset"
            transform="rotate(-90 60 60)"
          />
        </svg>
        <div class="compact-ring-center">
          <span
            class="compact-pct"
            :class="[`text-${statusTone}`, { 'is-word': !showCenterPercent }]"
          >
            {{ centerReadout }}
          </span>
        </div>
      </div>

      <!-- Center: Stage Text on Top, Temps Stacked Directly Underneath -->
      <div class="compact-center">
        <div class="compact-text-block">
          <div v-if="mergedSettings.showPrintStage" class="compact-stage-row">
            <span class="status-dot" :class="`dot-${statusTone}`" />
            <span class="compact-stage-full" :class="`text-${statusTone}`">{{ stageLabel }}</span>
            <span class="compact-stage-short" :class="`text-${statusTone}`">{{ shortStageLabel }}</span>
          </div>
          <div v-if="fileLabel" class="compact-file" :title="fileLabel">{{ fileLabel }}</div>
        </div>

        <div v-if="tempItems.length > 0" class="compact-temps-row">
          <div
            v-for="item in tempItems"
            :key="item.id"
            class="compact-temp-chip"
            :class="`pill-${statusTone}`"
          >
            <span class="chip-full">{{ item.compactKey }} {{ item.full }}</span>
            <span class="chip-short">{{ item.shortKey }} {{ item.short }}</span>
          </div>
        </div>
      </div>

      <!-- Right: ETA (and optional Layer Count underneath) -->
      <div
        v-if="mergedSettings.showRemainingTime || mergedSettings.showLayerCount"
        class="compact-right"
      >
        <div v-if="mergedSettings.showRemainingTime" class="compact-eta-block">
          <span class="compact-eta-k">ETA</span>
          <span class="compact-eta-v" :class="`text-${statusTone}`">{{ etaText }}</span>
        </div>
        <div v-if="mergedSettings.showLayerCount" class="compact-layer">
          L {{ compactLayerText }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bambu-widget {
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

/* Corner reticles */
.reticle {
  position: absolute;
  width: clamp(7px, 3.4cqmin, 13px);
  height: clamp(7px, 3.4cqmin, 13px);
  border-color: var(--bambu-accent);
  pointer-events: none;
  opacity: 0.9;
  z-index: 2;
}

.bambu-widget.tone-root-warn .reticle {
  border-color: #fde047;
}

.bambu-widget.tone-root-err .reticle {
  border-color: #ff6b8b;
}

.bambu-widget.tone-root-ok .reticle {
  border-color: #34f5a8;
}

.reticle-tl {
  top: 5px;
  left: 5px;
  border-top: 2px solid;
  border-left: 2px solid;
}

.reticle-tr {
  top: 5px;
  right: 5px;
  border-top: 2px solid;
  border-right: 2px solid;
}

.reticle-bl {
  bottom: 5px;
  left: 5px;
  border-bottom: 2px solid;
  border-left: 2px solid;
}

.reticle-br {
  bottom: 5px;
  right: 5px;
  border-bottom: 2px solid;
  border-right: 2px solid;
}

/* Semantic High-Contrast Colors (>= 7:1 on #000000) */
.text-accent {
  color: var(--bambu-accent);
}

.text-ok {
  color: #34f5a8;
}

.text-warn {
  color: #fde047;
}

.text-err {
  color: #ff6b8b;
}

.text-neutral {
  color: #e2e8f0;
}

.stroke-accent {
  stroke: var(--bambu-accent);
}

.stroke-ok {
  stroke: #34f5a8;
}

.stroke-warn {
  stroke: #fde047;
}

.stroke-err {
  stroke: #ff6b8b;
}

.stroke-neutral {
  stroke: #cbd5e1;
}

.fill-accent {
  background: var(--bambu-accent);
}

.fill-ok {
  background: #34f5a8;
}

.fill-warn {
  background: #fde047;
}

.fill-err {
  background: #ff6b8b;
}

.fill-neutral {
  background: #cbd5e1;
}

.dot-accent {
  background: var(--bambu-accent);
  box-shadow: 0 0 8px var(--bambu-accent);
}

.dot-ok {
  background: #34f5a8;
  box-shadow: 0 0 8px #34f5a8;
}

.dot-warn {
  background: #fde047;
  box-shadow: 0 0 8px #fde047;
}

.dot-err {
  background: #ff6b8b;
  box-shadow: 0 0 8px #ff6b8b;
}

.dot-neutral {
  background: #cbd5e1;
}

/* Medium / Full Slot View */
.bambu-full {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  width: 100%;
  height: 100%;
  gap: clamp(4px, 2.2cqh, 12px);
}

.bambu-header {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: clamp(4px, 1.8cqh, 8px);
  min-height: calc(clamp(12px, 6cqh, 22px) + clamp(4px, 1.8cqh, 8px) + 1px);
  border-bottom: 1px solid color-mix(in srgb, var(--bambu-accent) 42%, #334155);
  flex-shrink: 0;
  min-width: 0;
}

.bambu-widget.tone-root-warn .bambu-header {
  border-bottom-color: #fde047;
}

.bambu-widget.tone-root-err .bambu-header {
  border-bottom-color: #ff6b8b;
}

.header-id {
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

.printer-name {
  font-size: clamp(9px, min(3.4cqw, 5cqh), 13px);
  font-weight: 700;
  letter-spacing: 0.11em;
  color: #ffffff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mock-pill {
  font-size: clamp(7.5px, min(2.2cqw, 3.6cqh), 10px);
  font-weight: 700;
  line-height: 1;
  letter-spacing: 0.08em;
  color: var(--bambu-accent);
  border: 1px solid var(--bambu-accent);
  border-radius: 3px;
  padding: 1px 4px;
  flex-shrink: 0;
}

.stage-badge {
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

.badge-accent {
  color: var(--bambu-accent);
}

.badge-ok {
  color: #34f5a8;
}

.badge-warn {
  color: #fde047;
  box-shadow: 0 0 8px rgba(253, 224, 71, 0.28);
}

.badge-err {
  color: #ff6b8b;
  box-shadow: 0 0 8px rgba(255, 107, 139, 0.35);
}

.badge-neutral {
  color: #e2e8f0;
}

.bambu-body {
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: clamp(8px, 3cqw, 18px);
}

.ring-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  height: 100%;
  max-height: min(62cqh, 40cqw);
}

.ring-box {
  position: relative;
  height: 100%;
  aspect-ratio: 1 / 1;
  max-width: min(38cqw, 60cqh);
  max-height: min(38cqw, 60cqh);
  display: flex;
  align-items: center;
  justify-content: center;
}

.ring-svg {
  width: 100%;
  height: 100%;
  display: block;
}

.ring-track {
  stroke: #1e293b;
}

.ring-ticks line {
  stroke: #475569;
}

.ring-progress {
  transition: stroke-dashoffset 0.35s ease;
}

.ring-center {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}

.ring-pct {
  font-size: clamp(14px, min(7.2cqw, 14cqh), 38px);
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1;
}

.ring-pct.is-word {
  font-size: clamp(11px, min(5cqw, 9.5cqh), 24px);
  letter-spacing: 0.06em;
}

.info-panel {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: clamp(4px, 2.2cqh, 11px);
}

.job-title {
  font-size: clamp(10px, min(4.1cqw, 6.8cqh), 18px);
  font-weight: 700;
  color: #ffffff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.meta-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: clamp(4px, 1.8cqw, 12px);
}

.meta-cell {
  display: flex;
  align-items: baseline;
  gap: clamp(3px, 1cqw, 6px);
  min-width: 0;
}

.meta-k {
  font-size: clamp(9px, min(2.8cqw, 4.6cqh), 13px);
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #cbd5e1;
}

.meta-v {
  font-size: clamp(11px, min(4cqw, 6.8cqh), 20px);
  font-weight: 700;
  color: #ffffff;
  white-space: nowrap;
}

.temp-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: clamp(3px, 1.4cqw, 9px);
}

@container hud-slot (min-width: 281px) {
  .temp-grid.temp-count-3 {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

.temp-tile {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  padding: clamp(2px, 1.3cqh, 7px) clamp(4px, 1.6cqw, 9px);
  border: 1px solid color-mix(in srgb, var(--bambu-accent) 36%, #334155);
  border-radius: 4px;
  background: #000000;
}

.bambu-widget.tone-root-warn .temp-tile {
  border-color: #fde047;
}

.bambu-widget.tone-root-err .temp-tile {
  border-color: #ff6b8b;
}

.temp-k {
  font-size: clamp(8px, min(2.3cqw, 3.8cqh), 11px);
  font-weight: 700;
  letter-spacing: 0.07em;
  color: #cbd5e1;
  white-space: nowrap;
}

.temp-k-short {
  display: none;
}

.temp-v {
  font-size: clamp(10px, min(3.2cqw, 5.6cqh), 16px);
  font-weight: 700;
  color: #ffffff;
  white-space: nowrap;
}

.temp-v-short {
  display: none;
}

/* Footer Linear Progress Bar */
.progress-track {
  position: relative;
  width: 100%;
  height: clamp(6px, 2.6cqh, 11px);
  background: #1e293b;
  border: 1px solid color-mix(in srgb, var(--bambu-accent) 40%, #334155);
  border-radius: 3px;
  overflow: hidden;
  flex-shrink: 0;
}

.progress-track.border-warn {
  border-color: #fde047;
}

.progress-track.border-err {
  border-color: #ff6b8b;
}

.progress-track.border-ok {
  border-color: #34f5a8;
}

.progress-fill {
  height: 100%;
  transition: width 0.35s ease;
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

/* Medium-narrow slots (e.g. 2x2 at 239x159, 3x1 at 158x320, 2x1 at 159x240) */
@container hud-slot (max-width: 265px) {
  .temp-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: clamp(2px, 1cqh, 5px);
  }

  .temp-tile {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    gap: 3px;
    padding: clamp(2px, 1cqh, 5px) clamp(4px, 1.4cqw, 7px);
  }

  .temp-k-full {
    display: none;
  }

  .temp-k-short {
    display: inline;
  }

  .temp-v {
    font-size: clamp(9px, min(3.8cqw, 5cqh), 13px);
  }
}

@container hud-slot (max-width: 205px) {
  .bambu-body {
    flex-direction: column;
    justify-content: center;
    gap: clamp(4px, 2cqh, 10px);
  }

  .ring-panel {
    height: auto;
    max-height: none;
  }

  .ring-box {
    width: min(60cqw, 34cqh);
    height: min(60cqw, 34cqh);
    max-width: none;
    max-height: none;
  }

  .ring-pct {
    font-size: clamp(16px, min(14cqw, 9cqh), 32px);
  }

  .info-panel {
    width: 100%;
    flex: 0 1 auto;
    gap: clamp(3px, 1.5cqh, 7px);
  }

  .job-title {
    text-align: center;
    font-size: clamp(10px, 6.2cqw, 14px);
  }

  .meta-row {
    justify-content: space-between;
  }

  .meta-k {
    font-size: clamp(8px, 4.8cqw, 11px);
  }

  .meta-v {
    font-size: clamp(10px, 5.8cqw, 15px);
  }

  .temp-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .temp-k {
    font-size: clamp(8px, 4.5cqw, 10px);
  }

  .temp-v {
    font-size: clamp(10px, 5.5cqw, 14px);
  }
}

/* Shallow medium height slots (e.g. 2x2 at 239x159) */
@container hud-slot (max-height: 175px) {
  .bambu-full {
    gap: clamp(3px, 1.8cqh, 7px);
  }

  .info-panel {
    gap: clamp(2px, 1.4cqh, 6px);
  }

  .job-title {
    line-height: 1.2;
  }

  .ring-box {
    max-width: min(34cqw, 54cqh);
    max-height: min(34cqw, 54cqh);
  }
}

@container hud-slot (max-width: 265px) and (max-height: 175px) {
  .temp-grid.temp-count-3 .temp-v-full,
  .temp-grid.temp-count-4 .temp-v-full {
    display: none;
  }

  .temp-grid.temp-count-3 .temp-v-short,
  .temp-grid.temp-count-4 .temp-v-short {
    display: inline;
  }
}

/* Compact / Split View (hidden in full/square slots) */
.bambu-compact {
  display: none;
  width: 100%;
  height: 100%;
  align-items: center;
  justify-content: space-between;
  gap: clamp(6px, 2.6cqw, 16px);
}

.compact-ring-wrap {
  position: relative;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.compact-ring-svg {
  width: 100%;
  height: 100%;
  display: block;
}

.compact-ring-center {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}

.compact-pct {
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1;
}

.compact-center {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: clamp(4px, 3cqh, 9px);
}

.compact-text-block {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.compact-stage-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.compact-stage-full {
  font-weight: 700;
  letter-spacing: 0.06em;
  line-height: 1.15;
  white-space: normal;
  word-break: break-word;
}

.compact-stage-short {
  display: none;
  font-weight: 700;
  letter-spacing: 0.08em;
  white-space: nowrap;
}

.compact-file {
  display: none;
  font-size: clamp(9px, min(8cqh, 2.7cqw), 12px);
  font-weight: 600;
  color: #cbd5e1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.compact-temps-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: clamp(3px, 1.2cqw, 7px);
  min-width: 0;
}

.compact-temp-chip {
  border: 1px solid color-mix(in srgb, var(--bambu-accent) 52%, #475569);
  border-radius: 4px;
  background: #000000;
  color: #ffffff;
  font-weight: 700;
  white-space: nowrap;
  padding: clamp(1px, 1.2cqh, 4px) clamp(5px, 1.4cqw, 8px);
  line-height: 1.15;
}

.compact-temp-chip.pill-warn {
  border-color: #fde047;
  color: #fde047;
}

.compact-temp-chip.pill-err {
  border-color: #ff6b8b;
  color: #ff6b8b;
}

.compact-temp-chip.pill-ok {
  border-color: #34f5a8;
}

.chip-short {
  display: none;
}

.compact-right {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  justify-content: center;
  gap: 2px;
  text-align: right;
}

.compact-eta-block {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  line-height: 1.05;
}

.compact-eta-k {
  font-size: clamp(8px, min(7cqh, 2.3cqw), 11px);
  font-weight: 700;
  letter-spacing: 0.09em;
  color: #cbd5e1;
}

.compact-eta-v {
  font-size: clamp(13px, min(18cqh, 4.8cqw), 24px);
  font-weight: 800;
  letter-spacing: -0.02em;
  white-space: nowrap;
}

.compact-layer {
  font-size: clamp(9px, min(8.5cqh, 2.6cqw), 12px);
  font-weight: 700;
  color: #e2e8f0;
  white-space: nowrap;
}

/* Wide-shallow / top-bottom split slots:
   1x2 at 480x320 (480x159), 1x2 at 320x240 (320x119), 2-big-1-small compact (480x115 / 320x86), Settings preview (380x144) */
@container hud-slot (max-height: 165px) and (min-width: 260px) {
  .bambu-full {
    display: none;
  }

  .bambu-widget {
    padding: clamp(6px, 5cqh, 12px) clamp(10px, 3cqw, 18px);
  }

  .bambu-compact {
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    gap: clamp(8px, 2.8cqw, 16px);
  }

  .compact-ring-wrap {
    height: min(76cqh, 22cqw);
    width: min(76cqh, 22cqw);
  }

  .compact-pct {
    font-size: clamp(13px, min(20cqh, 6.2cqw), 26px);
  }

  .compact-pct.is-word {
    font-size: clamp(10px, min(14cqh, 4.6cqw), 18px);
  }

  .compact-stage-full {
    font-size: clamp(11px, min(12cqh, 3.6cqw), 17px);
  }

  .compact-temp-chip {
    font-size: clamp(10px, min(9.5cqh, 2.9cqw), 13px);
  }
}

@container hud-slot (min-height: 136px) and (max-height: 165px) and (min-width: 260px) {
  .compact-file {
    display: block;
  }
}

@container hud-slot (max-height: 135px) {
  .bambu-full {
    display: none;
  }

  .bambu-widget {
    padding: clamp(4px, 4cqh, 10px) clamp(8px, 3cqw, 16px);
  }

  .bambu-compact {
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    gap: clamp(8px, 2.6cqw, 16px);
  }

  .compact-ring-wrap {
    height: min(80cqh, 22cqw);
    width: min(80cqh, 22cqw);
  }

  .compact-pct {
    font-size: clamp(12px, min(21cqh, 6.2cqw), 24px);
  }

  .compact-pct.is-word {
    font-size: clamp(10px, min(15cqh, 4.6cqw), 17px);
  }

  .compact-center {
    gap: clamp(3px, 3.2cqh, 7px);
  }

  .compact-stage-full {
    font-size: clamp(10px, min(13cqh, 3.5cqw), 15px);
  }

  .compact-temp-chip {
    font-size: clamp(9px, min(11cqh, 3cqw), 12px);
  }

  .chip-full {
    display: none;
  }

  .chip-short {
    display: inline;
  }
}

@container hud-slot (max-width: 389px) and (max-height: 165px) {
  .chip-full {
    display: none;
  }

  .chip-short {
    display: inline;
  }
}

@container hud-slot (max-height: 110px) {
  .reticle {
    display: none;
  }
}

/* Narrow vertical strips (4x1 at 480x320, 3x1/4x1 at 320x240) */
@container hud-slot (max-width: 155px) {
  .reticle,
  .bambu-full {
    display: none;
  }

  .bambu-widget {
    padding: clamp(6px, 4cqw, 12px) clamp(4px, 3cqw, 10px);
  }

  .bambu-compact {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    gap: clamp(6px, 3.5cqh, 14px);
  }

  .compact-ring-wrap {
    width: min(74cqw, 34cqh);
    height: min(74cqw, 34cqh);
  }

  .compact-pct {
    font-size: clamp(14px, min(20cqw, 10cqh), 28px);
  }

  .compact-pct.is-word {
    font-size: clamp(11px, min(15cqw, 7.5cqh), 20px);
  }

  .compact-center {
    flex: 0 1 auto;
    align-items: center;
    gap: clamp(5px, 2.5cqh, 10px);
    width: 100%;
  }

  .compact-text-block {
    align-items: center;
    width: 100%;
  }

  .compact-stage-row {
    justify-content: center;
  }

  .compact-stage-full {
    display: none;
  }

  .compact-stage-short {
    display: inline;
    font-size: clamp(9px, 8.5cqw, 13px);
  }

  .compact-file {
    display: none;
  }

  .compact-temps-row {
    justify-content: center;
    gap: 3px;
  }

  .compact-temp-chip {
    font-size: clamp(8px, 7.8cqw, 12px);
    padding: 2px 5px;
  }

  .chip-full {
    display: none;
  }

  .chip-short {
    display: inline;
  }

  .compact-right {
    align-items: center;
    text-align: center;
    width: 100%;
  }

  .compact-eta-block {
    flex-direction: row;
    align-items: baseline;
    gap: 4px;
  }

  .compact-eta-k {
    font-size: clamp(8px, 7.5cqw, 11px);
  }

  .compact-eta-v {
    font-size: clamp(11px, 11cqw, 16px);
  }

  .compact-layer {
    display: none;
  }
}
</style>
