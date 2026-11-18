<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import HudGridCanvas from '../components/HudGridCanvas.vue'
import { useHrznState } from '../composables/useHrznState'
import { PLUGIN_LIST, getPluginById } from '../plugins/registry'
import type { GridLayoutId, PluginDynamicMode } from '../types/hrzn'

const {
  config,
  layout,
  rendererMode,
  previewDataUrl,
  saving,
  reloadingPlugins,
  setLayoutMode,
  setManualLayout,
  assignSlot,
  swapSlots,
  updateConfigPatch,
  updatePluginSettings,
  updatePluginDynamicConfig,
  triggerPluginTestEvent,
  triggerPluginReload,
} = useHrznState()

const showMirroredPreview = ref(false)
const showServerFrame = ref(false)
const selectedSlotIndex = ref<number>(0)
const showDynamicRules = ref(false)
const settingsModalPluginId = ref<string | null>(null)
const draftPluginSettings = ref<Record<string, unknown>>({})

const layoutTemplates: Array<{
  id: GridLayoutId
  label: string
  subtitle: string
  slots: number
}> = [
  { id: '1x1', label: '1x1', subtitle: 'Full Screen', slots: 1 },
  { id: '2x1', label: '2x1', subtitle: '2 Side-by-Side', slots: 2 },
  { id: '1x2', label: '1x2', subtitle: 'Top / Bottom', slots: 2 },
  { id: '2x2', label: '2x2', subtitle: 'Quadrants', slots: 4 },
  { id: '2-big-1-small', label: '2-Big + 1', subtitle: '2 Primary + Compact', slots: 3 },
  { id: '3x1', label: '3x1', subtitle: '3 Side-by-Side', slots: 3 },
  { id: '4x1', label: '4x1', subtitle: '4 Side-by-Side', slots: 4 },
]

const activeGridSlots = computed(() =>
  config.layout_mode === 'dynamic' ? layout.slots : config.grid_slots,
)

const activePluginSettings = computed(() =>
  config.layout_mode === 'dynamic' ? layout.effective_plugin_settings : config.plugin_configs,
)

watch(
  () => layout.slot_count,
  (count) => {
    if (selectedSlotIndex.value >= count) {
      selectedSlotIndex.value = 0
    }
  },
)

const selectedSlotPluginId = computed(() => activeGridSlots.value[selectedSlotIndex.value] ?? null)
const selectedSlotPlugin = computed(() => getPluginById(selectedSlotPluginId.value))

const activeSettingsPlugin = computed(() => getPluginById(settingsModalPluginId.value))

function getPluginDynamicMode(pluginId: string): PluginDynamicMode {
  const supportsOnEvent = getPluginById(pluginId)?.supportsOnEvent ?? false
  const normalize = (val: unknown): PluginDynamicMode | null => {
    if (val === 'always' || val === 'off') return val
    if (val === 'on_event') return supportsOnEvent ? 'on_event' : 'always'
    return null
  }
  return (
    normalize(config.plugin_configs[pluginId]?.dynamicMode) ??
    normalize(layout.plugin_statuses.find((s) => s.id === pluginId)?.dynamic_mode) ??
    normalize(getPluginById(pluginId)?.defaultSettings?.dynamicMode) ??
    'always'
  )
}

function getPluginUserPriority(pluginId: string): number {
  const raw =
    config.plugin_configs[pluginId]?.userPriority ??
    layout.plugin_statuses.find((s) => s.id === pluginId)?.user_priority ??
    getPluginById(pluginId)?.defaultSettings?.userPriority ??
    10
  const parsed = Number(raw)
  if (!Number.isFinite(parsed)) return 10
  return Math.max(1, Math.min(100, Math.round(parsed)))
}

const managedPlugins = computed(() => {
  return [...PLUGIN_LIST.value]
    .map((plugin) => {
      const status = layout.plugin_statuses.find((s) => s.id === plugin.id)
      const mode = getPluginDynamicMode(plugin.id)
      const userPriority = getPluginUserPriority(plugin.id)
      const slotIndex = config.layout_mode === 'dynamic' ? layout.slots.indexOf(plugin.id) : -1
      return {
        plugin,
        status,
        mode,
        userPriority,
        slotIndex,
      }
    })
    .sort((a, b) => {
      if (b.userPriority !== a.userPriority) return b.userPriority - a.userPriority
      if (a.plugin.id === 'clock') return -1
      if (b.plugin.id === 'clock') return 1
      return a.plugin.id.localeCompare(b.plugin.id)
    })
})

async function setPriorityDirect(pluginId: string, rawVal: string) {
  const parsed = Number.parseInt(rawVal, 10)
  if (Number.isNaN(parsed)) return
  const clamped = Math.max(1, Math.min(100, parsed))
  await updatePluginDynamicConfig(pluginId, { userPriority: clamped })
}

