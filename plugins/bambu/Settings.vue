<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import type {
  BambuConnectionState,
  BambuGcodeState,
  BambuPluginData,
  BambuSettings,
} from './types'
import { DEFAULT_BAMBU_SETTINGS } from './types'

interface BambuStatusResponse {
  connection_state?: BambuConnectionState
  connected?: boolean
  configured?: boolean
  mock_mode?: boolean
  printer_ip?: string
  printer_name?: string
  mqtt_backend?: string
  telemetry?: BambuPluginData
  last_update_at?: string | null
  error?: string | null
}

const props = defineProps<{
  modelValue?: Partial<BambuSettings>
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: BambuSettings): void
}>()

const current = computed<BambuSettings>(() => ({
  ...DEFAULT_BAMBU_SETTINGS,
  ...props.modelValue,
}))

function updateField<K extends keyof BambuSettings>(key: K, value: BambuSettings[K]) {
  emit('update:modelValue', {
    ...current.value,
    [key]: value,
  })
}

const showAccessCode = ref(false)
const statusLoading = ref(false)
const reconnecting = ref(false)
const statusState = ref<BambuConnectionState>('DISCONNECTED')
const statusTelemetry = ref<BambuPluginData | null>(null)
const statusError = ref('')
const statusBackend = ref('')

let statusPollTimer: ReturnType<typeof setInterval> | null = null

async function fetchWithPluginReload(url: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(url, init)
  if (res.status !== 404) {
    return res
  }
  const reloadRes = await fetch('/api/plugins/reload', { method: 'POST' })
  if (!reloadRes.ok) {
    return res
  }
  return fetch(url, init)
}

async function refreshStatus() {
  statusLoading.value = true
  try {
    const res = await fetchWithPluginReload('/api/plugins/bambu/status', { cache: 'no-store' })
    if (!res.ok) {
      throw new Error(`Status check failed (${res.status})`)
    }
    const payload = (await res.json()) as BambuStatusResponse
    const rawConn = String(payload.connection_state ?? 'DISCONNECTED').toUpperCase()
    if (
      rawConn === 'CONNECTED' ||
      rawConn === 'CONNECTING' ||
      rawConn === 'MOCK_ACTIVE' ||
      rawConn === 'DISCONNECTED'
    ) {
      statusState.value = rawConn
    } else {
      statusState.value = payload.mock_mode ? 'MOCK_ACTIVE' : payload.connected ? 'CONNECTED' : 'DISCONNECTED'
    }
    statusTelemetry.value = payload.telemetry ?? null
    statusBackend.value = payload.mqtt_backend ?? ''
    statusError.value = payload.error ? String(payload.error) : ''
  } catch (err) {
    statusError.value = err instanceof Error ? err.message : 'Unable to check Bambu printer status.'
  } finally {
    statusLoading.value = false
  }
}

async function saveAndReconnect() {
  statusError.value = ''
  reconnecting.value = true
  try {
    const saveRes = await fetch('/api/plugins/bambu/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        settings: {
          ...current.value,
        },
      }),
    })
    if (!saveRes.ok) {
      throw new Error(`Failed to save Bambu settings (${saveRes.status})`)
    }
    const recRes = await fetchWithPluginReload('/api/plugins/bambu/reconnect', { method: 'POST' })
    if (!recRes.ok) {
      throw new Error(`Reconnect failed (${recRes.status})`)
    }
    await refreshStatus()
  } catch (err) {
    statusError.value = err instanceof Error ? err.message : 'Unable to reconnect to Bambu printer.'
  } finally {
    reconnecting.value = false
  }
}

function handleWindowFocus() {
  void refreshStatus()
}

onMounted(() => {
  void refreshStatus()
  statusPollTimer = setInterval(() => {
    void refreshStatus()
  }, 3000)
  window.addEventListener('focus', handleWindowFocus)
})

onUnmounted(() => {
  if (statusPollTimer !== null) {
    clearInterval(statusPollTimer)
    statusPollTimer = null
  }
  window.removeEventListener('focus', handleWindowFocus)
})

const badgeLabel = computed(() => {
  if (statusLoading.value && !statusTelemetry.value) return 'CHECKING...'
  if (statusState.value === 'MOCK_ACTIVE') return 'MOCK ACTIVE'
  if (statusState.value === 'CONNECTED') return 'CONNECTED'
  if (statusState.value === 'CONNECTING') return 'CONNECTING'
  return 'DISCONNECTED'
})

