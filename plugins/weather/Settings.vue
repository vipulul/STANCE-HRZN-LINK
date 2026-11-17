<script setup lang="ts">
import { computed, ref } from 'vue'
import type { WeatherSettings } from './types'
import { DEFAULT_WEATHER_SETTINGS } from './types'

interface CitySearchResult {
  name: string
  country: string
  admin1: string
  latitude: number
  longitude: number
}

const props = defineProps<{
  modelValue?: Partial<WeatherSettings>
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: WeatherSettings): void
}>()

const current = computed<WeatherSettings>(() => ({
  ...DEFAULT_WEATHER_SETTINGS,
  ...props.modelValue,
}))

function updateField<K extends keyof WeatherSettings>(key: K, value: WeatherSettings[K]) {
  emit('update:modelValue', {
    ...current.value,
    [key]: value,
  })
}

function updateNumberField(key: 'latitude' | 'longitude', raw: string) {
  const parsed = Number.parseFloat(raw)
  if (!Number.isNaN(parsed) && Number.isFinite(parsed)) {
    updateField(key, parsed)
  }
}

const searchQuery = ref('')
const searchResults = ref<CitySearchResult[]>([])
const searching = ref(false)
const searchError = ref('')
const searchPerformed = ref(false)

async function runCitySearch() {
  const q = searchQuery.value.trim()
  if (q.length < 2) {
    searchResults.value = []
    searchError.value = 'Enter at least 2 characters to search.'
    searchPerformed.value = false
    return
  }

  searching.value = true
  searchError.value = ''
  searchPerformed.value = false
  try {
    const res = await fetch(`/api/plugins/weather/search?q=${encodeURIComponent(q)}`)
    if (!res.ok) {
      throw new Error(`Search failed (${res.status})`)
    }
    const payload = (await res.json()) as { results?: CitySearchResult[] }
    searchResults.value = Array.isArray(payload.results) ? payload.results : []
    searchPerformed.value = true
  } catch (err) {
    searchError.value = err instanceof Error ? err.message : 'Unable to search cities.'
    searchResults.value = []
  } finally {
    searching.value = false
  }
}

function selectCity(item: CitySearchResult) {
  emit('update:modelValue', {
    ...current.value,
    cityName: item.name,
    latitude: Number(item.latitude.toFixed(4)),
    longitude: Number(item.longitude.toFixed(4)),
  })
  searchResults.value = []
  searchPerformed.value = false
  searchQuery.value = item.name
}

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
    <!-- City Search -->
    <div>
      <label class="mb-2 block font-mono text-xs uppercase tracking-wider text-slate-400">
        Location Search
      </label>
      <div class="flex gap-2">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search city (e.g. Tokyo, London)..."
          class="min-w-0 flex-1 rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:border-cyan-400/70 focus:outline-none"
          @keydown.enter.prevent="runCitySearch"
        />
        <button
          type="button"
          :disabled="searching"
          class="rounded-lg border border-cyan-400/60 bg-cyan-500/20 px-3 py-2 font-mono text-xs font-semibold text-cyan-200 transition hover:bg-cyan-500/30 disabled:opacity-50"
          @click="runCitySearch"
        >
          {{ searching ? '...' : 'Search' }}
        </button>
      </div>

      <p v-if="searchError" class="mt-1.5 text-xs text-rose-400">
        {{ searchError }}
      </p>

      <div
        v-else-if="searchPerformed && searchResults.length === 0"
        class="mt-1.5 text-xs text-slate-400"
      >
        No matching cities found.
      </div>

      <div
        v-if="searchResults.length > 0"
        class="mt-2 max-h-44 space-y-1 overflow-y-auto rounded-lg border border-slate-800 bg-slate-950/90 p-1.5"
      >
        <button
          v-for="(item, idx) in searchResults"
          :key="`${item.name}-${item.latitude}-${item.longitude}-${idx}`"
          type="button"
          class="flex w-full items-center justify-between rounded-md px-2.5 py-2 text-left text-xs transition hover:bg-cyan-500/15"
          @click="selectCity(item)"
        >
          <span class="font-medium text-slate-100">
            {{ item.name }}
            <span v-if="item.admin1 || item.country" class="text-slate-400">
              · {{ [item.admin1, item.country].filter(Boolean).join(', ') }}
            </span>
          </span>
          <span class="ml-2 shrink-0 font-mono text-[11px] text-cyan-300">
            {{ item.latitude.toFixed(2) }}, {{ item.longitude.toFixed(2) }}
          </span>
        </button>
      </div>
    </div>

    <!-- Manual City & Coordinates -->
    <div class="space-y-2.5">
      <label class="block font-mono text-xs uppercase tracking-wider text-slate-400">
        Coordinates &amp; Label
      </label>

      <div>
        <label class="mb-1 block text-[11px] text-slate-400">City Name</label>
        <input
          :value="current.cityName"
          type="text"
          class="w-full rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-xs text-slate-100 focus:border-cyan-400/70 focus:outline-none"
          @change="updateField('cityName', ($event.target as HTMLInputElement).value)"
        />
      </div>

      <div class="grid grid-cols-2 gap-2">
        <div>
          <label class="mb-1 block text-[11px] text-slate-400">Latitude</label>
          <input
            :value="current.latitude"
            type="number"
            step="0.0001"
            min="-90"
            max="90"
            class="w-full rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 font-mono text-xs text-slate-100 focus:border-cyan-400/70 focus:outline-none"
            @change="updateNumberField('latitude', ($event.target as HTMLInputElement).value)"
          />
        </div>
        <div>
          <label class="mb-1 block text-[11px] text-slate-400">Longitude</label>
          <input
            :value="current.longitude"
            type="number"
            step="0.0001"
            min="-180"
            max="180"
            class="w-full rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 font-mono text-xs text-slate-100 focus:border-cyan-400/70 focus:outline-none"
            @change="updateNumberField('longitude', ($event.target as HTMLInputElement).value)"
          />
        </div>
      </div>
    </div>

    <!-- Display Toggles -->
    <div class="space-y-2">
      <label class="block font-mono text-xs uppercase tracking-wider text-slate-400">
        Display Elements
      </label>

      <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <span class="text-xs text-slate-200">Show Condition</span>
        <input
          :checked="current.showCondition"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField('showCondition', ($event.target as HTMLInputElement).checked)"
        />
      </label>

      <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <span class="text-xs text-slate-200">Show High/Low</span>
        <input
          :checked="current.showHighLow"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField('showHighLow', ($event.target as HTMLInputElement).checked)"
        />
      </label>

      <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <span class="text-xs text-slate-200">Show Humidity</span>
        <input
          :checked="current.showHumidity"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField('showHumidity', ($event.target as HTMLInputElement).checked)"
        />
      </label>

      <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <span class="text-xs text-slate-200">Show Wind</span>
        <input
          :checked="current.showWind"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField('showWind', ($event.target as HTMLInputElement).checked)"
        />
      </label>

      <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <span class="text-xs text-slate-200">Show Corner Brackets</span>
        <input
          :checked="current.showCornerBrackets"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField('showCornerBrackets', ($event.target as HTMLInputElement).checked)"
        />
      </label>

      <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <span class="text-xs text-slate-200">Auto-Surface on Rain/Storm</span>
        <input
          :checked="current.alertOnSevereWeather"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField('alertOnSevereWeather', ($event.target as HTMLInputElement).checked)"
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