async function movePluginOrder(index: number, delta: -1 | 1) {
  const list = managedPlugins.value
  const targetIdx = index + delta
  if (targetIdx < 0 || targetIdx >= list.length) return

  const currentItem = list[index]
  const neighborItem = list[targetIdx]
  let nextCurrentPrio = neighborItem.userPriority
  let nextNeighborPrio = currentItem.userPriority

  if (nextCurrentPrio === nextNeighborPrio) {
    if (delta === -1) {
      if (neighborItem.userPriority < 100) {
        nextCurrentPrio = neighborItem.userPriority + 1
      } else {
        nextNeighborPrio = 99
      }
    } else {
      if (neighborItem.userPriority > 1) {
        nextCurrentPrio = neighborItem.userPriority - 1
      } else {
        nextNeighborPrio = 2
      }
    }
  }

  await updateConfigPatch(
    {
      plugin_configs: {
        [currentItem.plugin.id]: { userPriority: nextCurrentPrio },
        [neighborItem.plugin.id]: { userPriority: nextNeighborPrio },
      },
    },
    `Updated slot priority: ${currentItem.plugin.name} -> P${nextCurrentPrio}`,
  )
}

function openPluginSettings(pluginId: string) {
  const plugin = getPluginById(pluginId)
  if (!plugin) return
  draftPluginSettings.value = {
    ...plugin.defaultSettings,
    ...(config.plugin_configs[pluginId] ?? {}),
    dynamicMode: getPluginDynamicMode(pluginId),
    userPriority: getPluginUserPriority(pluginId),
  }
  settingsModalPluginId.value = pluginId
}

async function applyDraftPluginSettings() {
  if (!settingsModalPluginId.value) return
  const prio = Number(draftPluginSettings.value.userPriority ?? 10)
  const payload = {
    ...draftPluginSettings.value,
    userPriority: Number.isFinite(prio) ? Math.max(1, Math.min(100, Math.round(prio))) : 10,
  }
  const ok = await updatePluginSettings(settingsModalPluginId.value, payload)
  if (ok) {
    settingsModalPluginId.value = null
  }
}

async function handleDynamicRuleChange() {
  const holdVal = Number(config.dynamic_rules.event_hold_seconds ?? 12)
  const clampedHold = Number.isFinite(holdVal) ? Math.max(1, Math.min(300, Math.round(holdVal))) : 12
  config.dynamic_rules.event_hold_seconds = clampedHold
  await updateConfigPatch(
    {
      dynamic_rules: {
        night_mode_enabled: config.dynamic_rules.night_mode_enabled,
        night_start_hour: config.dynamic_rules.night_start_hour,
        night_end_hour: config.dynamic_rules.night_end_hour,
        night_style_preset: config.dynamic_rules.night_style_preset,
        event_hold_seconds: clampedHold,
      },
    },
    'Dynamic mode rules updated',
  )
}

function updateResolutionPreset(w: number, h: number) {
  updateConfigPatch({ display_width: w, display_height: h }, `Canvas set to ${w}x${h}`)
}

const swapCandidates = computed(() =>
  Array.from({ length: layout.slot_count }, (_, idx) => idx).filter(
    (idx) => idx !== selectedSlotIndex.value,
  ),
)

const hourOptions = Array.from({ length: 24 }, (_, h) => ({
  value: h,
  label: `${String(h).padStart(2, '0')}:00`,
}))
</script>

