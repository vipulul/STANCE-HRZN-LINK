<script setup lang="ts">
import { computed } from 'vue'
import { getPluginById } from '../plugins/registry'
import type { GridLayoutId } from '../types/hrzn'

const props = withDefaults(
  defineProps<{
    layout: GridLayoutId
    slots: Array<string | null>
    width: number
    height: number
    pluginSettings: Record<string, Record<string, unknown>>
    pluginData?: Record<string, Record<string, unknown>>
    interactive?: boolean
    mirrored?: boolean
    selectedSlot?: number | null
  }>(),
  {
    pluginData: () => ({}),
    interactive: false,
    mirrored: false,
    selectedSlot: null,
  },
)

const emit = defineEmits<{
  (e: 'select-slot', index: number): void
  (e: 'open-settings', index: number, pluginId: string): void
}>()

const SLOT_COUNTS: Record<GridLayoutId, number> = {
  '1x1': 1,
  '2x1': 2,
  '1x2': 2,
  '2-big-1-small': 3,
  '3x1': 3,
  '2x2': 4,
  '4x1': 4,
}

const activeSlotIndices = computed(() =>
  Array.from({ length: SLOT_COUNTS[props.layout] ?? 1 }, (_, i) => i),
)

function slotRoleLabel(idx: number): string {
  if (props.layout === '2-big-1-small') {
    return idx < 2 ? `PRIMARY ${idx + 1}` : 'COMPACT'
  }
  return `SLOT ${idx + 1}`
}

function getSlotPlugin(idx: number) {
  const pluginId = props.slots[idx] ?? null
  return getPluginById(pluginId)
}

function handleSlotClick(idx: number) {
  if (!props.interactive) return
  emit('select-slot', idx)
}

function handleOpenSettings(idx: number, pluginId: string, evt: MouseEvent) {
  evt.stopPropagation()
  emit('open-settings', idx, pluginId)
}
</script>

<template>
  <div
    class="hud-canvas-root"
    :class="[`layout-${layout}`, { 'is-mirrored': mirrored, 'is-interactive': interactive }]"
    :style="{
      width: `${width}px`,
      height: `${height}px`,
    }"
  >
    <div
      v-for="idx in activeSlotIndices"
      :key="idx"
      class="hud-slot"
      :class="{
        'span-2': layout === '2-big-1-small' && idx === 2,
        'is-selected': interactive && selectedSlot === idx,
        'is-empty': !getSlotPlugin(idx),
      }"
      @click="handleSlotClick(idx)"
    >
      <component
        :is="getSlotPlugin(idx)!.Widget"
        v-if="getSlotPlugin(idx)"
        :settings="pluginSettings[getSlotPlugin(idx)!.id] ?? getSlotPlugin(idx)!.defaultSettings"
        :data="pluginData[getSlotPlugin(idx)!.id] ?? {}"
        :slot-index="idx"
        :layout="layout"
      />

      <div v-else-if="interactive" class="empty-slot-placeholder">
        <span class="font-mono text-[10px] uppercase tracking-widest text-slate-600">
          Empty Slot
        </span>
        <span class="mt-0.5 font-mono text-[9px] text-slate-700">
          Click to assign
        </span>
      </div>

      <!-- Studio Interactive Overlay -->
      <div
        v-if="interactive"
        class="slot-overlay"
        :class="{ 'slot-overlay-flipped': mirrored }"
      >
        <div class="flex items-center justify-between gap-1">
          <span class="rounded bg-slate-950/85 px-1.5 py-0.5 font-mono text-[9px] font-semibold tracking-wider text-cyan-300 ring-1 ring-cyan-500/30">
            {{ slotRoleLabel(idx) }}
          </span>

          <button
            v-if="getSlotPlugin(idx)"
            type="button"
            class="rounded bg-slate-950/90 px-1.5 py-0.5 font-mono text-[9px] text-slate-200 ring-1 ring-slate-700 transition hover:text-cyan-200 hover:ring-cyan-400"
            title="Plugin Settings"
            @click="handleOpenSettings(idx, getSlotPlugin(idx)!.id, $event)"
          >
            Settings
          </button>
        </div>

        <div class="flex items-center justify-between">
          <span class="rounded bg-slate-950/80 px-1.5 py-0.5 font-mono text-[9px] text-slate-400">
            {{ getSlotPlugin(idx)?.name ?? 'Unassigned' }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.hud-canvas-root {
  display: grid;
  background: #000000;
  overflow: hidden;
  box-sizing: border-box;
  gap: 2px;
  transition: transform 0.2s ease;
}

.hud-canvas-root.is-mirrored {
  transform: scaleY(-1);
}

.layout-1x1 {
  grid-template-columns: 1fr;
  grid-template-rows: 1fr;
}

.layout-2x1 {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr;
}

.layout-1x2 {
  grid-template-columns: 1fr;
  grid-template-rows: 1fr 1fr;
}

.layout-2x2 {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
}

.layout-2-big-1-small {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1.75fr 1fr;
}

.layout-3x1 {
  grid-template-columns: repeat(3, 1fr);
  grid-template-rows: 1fr;
}

.layout-4x1 {
  grid-template-columns: repeat(4, 1fr);
  grid-template-rows: 1fr;
}

.hud-slot {
  position: relative;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: #000000;
  container-type: size;
  container-name: hud-slot;
}

.hud-slot.span-2 {
  grid-column: span 2;
}

.is-interactive .hud-slot {
  cursor: pointer;
  outline: 1px dashed rgba(30, 41, 59, 0.85);
  outline-offset: -1px;
}

.is-interactive .hud-slot:hover {
  outline: 1px solid rgba(34, 211, 238, 0.55);
}

.is-interactive .hud-slot.is-selected {
  outline: 2px solid rgba(34, 211, 238, 0.95);
  outline-offset: -2px;
}

.empty-slot-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #020408;
}

.slot-overlay {
  position: absolute;
  inset: 0;
  padding: 5px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  opacity: 0;
  background: linear-gradient(180deg, rgba(2, 6, 23, 0.55) 0%, transparent 45%, rgba(2, 6, 23, 0.55) 100%);
  transition: opacity 0.15s ease;
  pointer-events: none;
}

.slot-overlay-flipped {
  transform: scaleY(-1);
}

.slot-overlay button {
  pointer-events: auto;
}

.hud-slot:hover .slot-overlay,
.hud-slot.is-selected .slot-overlay {
  opacity: 1;
}
</style>