const badgeClass = computed(() => {
  if (statusState.value === 'CONNECTED') {
    return 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300'
  }
  if (statusState.value === 'MOCK_ACTIVE') {
    return 'border-cyan-500/40 bg-cyan-500/15 text-cyan-200'
  }
  if (statusState.value === 'CONNECTING') {
    return 'border-amber-500/30 bg-amber-500/10 text-amber-300'
  }
  return 'border-rose-500/40 bg-rose-500/15 text-rose-200'
})

const mockStateOptions: Array<{ id: BambuGcodeState; label: string; desc: string }> = [
  { id: 'RUNNING', label: 'RUNNING', desc: 'Live progress tick' },
  { id: 'PREPARE', label: 'PREPARE', desc: 'Heating & leveling' },
  { id: 'PAUSE', label: 'PAUSE', desc: 'Amber alert pause' },
  { id: 'FINISH', label: 'FINISH', desc: '100% complete' },
  { id: 'FAILED', label: 'FAILED', desc: 'Error / runout alert' },
  { id: 'IDLE', label: 'IDLE', desc: 'Collapsed 1x1 standby' },
]

const displayToggles: Array<{ key: keyof BambuSettings; label: string }> = [
  { key: 'showTemperatures', label: 'Show Nozzle & Bed Temps' },
  { key: 'showChamberTemp', label: 'Show Chamber Temp' },
  { key: 'showSecondNozzle', label: 'Show 2nd Nozzle Temp (Dual-Extruder)' },
  { key: 'showLayerCount', label: 'Show Layer Count' },
  { key: 'showRemainingTime', label: 'Show Remaining Time' },
  { key: 'showPrintStage', label: 'Show Print Stage' },
  { key: 'showCornerBrackets', label: 'Show Corner Brackets' },
]

const triggerToggles: Array<{ key: keyof BambuSettings; label: string; desc: string }> = [
  {
    key: 'triggerOnPrintStart',
    label: 'Trigger on Print Start',
    desc: 'Surface when printer enters PREPARE or RUNNING',
  },
  {
    key: 'triggerWhilePrinting',
    label: 'Trigger While Printing',
    desc: 'Keep split screen active while preparing or printing',
  },
  {
    key: 'triggerOnPrintFinish',
    label: 'Trigger on Print Finish',
    desc: 'Pulse HUD briefly when print reaches FINISH',
  },
  {
    key: 'triggerOnErrorOrPause',
    label: 'Trigger on Pause / Error',
    desc: 'Surface alert on PAUSE, FAILED, or print_error != 0',
  },
]

const swatches = [
  { label: 'HUD Cyan', hex: '#00f0ff' },
  { label: 'Bambu Emerald', hex: '#10e18c' },
  { label: 'Amber', hex: '#f5a623' },
  { label: 'Crimson', hex: '#ff2a6d' },
  { label: 'Violet', hex: '#a855f7' },
  { label: 'Pure White', hex: '#f8fafc' },
]
</script>