<template>
  <div class="space-y-6">
    <!-- Mode Switcher & Dynamic Reason Bar -->
    <section class="rounded-xl border border-slate-800 bg-slate-900/60 p-5 shadow-lg">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div class="flex flex-wrap items-center gap-3">
          <div class="inline-flex rounded-lg border border-slate-800 bg-slate-950 p-1 font-mono text-xs">
            <button
              type="button"
              class="rounded-md px-3.5 py-1.5 font-semibold transition"
              :class="
                config.layout_mode === 'manual'
                  ? 'bg-cyan-500/20 text-cyan-200 ring-1 ring-cyan-500/50'
                  : 'text-slate-400 hover:text-slate-200'
              "
              @click="setLayoutMode('manual')"
            >
              Manual Grid
            </button>
            <button
              type="button"
              class="rounded-md px-3.5 py-1.5 font-semibold transition"
              :class="
                config.layout_mode === 'dynamic'
                  ? 'bg-emerald-500/20 text-emerald-200 ring-1 ring-emerald-500/50'
                  : 'text-slate-400 hover:text-slate-200'
              "
              @click="setLayoutMode('dynamic')"
            >
              Dynamic Mode
            </button>
          </div>

          <!-- Dynamic / Active Reason Status Badge -->
          <div
            class="flex items-center gap-2 rounded-lg border px-3 py-1.5 font-mono text-xs"
            :class="
              config.layout_mode === 'dynamic'
                ? 'border-emerald-500/35 bg-emerald-500/10 text-emerald-200'
                : 'border-cyan-500/30 bg-cyan-500/10 text-cyan-200'
            "
          >
            <span
              class="h-2 w-2 rounded-full"
              :class="config.layout_mode === 'dynamic' ? 'bg-emerald-400 animate-pulse' : 'bg-cyan-400'"
            />
            <span>{{ layout.reason }}</span>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <button
            type="button"
            :disabled="reloadingPlugins"
            class="rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-1.5 font-mono text-xs font-semibold text-cyan-200 transition hover:bg-cyan-500/20 disabled:opacity-50"
            @click="triggerPluginReload"
          >
            {{ reloadingPlugins ? 'Reloading...' : 'Reload Plugins' }}
          </button>
          <button
            type="button"
            class="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 font-mono text-xs text-slate-300 transition hover:border-cyan-500/50 hover:text-cyan-200"
            @click="showDynamicRules = !showDynamicRules"
          >
            {{ showDynamicRules ? 'Hide Dynamic Rules' : 'Dynamic Rules' }}
          </button>
        </div>
      </div>

      <!-- Dynamic Mode & Priority Manager (auto-shown in Dynamic Mode, toggleable otherwise) -->
      <div
        v-if="config.layout_mode === 'dynamic' || showDynamicRules"
        class="mt-4 space-y-4 border-t border-slate-800 pt-4"
      >
        <!-- Global Dynamic Schedule & Cooldown Rules -->
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <div class="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2">
            <label class="mb-1 flex items-center justify-between font-mono text-[11px] text-slate-400">
              <span>Event Hold Cooldown</span>
              <span class="text-cyan-300">{{ config.dynamic_rules.event_hold_seconds }}s</span>
            </label>
            <input
              v-model.number="config.dynamic_rules.event_hold_seconds"
              type="number"
              min="1"
              max="300"
              class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-xs text-slate-100 focus:border-cyan-500 focus:outline-none"
              @change="handleDynamicRuleChange"
            />
          </div>

          <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
            <div>
              <div class="font-mono text-xs font-semibold text-slate-200">Night Minimal</div>
              <div class="text-[11px] text-slate-400">Force 1x1 clock overnight</div>
            </div>
            <input
              v-model="config.dynamic_rules.night_mode_enabled"
              type="checkbox"
              class="h-4 w-4 accent-cyan-400"
              @change="handleDynamicRuleChange"
            />
          </label>

          <div class="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2">
            <label class="mb-1 block font-mono text-[11px] text-slate-400">Night Start</label>
            <select
              v-model.number="config.dynamic_rules.night_start_hour"
              class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-xs text-slate-100 focus:border-cyan-500 focus:outline-none"
              @change="handleDynamicRuleChange"
            >
              <option v-for="opt in hourOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>

          <div class="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2">
            <label class="mb-1 block font-mono text-[11px] text-slate-400">Night End</label>
            <select
              v-model.number="config.dynamic_rules.night_end_hour"
              class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-xs text-slate-100 focus:border-cyan-500 focus:outline-none"
              @change="handleDynamicRuleChange"
            >
              <option v-for="opt in hourOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>

          <div class="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2">
            <label class="mb-1 block font-mono text-[11px] text-slate-400">Night Preset</label>
            <select
              v-model="config.dynamic_rules.night_style_preset"
              class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-xs text-slate-100 focus:border-cyan-500 focus:outline-none"
              @change="handleDynamicRuleChange"
            >
              <option value="minimal">minimal</option>
              <option value="tactical">tactical</option>
              <option value="segmented">segmented</option>
            </select>
          </div>
        </div>

        <!-- Per-Plugin Dynamic Mode & Priority Manager -->
        <div class="rounded-lg border border-slate-800 bg-slate-950/60 p-3.5">
          <div class="mb-2.5 flex flex-wrap items-center justify-between gap-2">
            <span class="font-mono text-xs font-semibold uppercase tracking-wider text-cyan-300">
              Dynamic Mode &amp; Priority Order
            </span>
            <span class="font-mono text-[11px] text-slate-500">
              Higher priority gets earlier slots (Slot 1 left/top &rarr; Slot 2 right/bottom)
            </span>
          </div>

          <div class="space-y-2">
            <div
              v-for="(item, idx) in managedPlugins"
              :key="item.plugin.id"
              class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-800/90 bg-slate-900/70 px-3 py-2.5"
            >
              <!-- Left: Reorder Arrows + Priority Input + Plugin Info -->
              <div class="flex min-w-[220px] flex-1 items-center gap-3">
                <div class="flex flex-col gap-0.5">
                  <button
                    type="button"
                    :disabled="idx === 0 || saving"
                    title="Move Higher Priority (Earlier Slot)"
                    class="rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 font-mono text-[10px] leading-none text-slate-300 transition hover:border-cyan-500/60 hover:text-cyan-200 disabled:opacity-30"
                    @click="movePluginOrder(idx, -1)"
                  >
                    ▲
                  </button>
                  <button
                    type="button"
                    :disabled="idx === managedPlugins.length - 1 || saving"
                    title="Move Lower Priority (Later Slot)"
                    class="rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 font-mono text-[10px] leading-none text-slate-300 transition hover:border-cyan-500/60 hover:text-cyan-200 disabled:opacity-30"
                    @click="movePluginOrder(idx, 1)"
                  >
                    ▼
                  </button>
                </div>

                <div class="w-16">
                  <label class="block font-mono text-[9px] uppercase text-slate-500">Priority</label>
                  <input
                    :value="item.userPriority"
                    type="number"
                    min="1"
                    max="100"
                    class="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-xs font-semibold text-cyan-300 focus:border-cyan-500 focus:outline-none"
                    @change="setPriorityDirect(item.plugin.id, ($event.target as HTMLInputElement).value)"
                  />
                </div>

                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="font-mono text-xs font-semibold text-slate-100">
                      {{ item.plugin.name }}
                    </span>
                    <span
                      v-if="item.slotIndex >= 0"
                      class="rounded border border-emerald-500/40 bg-emerald-500/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-emerald-300"
                    >
                      SLOT {{ item.slotIndex + 1 }}
                    </span>
                    <span
                      v-else-if="item.mode === 'off'"
                      class="rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 font-mono text-[10px] text-slate-500"
                    >
                      OFF
                    </span>
                    <span
                      v-else-if="item.mode === 'on_event'"
                      class="rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 font-mono text-[10px] text-amber-300"
                    >
                      STANDBY
                    </span>

                    <span
                      v-if="item.status?.holding_event"
                      class="rounded border border-cyan-500/40 bg-cyan-500/15 px-1.5 py-0.5 font-mono text-[10px] text-cyan-200"
                    >
                      HOLD {{ Math.ceil(item.status.hold_remaining_s ?? 0) }}s
                    </span>
                    <span
                      v-else-if="item.status?.event_triggered"
                      class="rounded border border-rose-500/40 bg-rose-500/15 px-1.5 py-0.5 font-mono text-[10px] text-rose-200"
                    >
                      EVENT FIRING
                    </span>
                  </div>
                  <div class="truncate text-[11px] text-slate-400">
                    {{ item.status?.reason ?? item.plugin.description }}
                  </div>
                </div>
              </div>

              <!-- Right: Mode Segmented Control + Test Event + Configure -->
              <div class="flex flex-wrap items-center gap-2 font-mono text-xs">
                <div class="inline-flex rounded-md border border-slate-800 bg-slate-950 p-0.5 text-[11px]">
                  <button
                    v-for="m in [
                      { id: 'always', label: 'Always' },
                      { id: 'on_event', label: 'On Event' },
                      { id: 'off', label: 'Off' },
                    ]"
                    :key="m.id"
                    type="button"
                    :disabled="m.id === 'on_event' && !item.plugin.supportsOnEvent"
                    :title="
                      m.id === 'on_event' && !item.plugin.supportsOnEvent
                        ? 'This plugin does not have event triggers'
                        : undefined
                    "
                    class="rounded px-2.5 py-1 font-semibold transition"
                    :class="
                      m.id === 'on_event' && !item.plugin.supportsOnEvent
                        ? 'cursor-not-allowed text-slate-600 opacity-40'
                        : item.mode === m.id
                          ? m.id === 'always'
                            ? 'bg-emerald-500/20 text-emerald-200'
                            : m.id === 'on_event'
                              ? 'bg-amber-500/20 text-amber-200'
                              : 'bg-slate-800 text-slate-300'
                          : 'text-slate-500 hover:text-slate-300'
                    "
                    @click="
                      updatePluginDynamicConfig(item.plugin.id, {
                        dynamicMode: m.id as PluginDynamicMode,
                      })
                    "
                  >
                    {{ m.label }}
                  </button>
                </div>

                <button
                  v-if="item.plugin.supportsOnEvent && item.mode === 'on_event'"
                  type="button"
                  :disabled="saving"
                  class="rounded-md border border-amber-500/40 bg-amber-500/15 px-2.5 py-1 text-[11px] font-semibold text-amber-200 transition hover:bg-amber-500/25 disabled:opacity-50"
                  @click="triggerPluginTestEvent(item.plugin.id)"
                >
                  Test Event
                </button>

                <button
                  type="button"
                  class="rounded-md border border-slate-700 bg-slate-950 px-2.5 py-1 text-[11px] text-slate-300 transition hover:border-cyan-500/50 hover:text-cyan-200"
                  @click="openPluginSettings(item.plugin.id)"
                >
                  Settings
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Manual Grid Template Selector -->
      <div v-if="config.layout_mode === 'manual'" class="mt-4 border-t border-slate-800 pt-4">
        <div class="mb-2.5 flex items-center justify-between">
          <span class="font-mono text-xs uppercase tracking-wider text-slate-400">
            Grid Layout Template
          </span>
          <span class="font-mono text-[11px] text-slate-500">
            Active: {{ config.manual_layout }} ({{ layout.slot_count }} slot{{ layout.slot_count === 1 ? '' : 's' }})
          </span>
        </div>

        <div class="grid grid-cols-2 gap-2.5 sm:grid-cols-4 lg:grid-cols-7">
          <button
            v-for="tpl in layoutTemplates"
            :key="tpl.id"
            type="button"
            class="group flex flex-col items-center rounded-lg border p-2.5 text-center transition"
            :class="
              config.manual_layout === tpl.id
                ? 'border-cyan-400/70 bg-cyan-500/15 text-cyan-100'
                : 'border-slate-800 bg-slate-950/70 text-slate-300 hover:border-slate-700'
            "
            @click="setManualLayout(tpl.id)"
          >
            <!-- Mini wireframe icon -->
            <div class="mb-2 grid h-9 w-14 gap-0.5 rounded border border-slate-700 bg-black p-1"
              :class="{
                'grid-cols-1 grid-rows-1': tpl.id === '1x1',
                'grid-cols-2 grid-rows-1': tpl.id === '2x1',
                'grid-cols-1 grid-rows-2': tpl.id === '1x2',
                'grid-cols-2 grid-rows-2': tpl.id === '2x2' || tpl.id === '2-big-1-small',
                'grid-cols-3 grid-rows-1': tpl.id === '3x1',
                'grid-cols-4 grid-rows-1': tpl.id === '4x1',
              }"
            >
              <span
                v-for="cell in tpl.slots"
                :key="cell"
                class="rounded-[1px]"
                :class="[
                  config.manual_layout === tpl.id ? 'bg-cyan-400/70' : 'bg-slate-600/70 group-hover:bg-cyan-500/40',
                  tpl.id === '2-big-1-small' && cell === 3 ? 'col-span-2' : '',
                ]"
              />
            </div>
            <div class="font-mono text-xs font-semibold">{{ tpl.label }}</div>
            <div class="text-[10px] text-slate-400">{{ tpl.subtitle }}</div>
          </button>
        </div>
      </div>
    </section>

    <!-- Interactive Grid Builder + Live 1:1 HUD Preview -->
    <section class="grid gap-6 lg:grid-cols-12">
      <!-- Left: Live 1:1 Preview Canvas -->
      <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-5 shadow-lg lg:col-span-7">
        <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 class="font-mono text-sm font-semibold uppercase tracking-wider text-cyan-300">
              Live 1:1 HUD Preview
            </h2>
            <p class="text-xs text-slate-400">
              {{ config.display_width }}×{{ config.display_height }}px ·
              {{ showMirroredPreview ? 'Mirrored (Combiner View)' : 'Normal Preview' }} ·
              Renderer: <span class="text-slate-200">{{ rendererMode }}</span>
            </p>
          </div>

          <div class="flex flex-wrap items-center gap-2 font-mono text-xs">
            <div class="inline-flex rounded-md border border-slate-800 bg-slate-950 p-0.5">
              <button
                type="button"
                class="rounded px-2 py-1 text-[11px] transition"
                :class="!showMirroredPreview ? 'bg-cyan-500/20 text-cyan-200' : 'text-slate-400'"
                @click="showMirroredPreview = false"
              >
                Normal Preview
              </button>
              <button
                type="button"
                class="rounded px-2 py-1 text-[11px] transition"
                :class="showMirroredPreview ? 'bg-cyan-500/20 text-cyan-200' : 'text-slate-400'"
                @click="showMirroredPreview = true"
              >
                Mirrored (Combiner)
              </button>
            </div>

            <button
              type="button"
              class="rounded-md border border-slate-700 bg-slate-950 px-2.5 py-1 text-[11px] text-slate-300 transition hover:border-cyan-500/50 hover:text-cyan-200"
              @click="showServerFrame = !showServerFrame"
            >
              {{ showServerFrame ? 'Interactive Canvas' : 'Server PNG Frame' }}
            </button>
          </div>
        </div>

        <!-- 1:1 Pixel-Exact Container -->
        <div class="flex flex-col items-center justify-center overflow-x-auto rounded-xl border border-cyan-500/30 bg-slate-950 p-4">
          <div
            v-if="showServerFrame"
            class="overflow-hidden border border-slate-800 bg-black"
            :style="{ width: `${config.display_width}px`, height: `${config.display_height}px` }"
          >
            <img
              :src="previewDataUrl"
              alt="Headless Server Captured HUD Frame"
              class="h-full w-full object-contain transition-transform duration-200"
              :class="showMirroredPreview ? '-scale-y-100' : ''"
            />
          </div>

          <HudGridCanvas
            v-else
            class="border border-slate-800 shadow-[0_0_30px_rgba(0,240,255,0.08)]"
            :layout="layout.active_layout"
            :slots="activeGridSlots"
            :width="config.display_width"
            :height="config.display_height"
            :plugin-settings="activePluginSettings"
            :plugin-data="layout.plugin_data"
            :interactive="config.layout_mode === 'manual'"
            :mirrored="showMirroredPreview"
            :selected-slot="selectedSlotIndex"
            @select-slot="(idx) => (selectedSlotIndex = idx)"
            @open-settings="(_idx, pluginId) => openPluginSettings(pluginId)"
          />
        </div>

        <!-- Quick Aspect Ratio / Resolution Switcher -->
        <div class="mt-4 flex flex-wrap items-center justify-between gap-2 font-mono text-xs">
          <span class="text-slate-400">Preview / TFT Canvas:</span>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="res in [
                { label: '480×320 (HRZN-01)', w: 480, h: 320 },
                { label: '320×240 (QVGA)', w: 320, h: 240 },
                { label: '240×240 (Round/Sq)', w: 240, h: 240 },
              ]"
              :key="res.label"
              type="button"
              class="rounded-md border px-2.5 py-1 text-[11px] transition"
              :class="
                config.display_width === res.w && config.display_height === res.h
                  ? 'border-cyan-400/60 bg-cyan-500/20 text-cyan-200'
                  : 'border-slate-800 bg-slate-950 text-slate-400 hover:border-slate-700 hover:text-slate-200'
              "
              @click="updateResolutionPreset(res.w, res.h)"
            >
              {{ res.label }}
            </button>
          </div>
        </div>
      </div>

      <!-- Right: Slot Assignment & Installed Plugin Registry -->
      <div class="space-y-6 lg:col-span-5">
        <!-- Slot Inspector -->
        <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-5 shadow-lg">
          <div class="mb-4 flex items-center justify-between">
            <div>
              <h2 class="font-mono text-sm font-semibold uppercase tracking-wider text-cyan-300">
                Slot Builder &amp; Assignment
              </h2>
              <p class="text-xs text-slate-400">
                {{
                  config.layout_mode === 'dynamic'
                    ? 'Dynamic Mode controls slot assignments automatically.'
                    : 'Click any slot in the preview or below to assign/swap plugins.'
                }}
              </p>
            </div>
            <span class="rounded border border-slate-700 bg-slate-950 px-2 py-0.5 font-mono text-xs text-cyan-300">
              Slot {{ selectedSlotIndex + 1 }} / {{ layout.slot_count }}
            </span>
          </div>

          <!-- Slot Tabs -->
          <div class="mb-4 grid grid-cols-4 gap-2 font-mono text-xs">
            <button
              v-for="idx in Array.from({ length: layout.slot_count }, (_, i) => i)"
              :key="idx"
              type="button"
              class="rounded-lg border px-2.5 py-2 text-left transition"
              :class="
                selectedSlotIndex === idx
                  ? 'border-cyan-400/70 bg-cyan-500/15 text-cyan-100'
                  : 'border-slate-800 bg-slate-950/70 text-slate-400 hover:border-slate-700'
              "
              @click="selectedSlotIndex = idx"
            >
              <div class="text-[10px] uppercase text-slate-500">Slot {{ idx + 1 }}</div>
              <div class="truncate font-semibold text-slate-200">
                {{ getPluginById(activeGridSlots[idx])?.id ?? 'Empty' }}
              </div>
            </button>
          </div>

          <!-- Selected Slot Actions -->
          <div class="rounded-lg border border-slate-800 bg-slate-950/70 p-4">
            <div class="mb-3 flex items-center justify-between">
              <div>
                <div class="font-mono text-xs uppercase text-slate-400">
                  Slot {{ selectedSlotIndex + 1 }} Occupant
                </div>
                <div class="font-mono text-sm font-semibold text-slate-100">
                  {{ selectedSlotPlugin ? selectedSlotPlugin.name : 'Empty (Black / Transparent)' }}
                </div>
              </div>

              <button
                v-if="selectedSlotPlugin"
                type="button"
                class="rounded-lg bg-cyan-500/20 px-3 py-1.5 font-mono text-xs font-semibold text-cyan-200 ring-1 ring-cyan-500/40 transition hover:bg-cyan-500/30"
                @click="openPluginSettings(selectedSlotPlugin.id)"
              >
                Plugin Settings
              </button>
            </div>

            <div class="space-y-3" :class="{ 'pointer-events-none opacity-50': config.layout_mode === 'dynamic' }">
              <div>
                <div class="mb-1.5 font-mono text-[11px] uppercase text-slate-400">
                  Assign Plugin
                </div>
                <div class="flex flex-wrap gap-2">
                  <button
                    v-for="plugin in PLUGIN_LIST"
                    :key="plugin.id"
                    type="button"
                    class="rounded-md border px-3 py-1.5 font-mono text-xs transition"
                    :class="
                      selectedSlotPluginId === plugin.id
                        ? 'border-cyan-400/70 bg-cyan-500/20 text-cyan-200'
                        : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-cyan-500/50'
                    "
                    @click="assignSlot(selectedSlotIndex, plugin.id)"
                  >
                    {{ plugin.name }}
                  </button>
                  <button
                    type="button"
                    class="rounded-md border px-3 py-1.5 font-mono text-xs transition"
                    :class="
                      selectedSlotPluginId === null
                        ? 'border-amber-400/70 bg-amber-500/15 text-amber-200'
                        : 'border-slate-700 bg-slate-900 text-slate-400 hover:border-amber-500/40 hover:text-amber-200'
                    "
                    @click="assignSlot(selectedSlotIndex, null)"
                  >
                    Leave Empty
                  </button>
                </div>
              </div>

              <div v-if="swapCandidates.length > 0">
                <div class="mb-1.5 font-mono text-[11px] uppercase text-slate-400">
                  Swap With Slot
                </div>
                <div class="flex flex-wrap gap-2">
                  <button
                    v-for="targetIdx in swapCandidates"
                    :key="targetIdx"
                    type="button"
                    class="rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1 font-mono text-xs text-slate-300 transition hover:border-cyan-500/50 hover:text-cyan-200"
                    @click="swapSlots(selectedSlotIndex, targetIdx)"
                  >
                    Swap with Slot {{ targetIdx + 1 }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Registered Plugins & Priority Status -->
        <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-5 shadow-lg">
          <div class="mb-3 flex items-center justify-between gap-2">
            <h2 class="font-mono text-sm font-semibold uppercase tracking-wider text-cyan-300">
              Registered HUD Plugins
            </h2>
            <button
              type="button"
              :disabled="reloadingPlugins"
              class="rounded-md border border-cyan-500/40 bg-cyan-500/10 px-2.5 py-1 font-mono text-[11px] font-semibold text-cyan-200 transition hover:bg-cyan-500/20 disabled:opacity-50"
              @click="triggerPluginReload"
            >
              {{ reloadingPlugins ? 'Reloading...' : 'Reload Plugins' }}
            </button>
          </div>
          <div class="space-y-2.5">
            <div
              v-for="plugin in PLUGIN_LIST"
              :key="plugin.id"
              class="flex items-start justify-between gap-3 rounded-lg border border-slate-800 bg-slate-950/70 p-3.5"
            >
              <div>
                <div class="flex flex-wrap items-center gap-2">
                  <span class="font-mono text-xs font-semibold text-slate-100">{{ plugin.name }}</span>
                  <span class="rounded border border-cyan-500/30 bg-cyan-500/10 px-1.5 py-0.5 font-mono text-[10px] text-cyan-300">
                    P{{ getPluginUserPriority(plugin.id) }}
                  </span>
                  <span
                    class="rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase"
                    :class="
                      getPluginDynamicMode(plugin.id) === 'always'
                        ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                        : getPluginDynamicMode(plugin.id) === 'on_event'
                          ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                          : 'border-slate-700 bg-slate-900 text-slate-500'
                    "
                  >
                    {{ getPluginDynamicMode(plugin.id).replace('_', ' ') }}
                  </span>
                </div>
                <p class="mt-1 text-xs text-slate-400">{{ plugin.description }}</p>
              </div>
              <button
                type="button"
                class="shrink-0 rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1.5 font-mono text-xs text-slate-200 transition hover:border-cyan-500/50 hover:text-cyan-200"
                @click="openPluginSettings(plugin.id)"
              >
                Configure
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Plugin Settings Drawer / Modal -->
    <div
      v-if="settingsModalPluginId && activeSettingsPlugin"
      class="fixed inset-0 z-50 flex items-center justify-end bg-slate-950/75 backdrop-blur-sm"
      @click.self="settingsModalPluginId = null"
    >
      <div class="flex h-full w-full max-w-md flex-col border-l border-slate-800 bg-slate-900 p-6 shadow-2xl">
        <div class="mb-5 flex items-start justify-between border-b border-slate-800 pb-4">
          <div>
            <div class="font-mono text-[11px] uppercase tracking-wider text-cyan-400">
              Plugin Settings
            </div>
            <h3 class="font-mono text-base font-semibold text-slate-100">
              {{ activeSettingsPlugin.name }}
            </h3>
          </div>
          <button
            type="button"
            class="rounded-md border border-slate-700 bg-slate-950 px-2.5 py-1 font-mono text-xs text-slate-400 hover:text-slate-100"
            @click="settingsModalPluginId = null"
          >
            Close
          </button>
        </div>

        <!-- Live Mini Preview inside Drawer -->
        <div class="mb-5 overflow-hidden rounded-lg border border-cyan-500/30 bg-black p-2">
          <div class="mx-auto h-36 w-full" style="container-type: size; container-name: hud-slot;">
            <component
              :is="activeSettingsPlugin.Widget"
              :settings="draftPluginSettings"
              :data="layout.plugin_data[activeSettingsPlugin.id] ?? {}"
            />
          </div>
        </div>

        <!-- Universal Dynamic Mode & Priority Controls + Plugin-Specific Settings -->
        <div class="flex-1 space-y-5 overflow-y-auto pr-1">
          <div class="space-y-3 rounded-lg border border-slate-800 bg-slate-950/80 p-3.5">
            <div class="flex items-center justify-between">
              <span class="font-mono text-[11px] font-semibold uppercase tracking-wider text-cyan-300">
                Dynamic Mode &amp; Priority
              </span>
              <button
                v-if="activeSettingsPlugin.supportsOnEvent && draftPluginSettings.dynamicMode === 'on_event'"
                type="button"
                :disabled="saving"
                class="rounded border border-amber-500/40 bg-amber-500/15 px-2 py-0.5 font-mono text-[10px] font-semibold text-amber-200 transition hover:bg-amber-500/25 disabled:opacity-50"
                @click="triggerPluginTestEvent(activeSettingsPlugin.id)"
              >
                Test Event
              </button>
            </div>

            <div class="grid grid-cols-3 gap-1.5 font-mono text-xs">
              <button
                v-for="m in [
                  { id: 'always', label: 'Always' },
                  { id: 'on_event', label: 'On Event' },
                  { id: 'off', label: 'Off' },
                ]"
                :key="m.id"
                type="button"
                :disabled="m.id === 'on_event' && !activeSettingsPlugin.supportsOnEvent"
                :title="
                  m.id === 'on_event' && !activeSettingsPlugin.supportsOnEvent
                    ? 'This plugin does not have event triggers'
                    : undefined
                "
                class="rounded-md border px-2 py-1.5 text-[11px] font-semibold transition"
                :class="
                  m.id === 'on_event' && !activeSettingsPlugin.supportsOnEvent
                    ? 'cursor-not-allowed border-slate-800/60 bg-slate-950 text-slate-600 opacity-40'
                    : draftPluginSettings.dynamicMode === m.id
                      ? 'border-cyan-400/70 bg-cyan-500/20 text-cyan-200'
                      : 'border-slate-800 bg-slate-900 text-slate-400 hover:border-slate-700'
                "
                @click="draftPluginSettings.dynamicMode = m.id"
              >
                {{ m.label }}
              </button>
            </div>

            <div class="flex items-center justify-between gap-3">
              <div>
                <div class="font-mono text-xs text-slate-200">Slot Priority (1–100)</div>
                <div class="text-[10px] text-slate-500">Higher priority claims earlier slots</div>
              </div>
              <input
                v-model.number="draftPluginSettings.userPriority"
                type="number"
                min="1"
                max="100"
                class="w-20 rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1 text-right font-mono text-xs font-semibold text-cyan-300 focus:border-cyan-500 focus:outline-none"
              />
            </div>
          </div>

          <component
            :is="activeSettingsPlugin.Settings"
            v-if="activeSettingsPlugin.Settings"
            v-model="draftPluginSettings"
          />
          <p v-else class="font-mono text-xs text-slate-400">
            This plugin has no additional widget settings.
          </p>
        </div>

        <div class="mt-5 flex items-center justify-end gap-3 border-t border-slate-800 pt-4">
          <button
            type="button"
            class="rounded-lg border border-slate-700 bg-slate-950 px-4 py-2 font-mono text-xs text-slate-300 hover:border-slate-500"
            @click="settingsModalPluginId = null"
          >
            Cancel
          </button>
          <button
            type="button"
            :disabled="saving"
            class="rounded-lg bg-cyan-500 px-5 py-2 font-mono text-xs font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:opacity-50"
            @click="applyDraftPluginSettings"
          >
            {{ saving ? 'Saving...' : 'Save Plugin Settings' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
