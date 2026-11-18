<script setup lang="ts">
import { computed } from 'vue'
import type { TelemetrySettings } from './types'
import { DEFAULT_TELEMETRY_SETTINGS } from './types'

const props = defineProps<{
  modelValue?: Partial<TelemetrySettings>
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: TelemetrySettings): void
}>()

const current = computed<TelemetrySettings>(() => ({
  ...DEFAULT_TELEMETRY_SETTINGS,
  ...props.modelValue,
}))

function updateField<K extends keyof TelemetrySettings>(key: K, value: TelemetrySettings[K]) {
  emit('update:modelValue', {
    ...current.value,
    [key]: value,
  })
}

function updateNumberField(
  key: 'rssiThresholdDbm' | 'latencyThresholdMs' | 'minFpsThreshold',
  raw: string,
) {
  const parsed = Number.parseFloat(raw)
  if (!Number.isNaN(parsed) && Number.isFinite(parsed)) {
    updateField(key, parsed)
  }
}

const metricToggles: Array<{ key: keyof TelemetrySettings; label: string }> = [
  { key: 'showFps', label: 'Stream FPS' },
  { key: 'showFlapState', label: 'Flap State' },
  { key: 'showServoPulse', label: 'Servo Pulse (µs)' },
  { key: 'showDeviceStatus', label: 'ESP32 Link & RSSI' },
  { key: 'showLatency', label: 'Frame Latency (ms)' },
  { key: 'showLayout', label: 'Active Layout' },
]

const swatches = [
  { label: 'HUD Cyan', hex: '#00f0ff' },
  { label: 'Emerald', hex: '#10e18c' },
  { label: 'Amber', hex: '#f5a623' },
  { label: 'Crimson', hex: '#ff2a6d' },
  { label: 'Violet', hex: '#a855f7' },
  { label: 'Pure White', hex: '#f8fafc' },
]
</script>

<template>
  <div class="space-y-5 text-sm">
    <!-- Metric Visibility Checkboxes -->
    <div class="space-y-2">
      <label class="block font-mono text-xs uppercase tracking-wider text-slate-400">
        Visible Telemetry Metrics
      </label>

      <label
        v-for="item in metricToggles"
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

    <!-- Display Style -->
    <div class="space-y-2">
      <label class="block font-mono text-xs uppercase tracking-wider text-slate-400">
        Display Style
      </label>

      <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <div>
          <div class="text-xs text-slate-200">Compact Labels</div>
          <div class="text-[11px] text-slate-400">Use short avionic mnemonics (FPS, PWM, LAT)</div>
        </div>
        <input
          :checked="current.compactLabels"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField('compactLabels', ($event.target as HTMLInputElement).checked)"
        />
      </label>
    </div>

    <!-- On-Event Trigger Conditions -->
    <div class="space-y-2">
      <label class="block font-mono text-xs uppercase tracking-wider text-amber-300">
        On-Event Trigger Conditions
      </label>
      <p class="text-[11px] text-slate-400">
        Choose which hardware or link events automatically surface Telemetry in Dynamic Mode.
      </p>

      <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <div>
          <div class="text-xs text-slate-200">Flap Actuator Moving</div>
          <div class="text-[11px] text-slate-400">Surface while the motorized flap sweeps</div>
        </div>
        <input
          :checked="current.triggerOnFlapMove"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField('triggerOnFlapMove', ($event.target as HTMLInputElement).checked)"
        />
      </label>

      <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <div>
          <div class="text-xs text-slate-200">While Flap is Open</div>
          <div class="text-[11px] text-slate-400">Keep active whenever flap state is OPEN</div>
        </div>
        <input
          :checked="current.triggerOnFlapOpen"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField('triggerOnFlapOpen', ($event.target as HTMLInputElement).checked)"
        />
      </label>

      <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <div>
          <div class="text-xs text-slate-200">ESP32-S3 Link Offline</div>
          <div class="text-[11px] text-slate-400">Alert when hardware device is disconnected</div>
        </div>
        <input
          :checked="current.triggerOnDeviceDisconnect"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField('triggerOnDeviceDisconnect', ($event.target as HTMLInputElement).checked)"
        />
      </label>

      <!-- Weak Wi-Fi RSSI Trigger + Threshold -->
      <div class="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <label class="flex cursor-pointer items-center justify-between">
          <div>
            <div class="text-xs text-slate-200">Weak Wi-Fi Signal (RSSI)</div>
            <div class="text-[11px] text-slate-400">Trigger when signal drops below threshold</div>
          </div>
          <input
            :checked="current.triggerOnWeakWifi"
            type="checkbox"
            class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
            @change="updateField('triggerOnWeakWifi', ($event.target as HTMLInputElement).checked)"
          />
        </label>
        <div v-if="current.triggerOnWeakWifi" class="mt-2 flex items-center justify-between gap-2 border-t border-slate-800/80 pt-2">
          <span class="text-[11px] text-slate-400">RSSI &le; (dBm)</span>
          <input
            :value="current.rssiThresholdDbm"
            type="number"
            min="-100"
            max="-30"
            step="1"
            class="w-20 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-right font-mono text-xs text-cyan-300 focus:border-cyan-400/70 focus:outline-none"
            @change="updateNumberField('rssiThresholdDbm', ($event.target as HTMLInputElement).value)"
          />
        </div>
      </div>

      <!-- High Latency Trigger + Threshold -->
      <div class="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <label class="flex cursor-pointer items-center justify-between">
          <div>
            <div class="text-xs text-slate-200">High Frame Latency</div>
            <div class="text-[11px] text-slate-400">Trigger when render/encode latency spikes</div>
          </div>
          <input
            :checked="current.triggerOnHighLatency"
            type="checkbox"
            class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
            @change="updateField('triggerOnHighLatency', ($event.target as HTMLInputElement).checked)"
          />
        </label>
        <div v-if="current.triggerOnHighLatency" class="mt-2 flex items-center justify-between gap-2 border-t border-slate-800/80 pt-2">
          <span class="text-[11px] text-slate-400">Latency &ge; (ms)</span>
          <input
            :value="current.latencyThresholdMs"
            type="number"
            min="5"
            max="2000"
            step="5"
            class="w-20 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-right font-mono text-xs text-cyan-300 focus:border-cyan-400/70 focus:outline-none"
            @change="updateNumberField('latencyThresholdMs', ($event.target as HTMLInputElement).value)"
          />
        </div>
      </div>

      <!-- Low Device FPS Trigger + Threshold -->
      <div class="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <label class="flex cursor-pointer items-center justify-between">
          <div>
            <div class="text-xs text-slate-200">Low Device FPS</div>
            <div class="text-[11px] text-slate-400">Trigger when connected device FPS drops</div>
          </div>
          <input
            :checked="current.triggerOnLowFps"
            type="checkbox"
            class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
            @change="updateField('triggerOnLowFps', ($event.target as HTMLInputElement).checked)"
          />
        </label>
        <div v-if="current.triggerOnLowFps" class="mt-2 flex items-center justify-between gap-2 border-t border-slate-800/80 pt-2">
          <span class="text-[11px] text-slate-400">FPS &lt;</span>
          <input
            :value="current.minFpsThreshold"
            type="number"
            min="0.2"
            max="30"
            step="0.1"
            class="w-20 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-right font-mono text-xs text-cyan-300 focus:border-cyan-400/70 focus:outline-none"
            @change="updateNumberField('minFpsThreshold', ($event.target as HTMLInputElement).value)"
          />
        </div>
      </div>
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
