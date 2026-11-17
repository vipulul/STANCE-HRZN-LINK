<script setup lang="ts">
import { computed } from 'vue'
import type { ClockSettings, ClockStylePreset } from './types'
import { DEFAULT_CLOCK_SETTINGS } from './types'

const props = defineProps<{
  modelValue?: Partial<ClockSettings>
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: ClockSettings): void
}>()

const current = computed<ClockSettings>(() => ({
  ...DEFAULT_CLOCK_SETTINGS,
  ...props.modelValue,
}))

function updateField<K extends keyof ClockSettings>(key: K, value: ClockSettings[K]) {
  emit('update:modelValue', {
    ...current.value,
    [key]: value,
  })
}

const presets: Array<{ id: ClockStylePreset; label: string; desc: string }> = [
  { id: 'minimal', label: 'Minimal', desc: 'Clean hairline typography' },
  { id: 'tactical', label: 'Tactical', desc: 'Reticle frame & arc dial' },
  { id: 'segmented', label: 'Segmented', desc: 'Cyber matrix + tick bar' },
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
    <!-- Time Format -->
    <div>
      <label class="mb-2 block font-mono text-xs uppercase tracking-wider text-slate-400">
        Time Format
      </label>
      <div class="grid grid-cols-2 gap-2">
        <button
          type="button"
          class="rounded-lg border px-3 py-2 font-mono text-xs font-semibold transition"
          :class="
            current.format24h
              ? 'border-cyan-400/70 bg-cyan-500/20 text-cyan-200'
              : 'border-slate-800 bg-slate-950/70 text-slate-400 hover:border-slate-700'
          "
          @click="updateField('format24h', true)"
        >
          24-Hour (MIL)
        </button>
        <button
          type="button"
          class="rounded-lg border px-3 py-2 font-mono text-xs font-semibold transition"
          :class="
            !current.format24h
              ? 'border-cyan-400/70 bg-cyan-500/20 text-cyan-200'
              : 'border-slate-800 bg-slate-950/70 text-slate-400 hover:border-slate-700'
          "
          @click="updateField('format24h', false)"
        >
          12-Hour (AM/PM)
        </button>
      </div>
    </div>

    <!-- Style Preset -->
    <div>
      <label class="mb-2 block font-mono text-xs uppercase tracking-wider text-slate-400">
        Style Preset
      </label>
      <div class="grid grid-cols-3 gap-2">
        <button
          v-for="preset in presets"
          :key="preset.id"
          type="button"
          class="rounded-lg border p-2.5 text-left transition"
          :class="
            current.stylePreset === preset.id
              ? 'border-cyan-400/70 bg-cyan-500/15 text-cyan-100'
              : 'border-slate-800 bg-slate-950/70 text-slate-300 hover:border-slate-700'
          "
          @click="updateField('stylePreset', preset.id)"
        >
          <div class="font-mono text-xs font-semibold">{{ preset.label }}</div>
          <div class="mt-0.5 text-[11px] text-slate-400">{{ preset.desc }}</div>
        </button>
      </div>
    </div>

    <!-- Display Toggles -->
    <div class="space-y-2">
      <label class="block font-mono text-xs uppercase tracking-wider text-slate-400">
        Display Elements
      </label>

      <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <span class="text-xs text-slate-200">Show Seconds</span>
        <input
          :checked="current.showSeconds"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField('showSeconds', ($event.target as HTMLInputElement).checked)"
        />
      </label>

      <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <span class="text-xs text-slate-200">Show Date</span>
        <input
          :checked="current.showDate"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField('showDate', ($event.target as HTMLInputElement).checked)"
        />
      </label>

      <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <span class="text-xs text-slate-200">Show Adaptive Arc Ring</span>
        <input
          :checked="current.showArcRing"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField('showArcRing', ($event.target as HTMLInputElement).checked)"
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
