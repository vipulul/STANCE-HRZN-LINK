<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import type { DeviceStatus, FlapState, HrznConfig, StateSnapshot } from './types/hrzn'

const uiConnected = ref(false)
const saving = ref(false)
const statusMessage = ref<string | null>(null)
const showMirroredPreview = ref(false)
const previewDataUrl = ref<string>('/api/preview.png')

const config = reactive<HrznConfig>({
  servo_closed_us: 1000,
  servo_open_us: 2000,
  sweep_duration_ms: 800,
  settle_detach_ms: 250,
  brightness: 200,
  flap_state: 'open',
  target_angle_pct: 100,
  mirror_vertical: true,
  frame_format: 'RGB565',
  target_fps: 2.0,
  hud_title: 'STANCE // HRZN-01',
  hud_subtitle: 'OPTICAL HUD LINK',
})

const device = reactive<DeviceStatus>({
  connected: false,
  device_id: null,
  hw_version: 'HRZN-01',
  fw_version: null,
  display_width: 320,
  display_height: 240,
  uptime_s: 0,
  rssi_dbm: null,
  free_heap: null,
  flap_position_pct: 0,
  servo_us: 1000,
  servo_attached: false,
  brightness: 200,
  fps: 0,
  last_seen: null,
})

let socket: WebSocket | null = null
let reconnectTimer: number | null = null
let statusTimer: number | null = null
const hasUnsavedConfig = ref(false)

const estimatedPulseUs = computed(() => {
  const span = config.servo_open_us - config.servo_closed_us
  return Math.round(config.servo_closed_us + (span * config.target_angle_pct) / 100)
})

const brightnessPct = computed(() => Math.round((config.brightness / 255) * 100))

const formattedUptime = computed(() => {
  const s = device.uptime_s
  const hrs = Math.floor(s / 3600)
  const mins = Math.floor((s % 3600) / 60)
  const secs = s % 60
  return `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
})

function flashStatus(msg: string) {
  statusMessage.value = msg
  if (statusTimer !== null) {
    window.clearTimeout(statusTimer)
  }
  statusTimer = window.setTimeout(() => {
    statusMessage.value = null
  }, 2500)
}

function applySnapshot(snapshot: StateSnapshot) {
  if (snapshot.config) {
    if (!hasUnsavedConfig.value) {
      Object.assign(config, snapshot.config)
    } else {
      config.flap_state = snapshot.config.flap_state
      config.target_angle_pct = snapshot.config.target_angle_pct
      config.brightness = snapshot.config.brightness
    }
  }
  if (snapshot.device) {
    Object.assign(device, snapshot.device)
  }
  if (snapshot.preview_data_url) {
    previewDataUrl.value = snapshot.preview_data_url
  }
}

async function fetchInitialState() {
  try {
    const res = await fetch('/api/state')
    if (res.ok) {
      const data = (await res.json()) as StateSnapshot
      applySnapshot(data)
    }
  } catch {
    // WebSocket reconnect handles recovery
  }
}

function connectUiSocket() {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${window.location.host}/ws/ui`
  socket = new WebSocket(url)

  socket.onopen = () => {
    uiConnected.value = true
  }

  socket.onmessage = (event: MessageEvent<string>) => {
    try {
      const data = JSON.parse(event.data) as StateSnapshot
      applySnapshot(data)
    } catch {
      // Ignore malformed frames
    }
  }

  socket.onclose = () => {
    uiConnected.value = false
    socket = null
    reconnectTimer = window.setTimeout(connectUiSocket, 2500)
  }

  socket.onerror = () => {
    socket?.close()
  }
}

async function sendFlapMove(state: FlapState, positionPct?: number) {
  const targetPct =
    state === 'open' ? 100 : state === 'closed' ? 0 : (positionPct ?? config.target_angle_pct)

  config.flap_state = state
  config.target_angle_pct = targetPct

  try {
    const res = await fetch('/api/flap', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        state,
        position_pct: targetPct,
        duration_ms: config.sweep_duration_ms,
      }),
    })
    if (res.ok) {
      flashStatus(`Flap -> ${state.toUpperCase()} (${targetPct}%)`)
    }
  } catch {
    flashStatus('Failed to send flap command')
  }
}

