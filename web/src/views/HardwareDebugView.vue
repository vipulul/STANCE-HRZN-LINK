<script setup lang="ts">
import { computed, ref } from 'vue'
import { useHrznState } from '../composables/useHrznState'

const {
  config,
  device,
  saving,
  hasUnsavedConfig,
  previewDataUrl,
  rendererMode,
  combinedLogs,
  saveHardwareConfig,
  sendFlapMove,
  sendBrightness,
  clearClientLogs,
} = useHrznState()

const showMirroredThumb = ref(false)
const pauseLogs = ref(false)

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

const visibleLogs = computed(() => [...combinedLogs.value].reverse())

function applyResolution(w: number, h: number) {
  config.display_width = w
  config.display_height = h
  hasUnsavedConfig.value = true
}

function formatLogTime(iso: string): string {
  const idx = iso.indexOf('T')
  if (idx === -1) return iso
  return iso.slice(idx + 1, idx + 9)
}
</script>

<template>
  <div class="grid gap-6 lg:grid-cols-12">
    <!-- Left Column: Telemetry, TFT Preview & Display/Stream Settings -->
    <section class="space-y-6 lg:col-span-5">
      <!-- Device Telemetry & Headless Stream Preview -->
      <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-5 shadow-lg">
        <div class="mb-4 flex items-center justify-between gap-2">
          <div>
            <h2 class="font-mono text-sm font-semibold uppercase tracking-wider text-cyan-300">
              Hardware Telemetry &amp; Stream
            </h2>
            <p class="text-xs text-slate-400">
              Engine:
              <span
                class="font-mono"
                :class="rendererMode === 'playwright' ? 'text-emerald-300' : 'text-amber-300'"
              >
                {{ rendererMode === 'playwright' ? 'Playwright Chromium' : 'Pillow Fallback' }}
              </span>
            </p>
          </div>

          <button
            type="button"
            class="rounded-md border border-slate-700 bg-slate-800 px-2.5 py-1 font-mono text-xs text-slate-300 transition hover:border-cyan-500/50 hover:text-cyan-200"
            @click="showMirroredThumb = !showMirroredThumb"
          >
            {{ showMirroredThumb ? 'Show Upright' : 'Show TFT Mirror' }}
          </button>
        </div>

        <div class="overflow-hidden rounded-lg border border-cyan-500/30 bg-black p-2">
          <img
            :src="previewDataUrl"
            alt="HRZN-01 Stream Preview"
            class="mx-auto max-h-[220px] w-full rounded object-contain transition-transform duration-200"
            :class="showMirroredThumb ? '-scale-y-100' : ''"
          />
        </div>

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

        <div class="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 font-mono text-[11px] text-slate-400">
          <span>ID: <span class="text-slate-200">{{ device.device_id ?? 'unpaired' }}</span></span>
          <span>FW: <span class="text-slate-200">{{ device.fw_version ?? '--' }}</span></span>
          <span>HW TFT: <span class="text-slate-200">{{ device.display_width }}×{{ device.display_height }}</span></span>
        </div>
      </div>

      <!-- TFT Resolution & Stream Pipeline Settings -->
      <div
        class="rounded-xl border border-slate-800 bg-slate-900/60 p-5 shadow-lg"
        @input="hasUnsavedConfig = true"
        @change="hasUnsavedConfig = true"
      >
        <h2 class="mb-4 font-mono text-sm font-semibold uppercase tracking-wider text-cyan-300">
          TFT Resolution &amp; Stream Pipeline
        </h2>

        <div class="space-y-4 text-sm">
          <div>
            <label class="mb-1.5 block text-xs text-slate-400">Resolution Presets</label>
            <div class="grid grid-cols-3 gap-2 font-mono text-xs">
              <button
                v-for="res in [
                  { label: '480×320', w: 480, h: 320 },
                  { label: '320×240', w: 320, h: 240 },
                  { label: '240×240', w: 240, h: 240 },
                ]"
                :key="res.label"
                type="button"
                class="rounded-md border px-2 py-1.5 transition"
                :class="
                  config.display_width === res.w && config.display_height === res.h
                    ? 'border-cyan-400/60 bg-cyan-500/20 text-cyan-200'
                    : 'border-slate-700 bg-slate-950 text-slate-300 hover:border-cyan-500/40'
                "
                @click="applyResolution(res.w, res.h)"
              >
                {{ res.label }}
              </button>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="mb-1 block text-xs text-slate-400">Canvas Width (px)</label>
              <input
                v-model.number="config.display_width"
                type="number"
                min="120"
                max="800"
                class="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100 focus:border-cyan-500 focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-xs text-slate-400">Canvas Height (px)</label>
              <input
                v-model.number="config.display_height"
                type="number"
                min="120"
                max="800"
                class="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100 focus:border-cyan-500 focus:outline-none"
              />
            </div>
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

          <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2.5">
            <span class="text-xs text-slate-300">Vertically Mirror Frames for Combiner Film</span>
            <input
              v-model="config.mirror_vertical"
              type="checkbox"
              class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
            />
          </label>

          <button
            type="button"
            :disabled="saving"
            class="w-full rounded-lg bg-cyan-500/20 px-4 py-2 font-mono text-xs font-semibold text-cyan-200 ring-1 ring-cyan-500/40 transition hover:bg-cyan-500/30 disabled:opacity-50"
            @click="saveHardwareConfig"
          >
            {{ saving ? 'Saving...' : 'Apply Display & Stream Settings' }}
          </button>
        </div>
      </div>
    </section>

    <!-- Right Column: Motorized Flap, Servo Endpoints, Backlight & WS Logs -->
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
              <span class="text-slate-300">Closed Endpoint (0% · <code>closed_us</code>)</span>
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
              <span class="text-slate-300">Open Endpoint (100% · <code>open_us</code>)</span>
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
            @click="saveHardwareConfig"
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

      <!-- WebSocket Connection & Runtime Logs -->
      <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-5 shadow-lg">
        <div class="mb-3 flex items-center justify-between gap-2">
          <div>
            <h2 class="font-mono text-sm font-semibold uppercase tracking-wider text-cyan-300">
              WebSocket Connection Logs
            </h2>
            <p class="text-xs text-slate-400">
              Live events from <code>/ws/device</code>, <code>/ws/ui</code>, and layout engine
            </p>
          </div>
          <div class="flex items-center gap-2 font-mono text-xs">
            <button
              type="button"
              class="rounded border border-slate-700 bg-slate-950 px-2.5 py-1 text-slate-300 hover:border-cyan-500/50"
              @click="pauseLogs = !pauseLogs"
            >
              {{ pauseLogs ? 'Resume' : 'Pause' }}
            </button>
            <button
              type="button"
              class="rounded border border-slate-700 bg-slate-950 px-2.5 py-1 text-slate-300 hover:border-amber-500/50"
              @click="clearClientLogs"
            >
              Clear Client
            </button>
          </div>
        </div>

        <div class="h-56 overflow-y-auto rounded-lg border border-slate-800 bg-slate-950 p-3 font-mono text-[11px]">
          <div
            v-if="visibleLogs.length === 0"
            class="py-8 text-center text-slate-600"
          >
            No WebSocket events logged yet.
          </div>
          <div
            v-for="(entry, idx) in pauseLogs ? [] : visibleLogs"
            :key="`${entry.ts}-${idx}`"
            class="flex items-start gap-2 border-b border-slate-900/80 py-1 last:border-b-0"
          >
            <span class="shrink-0 text-slate-500">{{ formatLogTime(entry.ts) }}</span>
            <span
              class="shrink-0 rounded px-1.5 py-0.2 text-[10px] uppercase"
              :class="
                entry.level === 'error'
                  ? 'bg-rose-500/20 text-rose-300'
                  : entry.level === 'warn'
                    ? 'bg-amber-500/20 text-amber-300'
                    : 'bg-cyan-500/15 text-cyan-300'
              "
            >
              {{ entry.source }}
            </span>
            <span class="shrink-0 font-semibold text-slate-200">{{ entry.event }}</span>
            <span class="break-all text-slate-400">{{ entry.detail }}</span>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