<template>
  <div class="space-y-5 text-sm">
    <!-- Live Connection & Telemetry Status -->
    <div class="space-y-3 rounded-lg border border-slate-800 bg-slate-950/70 p-3.5">
      <div class="flex items-center justify-between gap-2">
        <span class="font-mono text-xs uppercase tracking-wider text-slate-400">
          LAN MQTT Link
        </span>
        <span
          class="rounded border px-2 py-0.5 font-mono text-[10px] font-semibold uppercase"
          :class="badgeClass"
        >
          {{ badgeLabel }}
        </span>
      </div>

      <div
        v-if="statusTelemetry && (statusState === 'CONNECTED' || statusState === 'MOCK_ACTIVE')"
        class="rounded border border-slate-800 bg-slate-900/70 px-2.5 py-2 font-mono text-[11px] text-slate-300"
      >
        <div class="flex items-center justify-between gap-2">
          <strong class="text-slate-100">{{ statusTelemetry.stage_label || statusTelemetry.gcode_state }}</strong>
          <span class="text-cyan-300">
            {{ statusTelemetry.mc_percent ?? 0 }}% · ETA {{ statusTelemetry.eta_display || '--' }}
          </span>
        </div>
        <div class="mt-1 flex items-center justify-between gap-2 text-[10px] text-slate-400">
          <span class="min-w-0 truncate">
            {{ statusTelemetry.subtask_name || 'No active file' }}
          </span>
          <span class="shrink-0">
            {{ statusTelemetry.has_second_nozzle ? 'N1' : 'N' }} {{ Math.round(statusTelemetry.nozzle_temper ?? 0) }}°<template v-if="statusTelemetry.has_second_nozzle"> · N2 {{ Math.round(statusTelemetry.nozzle2_temper ?? 0) }}°</template> · B {{ Math.round(statusTelemetry.bed_temper ?? 0) }}°<template v-if="statusTelemetry.has_chamber"> · C {{ Math.round(statusTelemetry.chamber_temper ?? 0) }}°</template>
          </span>
        </div>
      </div>

      <div
        v-else
        class="rounded border border-slate-800 bg-slate-900/70 px-2.5 py-2 text-[11px] text-slate-400"
      >
        {{
          current.printerIp && current.serialNumber && current.accessCode
            ? `Target ${current.printerIp}:8883 (${statusBackend || 'tls'})`
            : 'Enter Printer IP, Serial Number, and LAN Access Code, or enable Mock Mode.'
        }}
      </div>

      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          :disabled="reconnecting"
          class="flex-1 rounded-lg border border-cyan-500/40 bg-cyan-500/15 px-3 py-2 font-mono text-xs font-semibold text-cyan-200 transition hover:bg-cyan-500/20 disabled:opacity-50"
          @click="saveAndReconnect"
        >
          {{ reconnecting ? 'Applying...' : current.mockMode ? 'Apply Mock Mode' : 'Save & Reconnect' }}
        </button>
        <button
          type="button"
          :disabled="statusLoading"
          class="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 font-mono text-xs font-semibold text-slate-300 transition hover:border-cyan-500/50 hover:text-cyan-200 disabled:opacity-50"
          @click="refreshStatus"
        >
          {{ statusLoading ? '...' : 'Refresh' }}
        </button>
      </div>

      <p v-if="statusError" class="text-xs text-rose-400">
        {{ statusError }}
      </p>
    </div>

    <!-- LAN Connection Credentials -->
    <div class="space-y-3">
      <label class="block font-mono text-xs uppercase tracking-wider text-slate-400">
        LAN Connection
      </label>

      <div class="grid grid-cols-2 gap-2">
        <div>
          <label class="mb-1 block text-[11px] text-slate-400">Printer IP Address</label>
          <input
            :value="current.printerIp"
            type="text"
            autocomplete="off"
            placeholder="192.168.1.50"
            class="w-full rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 font-mono text-xs text-slate-100 placeholder-slate-500 focus:border-cyan-400/70 focus:outline-none"
            @input="updateField('printerIp', ($event.target as HTMLInputElement).value)"
          />
        </div>
        <div>
          <label class="mb-1 block text-[11px] text-slate-400">Printer Label</label>
          <input
            :value="current.printerName"
            type="text"
            autocomplete="off"
            placeholder="BAMBU LAB"
            class="w-full rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 font-mono text-xs text-slate-100 placeholder-slate-500 focus:border-cyan-400/70 focus:outline-none"
            @input="updateField('printerName', ($event.target as HTMLInputElement).value)"
          />
        </div>
      </div>

      <div>
        <label class="mb-1 block text-[11px] text-slate-400">Serial Number</label>
        <input
          :value="current.serialNumber"
          type="text"
          autocomplete="off"
          placeholder="01P00A000000000"
          class="w-full rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 font-mono text-xs text-slate-100 placeholder-slate-500 focus:border-cyan-400/70 focus:outline-none"
          @input="updateField('serialNumber', ($event.target as HTMLInputElement).value)"
        />
      </div>

      <div>
        <label class="mb-1 block text-[11px] text-slate-400">LAN Access Code</label>
        <div class="flex gap-2">
          <input
            :value="current.accessCode"
            :type="showAccessCode ? 'text' : 'password'"
            autocomplete="off"
            placeholder="8-character LAN Access Code"
            class="min-w-0 flex-1 rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 font-mono text-xs text-slate-100 placeholder-slate-500 focus:border-cyan-400/70 focus:outline-none"
            @input="updateField('accessCode', ($event.target as HTMLInputElement).value)"
          />
          <button
            type="button"
            class="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 font-mono text-[11px] text-slate-300 transition hover:border-cyan-500/50 hover:text-cyan-200"
            @click="showAccessCode = !showAccessCode"
          >
            {{ showAccessCode ? 'Hide' : 'Show' }}
          </button>
        </div>
        <p class="mt-1 text-[11px] text-slate-400">
          Connects locally over TLS port <code class="text-slate-200">8883</code> as user <code class="text-slate-200">bblp</code>. Enable LAN Only Mode on the printer.
        </p>
      </div>
    </div>

    <!-- Simulation / Testing -->
    <div class="space-y-2.5">
      <label class="block font-mono text-xs uppercase tracking-wider text-cyan-300">
        Simulation / Testing
      </label>

      <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <div>
          <div class="text-xs text-slate-200">Mock Mode</div>
          <div class="text-[11px] text-slate-400">Simulate live printer telemetry &amp; Dynamic Mode without a printer</div>
        </div>
        <input
          :checked="current.mockMode"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField('mockMode', ($event.target as HTMLInputElement).checked)"
        />
      </label>

      <div>
        <label class="mb-1.5 block text-[11px] text-slate-400">Simulated State</label>
        <div class="grid grid-cols-3 gap-2">
          <button
            v-for="opt in mockStateOptions"
            :key="opt.id"
            type="button"
            class="rounded-lg border p-2.5 text-left transition"
            :class="
              current.mockState === opt.id
                ? 'border-cyan-400/70 bg-cyan-500/15 text-cyan-100'
                : 'border-slate-800 bg-slate-950/70 text-slate-300 hover:border-slate-700'
            "
            @click="updateField('mockState', opt.id)"
          >
            <div class="font-mono text-xs font-semibold">{{ opt.label }}</div>
            <div class="mt-0.5 text-[10px] text-slate-400">{{ opt.desc }}</div>
          </button>
        </div>
      </div>
    </div>

    <!-- Display Elements -->
    <div class="space-y-2">
      <label class="block font-mono text-xs uppercase tracking-wider text-slate-400">
        Display Elements
      </label>

      <label
        v-for="item in displayToggles"
        :key="item.key"
        class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5"
      >
        <span class="text-xs text-slate-200">{{ item.label }}</span>
        <input
          :checked="Boolean(current[item.key])"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField(item.key, ($event.target as HTMLInputElement).checked)"
        />
      </label>
    </div>

    <!-- On-Event Trigger Conditions -->
    <div class="space-y-2">
      <label class="block font-mono text-xs uppercase tracking-wider text-amber-300">
        On-Event Trigger Conditions
      </label>
      <p class="text-[11px] text-slate-400">
        Automatically split the HUD when printing begins and collapse back to 1x1 when IDLE.
      </p>

      <label
        v-for="trig in triggerToggles"
        :key="trig.key"
        class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5"
      >
        <div>
          <div class="text-xs text-slate-200">{{ trig.label }}</div>
          <div class="text-[11px] text-slate-400">{{ trig.desc }}</div>
        </div>
        <input
          :checked="Boolean(current[trig.key])"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField(trig.key, ($event.target as HTMLInputElement).checked)"
        />
      </label>
    </div>

    <!-- Accent Color Picker -->
    <div>
      <label class="mb-2 block font-mono text-xs uppercase tracking-wider text-slate-400">
        Accent Color
      </label>
      <div class="flex flex-wrap items-center gap-2">
        <button
          v-for="swatch in swatches"
          :key="swatch.hex"
          type="button"
          :title="swatch.label"
          class="h-7 w-7 rounded-md border-2 transition"
          :class="
            current.accentColor.toLowerCase() === swatch.hex.toLowerCase()
              ? 'scale-110 border-white'
              : 'border-slate-700 hover:border-slate-400'
          "
          :style="{ backgroundColor: swatch.hex }"
          @click="updateField('accentColor', swatch.hex)"
        />
        <div class="ml-auto flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950 px-2.5 py-1">
          <input
            :value="current.accentColor"
            type="color"
            class="h-6 w-6 cursor-pointer border-0 bg-transparent p-0"
            @input="updateField('accentColor', ($event.target as HTMLInputElement).value)"
          />
          <input
            :value="current.accentColor"
            type="text"
            maxlength="7"
            class="w-20 bg-transparent font-mono text-xs text-slate-200 focus:outline-none"
            @change="updateField('accentColor', ($event.target as HTMLInputElement).value)"
          />
        </div>
      </div>
    </div>
  </div>
</template>