async function sendBrightness(brightness: number) {
  config.brightness = brightness
  try {
    const res = await fetch('/api/brightness', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ brightness }),
    })
    if (res.ok) {
      flashStatus(`Brightness set to ${brightness}/255`)
    }
  } catch {
    flashStatus('Failed to update brightness')
  }
}

async function saveConfig() {
  saving.value = true
  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        servo_closed_us: config.servo_closed_us,
        servo_open_us: config.servo_open_us,
        sweep_duration_ms: config.sweep_duration_ms,
        settle_detach_ms: config.settle_detach_ms,
        brightness: config.brightness,
        mirror_vertical: config.mirror_vertical,
        frame_format: config.frame_format,
        target_fps: config.target_fps,
        hud_title: config.hud_title,
        hud_subtitle: config.hud_subtitle,
      }),
    })
    if (res.ok) {
      hasUnsavedConfig.value = false
      const data = (await res.json()) as StateSnapshot
      applySnapshot(data)
      flashStatus('Calibration & HUD settings saved')
    }
  } catch {
    flashStatus('Failed to save configuration')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  fetchInitialState()
  connectUiSocket()
})

onBeforeUnmount(() => {
  if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
  if (statusTimer !== null) window.clearTimeout(statusTimer)
  socket?.close()
})
</script>

