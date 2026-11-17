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

    <!-- Display & Dynamic Priority Behavior -->
    <div class="space-y-2">
      <label class="block font-mono text-xs uppercase tracking-wider text-slate-400">
        Layout &amp; Dynamic Behavior
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

      <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <div>
          <div class="text-xs text-slate-200">Show in Dynamic Mode When Flap Open</div>
          <div class="text-[11px] text-slate-400">Auto-activate widget when flap opens; hide when flap is closed</div>
        </div>
        <input
          :checked="current.activeWhenFlapOpen"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField('activeWhenFlapOpen', ($event.target as HTMLInputElement).checked)"
        />
      </label>

      <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <div>
          <div class="text-xs text-slate-200">Auto-Surface on Hardware Event</div>
          <div class="text-[11px] text-slate-400">Trigger On-Event surface when the motorized flap sweeps</div>
        </div>
        <input
          :checked="current.autoSurfaceOnEvent"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField('autoSurfaceOnEvent', ($event.target as HTMLInputElement).checked)"
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