<template>
  <div class="min-h-screen bg-slate-950 text-slate-100">
    <!-- Top Header -->
    <header class="border-b border-slate-800/80 bg-slate-900/70 backdrop-blur">
      <div class="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-4">
        <div class="flex items-center gap-3">
          <div class="flex h-9 w-9 items-center justify-center rounded-lg border border-cyan-500/40 bg-cyan-500/10 font-mono text-sm font-bold text-cyan-300">
            HZ
          </div>
          <div>
            <div class="flex items-center gap-2">
              <h1 class="font-mono text-lg font-semibold tracking-wide text-slate-100">
                STANCE // HRZN-LINK
              </h1>
              <span class="rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 font-mono text-xs text-cyan-300">
                HRZN-01
              </span>
            </div>
            <p class="text-xs text-slate-400">
              Thin-Client HUD Host &amp; Servo Calibration Dashboard
            </p>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-3 text-xs font-mono">
          <span
            v-if="statusMessage"
            class="rounded-md border border-cyan-500/40 bg-cyan-500/10 px-3 py-1.5 text-cyan-200"
          >
            {{ statusMessage }}
          </span>

          <div class="flex items-center gap-2 rounded-md border border-slate-800 bg-slate-900 px-3 py-1.5">
            <span
              class="h-2 w-2 rounded-full"
              :class="uiConnected ? 'bg-emerald-400' : 'bg-rose-500'"
            />
            <span class="text-slate-300">UI {{ uiConnected ? 'LIVE' : 'OFFLINE' }}</span>
          </div>

          <div class="flex items-center gap-2 rounded-md border border-slate-800 bg-slate-900 px-3 py-1.5">
            <span
              class="h-2 w-2 rounded-full"
              :class="device.connected ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'"
            />
            <span class="text-slate-300">
              {{ device.connected ? `HRZN-01 ONLINE (${device.device_id ?? 'ESP32-S3'})` : 'HRZN-01 STANDBY' }}
            </span>
          </div>
        </div>
      </div>
    </header>

    <!-- Main Content -->
    <main class="mx-auto grid max-w-6xl gap-6 px-6 py-6 lg:grid-cols-12">
      <!-- Left Column: Live HUD Preview + Renderer Settings -->
      <section class="space-y-6 lg:col-span-5">
        <!-- Live HUD Preview Card -->
        <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-5 shadow-lg">
          <div class="mb-4 flex items-center justify-between">
            <div>
              <h2 class="font-mono text-sm font-semibold uppercase tracking-wider text-cyan-300">
                Live HUD Preview
              </h2>
              <p class="text-xs text-slate-400">
                {{ showMirroredPreview ? 'Vertically mirrored TFT output' : 'Un-mirrored combiner view (320×240)' }}
              </p>
            </div>
            <button
              type="button"
              class="rounded-md border border-slate-700 bg-slate-800 px-2.5 py-1 font-mono text-xs text-slate-300 transition hover:border-cyan-500/50 hover:text-cyan-200"
              @click="showMirroredPreview = !showMirroredPreview"
            >
              {{ showMirroredPreview ? 'Show Upright' : 'Show TFT Mirror' }}
            </button>
          </div>

          <div class="overflow-hidden rounded-lg border border-cyan-500/30 bg-black p-2">
            <img
              :src="previewDataUrl"
              alt="HRZN-01 Live HUD Preview"
              class="mx-auto aspect-[4/3] w-full max-w-[360px] rounded object-contain transition-transform duration-200"
              :class="showMirroredPreview ? '-scale-y-100' : ''"
            />
          </div>

          <!-- Telemetry Strip -->
          <div class="mt-4 grid grid-cols-4 gap-2 text-center font-mono text-xs">
            <div class="rounded-lg border border-slate-800 bg-slate-950/60 p-2">
              <div class="text-[10px] text-slate-500">RSSI</div>
              <div class="text-slate-200">{{ device.rssi_dbm !== null ? `${device.rssi_dbm} dBm` : '--' }}</div>
            </div>
            <div class="rounded-lg border border-slate-800 bg-slate-950/60 p-2">
              <div class="text-[10px] text-slate-500">HEAP</div>
              <div class="text-slate-200">
                {{ device.free_heap !== null ? `${Math.round(device.free_heap / 1024)} KB` : '--' }}
              </div>
            </div>
            <div class="rounded-lg border border-slate-800 bg-slate-950/60 p-2">
              <div class="text-[10px] text-slate-500">DEV FPS</div>
              <div class="text-emerald-300">{{ device.connected ? device.fps.toFixed(1) : '0.0' }}</div>
            </div>
            <div class="rounded-lg border border-slate-800 bg-slate-950/60 p-2">
              <div class="text-[10px] text-slate-500">UPTIME</div>
              <div class="text-slate-200">{{ device.connected ? formattedUptime : '--:--:--' }}</div>
            </div>
          </div>
        </div>

        <!-- Renderer & HUD Label Settings -->
        <div
          class="rounded-xl border border-slate-800 bg-slate-900/60 p-5 shadow-lg"
          @input="hasUnsavedConfig = true"
          @change="hasUnsavedConfig = true"
        >
          <h2 class="mb-4 font-mono text-sm font-semibold uppercase tracking-wider text-cyan-300">
            HUD Stream &amp; Labels
          </h2>
          <div class="space-y-4 text-sm">
            <div>
              <label class="mb-1 block text-xs text-slate-400">HUD Title</label>
              <input
                v-model="config.hud_title"
                type="text"
                maxlength="32"
                class="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100 focus:border-cyan-500 focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-xs text-slate-400">HUD Subtitle</label>
              <input
                v-model="config.hud_subtitle"
                type="text"
                maxlength="40"
                class="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100 focus:border-cyan-500 focus:outline-none"
              />
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-xs text-slate-400">Stream Format</label>
                <select
                  v-model="config.frame_format"
                  class="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100 focus:border-cyan-500 focus:outline-none"
                >
                  <option value="RGB565">RGB565 (Raw)</option>
                  <option value="JPEG">JPEG (Compressed)</option>
                </select>
              </div>
              <div>
                <label class="mb-1 flex justify-between text-xs text-slate-400">
                  <span>Target FPS</span>
                  <span class="font-mono text-cyan-300">{{ config.target_fps.toFixed(1) }}</span>
                </label>
                <input
                  v-model.number="config.target_fps"
                  type="range"
                  min="0.5"
                  max="15"
                  step="0.5"
                  class="mt-2 w-full"
                />
              </div>
            </div>

            <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2.5">
              <span class="text-xs text-slate-300">Vertically Mirror Frames for Combiner Film</span>
              <input
                v-model="config.mirror_vertical"
                type="checkbox"
                class="h-4 w-4 rounded border-slate-600 bg-slate-900 text-cyan-400"
              />
            </label>

            <button
              type="button"
              :disabled="saving"
              class="w-full rounded-lg bg-cyan-500/20 px-4 py-2 font-mono text-xs font-semibold text-cyan-200 ring-1 ring-cyan-500/40 transition hover:bg-cyan-500/30 disabled:opacity-50"
              @click="saveConfig"
            >
              {{ saving ? 'Saving...' : 'Apply Stream & HUD Settings' }}
            </button>
          </div>
        </div>
      </section>

      <!-- Right Column: Flap Control, Servo Endpoint Calibration, Brightness -->
      <section class="space-y-6 lg:col-span-7">
        <!-- Motorized Flap Control Card -->
        <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-5 shadow-lg">
          <div class="mb-4 flex items-center justify-between">
            <div>
              <h2 class="font-mono text-sm font-semibold uppercase tracking-wider text-cyan-300">
                Motorized Flap Actuator
              </h2>
              <p class="text-xs text-slate-400">
                Cosine-eased <code class="text-slate-300">writeMicroseconds()</code> sweep with auto-detach
              </p>
            </div>
            <div class="rounded-md border border-slate-800 bg-slate-950 px-3 py-1 font-mono text-xs">
              <span class="text-slate-400">PULSE: </span>
              <span class="text-cyan-300">{{ device.connected ? device.servo_us : estimatedPulseUs }} µs</span>
              <span class="ml-2 text-[10px]" :class="device.servo_attached ? 'text-amber-300' : 'text-slate-500'">
                {{ device.servo_attached ? 'ACTIVE' : 'DETACHED' }}
              </span>
            </div>
          </div>

          <div class="grid grid-cols-3 gap-3">
            <button
              type="button"
              class="rounded-lg border px-4 py-3 font-mono text-sm font-semibold transition"
              :class="
                config.flap_state === 'open'
                  ? 'border-emerald-400/60 bg-emerald-500/20 text-emerald-200'
                  : 'border-slate-700 bg-slate-950/60 text-slate-300 hover:border-emerald-500/40'
              "
              @click="sendFlapMove('open', 100)"
            >
              OPEN (100%)
            </button>
            <button
              type="button"
              class="rounded-lg border px-4 py-3 font-mono text-sm font-semibold transition"
              :class="
                config.flap_state === 'custom' && config.target_angle_pct === 50
                  ? 'border-cyan-400/60 bg-cyan-500/20 text-cyan-200'
                  : 'border-slate-700 bg-slate-950/60 text-slate-300 hover:border-cyan-500/40'
              "
              @click="sendFlapMove('custom', 50)"
            >
              HALF (50%)
            </button>
            <button
              type="button"
              class="rounded-lg border px-4 py-3 font-mono text-sm font-semibold transition"
              :class="
                config.flap_state === 'closed'
                  ? 'border-amber-400/60 bg-amber-500/20 text-amber-200'
                  : 'border-slate-700 bg-slate-950/60 text-slate-300 hover:border-amber-500/40'
              "
              @click="sendFlapMove('closed', 0)"
            >
              CLOSE (0%)
            </button>
          </div>

          <div class="mt-5">
            <div class="mb-1.5 flex items-center justify-between text-xs">
              <span class="text-slate-400">Custom Deployment Angle</span>
              <span class="font-mono text-cyan-300">
                {{ config.target_angle_pct }}% ({{ estimatedPulseUs }} µs)
              </span>
            </div>
            <input
              v-model.number="config.target_angle_pct"
              type="range"
              min="0"
              max="100"
              step="1"
              class="w-full"
              @change="sendFlapMove('custom', config.target_angle_pct)"
            />
          </div>
        </div>

        <!-- Servo Pulse Endpoint Calibration Card -->
        <div
          class="rounded-xl border border-slate-800 bg-slate-900/60 p-5 shadow-lg"
          @input="hasUnsavedConfig = true"
          @change="hasUnsavedConfig = true"
        >
          <div class="mb-4 flex items-center justify-between">
            <div>
              <h2 class="font-mono text-sm font-semibold uppercase tracking-wider text-cyan-300">
                Servo Endpoint Calibration
              </h2>
              <p class="text-xs text-slate-400">
                Persisted in STANCE-HRZN-LINK and pushed to HRZN-01 via <code class="text-slate-300">config_sync</code>
              </p>
            </div>
          </div>

          <div class="grid gap-5 sm:grid-cols-2">
            <div class="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
              <div class="mb-2 flex items-center justify-between text-xs">
                <span class="text-slate-300">Closed Endpoint (0%)</span>
                <span class="font-mono text-cyan-300">{{ config.servo_closed_us }} µs</span>
              </div>
              <input
                v-model.number="config.servo_closed_us"
                type="range"
                min="500"
                max="2500"
                step="10"
                class="w-full"
              />
              <div class="mt-2 flex items-center justify-between text-[11px] font-mono text-slate-500">
                <span>500 µs</span>
                <span>2500 µs</span>
              </div>
            </div>

            <div class="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
              <div class="mb-2 flex items-center justify-between text-xs">
                <span class="text-slate-300">Open Endpoint (100%)</span>
                <span class="font-mono text-cyan-300">{{ config.servo_open_us }} µs</span>
              </div>
              <input
                v-model.number="config.servo_open_us"
                type="range"
                min="500"
                max="2500"
                step="10"
                class="w-full"
              />
              <div class="mt-2 flex items-center justify-between text-[11px] font-mono text-slate-500">
                <span>500 µs</span>
                <span>2500 µs</span>
              </div>
            </div>

            <div class="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
              <div class="mb-2 flex items-center justify-between text-xs">
                <span class="text-slate-300">Sweep Duration</span>
                <span class="font-mono text-cyan-300">{{ config.sweep_duration_ms }} ms</span>
              </div>
              <input
                v-model.number="config.sweep_duration_ms"
                type="range"
                min="150"
                max="3000"
                step="50"
                class="w-full"
              />
            </div>

            <div class="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
              <div class="mb-2 flex items-center justify-between text-xs">
                <span class="text-slate-300">Settle Detach Delay</span>
                <span class="font-mono text-cyan-300">{{ config.settle_detach_ms }} ms</span>
              </div>
              <input
                v-model.number="config.settle_detach_ms"
                type="range"
                min="50"
                max="1500"
                step="25"
                class="w-full"
              />
            </div>
          </div>

          <div class="mt-4 flex justify-end">
            <button
              type="button"
              :disabled="saving"
              class="rounded-lg bg-cyan-500 px-5 py-2 font-mono text-xs font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:opacity-50"
              @click="saveConfig"
            >
              {{ saving ? 'Syncing...' : 'Save & Sync Servo Limits' }}
            </button>
          </div>
        </div>

        <!-- Display Backlight Brightness Card -->
        <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-5 shadow-lg">
          <div class="mb-4 flex items-center justify-between">
            <div>
              <h2 class="font-mono text-sm font-semibold uppercase tracking-wider text-cyan-300">
                SPI TFT Backlight PWM
              </h2>
              <p class="text-xs text-slate-400">
                Adjust combiner display luminance for ambient desk lighting
              </p>
            </div>
            <span class="font-mono text-sm font-semibold text-cyan-300">
              {{ config.brightness }} / 255 ({{ brightnessPct }}%)
            </span>
          </div>

          <input
            v-model.number="config.brightness"
            type="range"
            min="0"
            max="255"
            step="1"
            class="w-full"
            @change="sendBrightness(config.brightness)"
          />

          <div class="mt-4 flex flex-wrap gap-2">
            <button
              v-for="preset in [
                { label: 'OFF (0)', val: 0 },
                { label: 'NIGHT (64)', val: 64 },
                { label: 'DESK (150)', val: 150 },
                { label: 'DAY (220)', val: 220 },
                { label: 'MAX (255)', val: 255 },
              ]"
              :key="preset.val"
              type="button"
              class="rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 font-mono text-xs text-slate-300 transition hover:border-cyan-500/50 hover:text-cyan-200"
              @click="sendBrightness(preset.val)"
            >
              {{ preset.label }}
            </button>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>
