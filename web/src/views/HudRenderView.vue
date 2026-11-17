<script setup lang="ts">
import { computed } from 'vue'
import HudGridCanvas from '../components/HudGridCanvas.vue'
import { useHrznState } from '../composables/useHrznState'

const { config, layout } = useHrznState()

const activeGridSlots = computed(() =>
  config.layout_mode === 'dynamic' ? layout.slots : config.grid_slots,
)

const activePluginSettings = computed(() =>
  config.layout_mode === 'dynamic' ? layout.effective_plugin_settings : config.plugin_configs,
)
</script>

<template>
  <div
    id="hud-render-root"
    class="m-0 overflow-hidden bg-black p-0"
    :style="{
      width: `${config.display_width}px`,
      height: `${config.display_height}px`,
    }"
  >
    <HudGridCanvas
      :layout="layout.active_layout"
      :slots="activeGridSlots"
      :width="config.display_width"
      :height="config.display_height"
      :plugin-settings="activePluginSettings"
      :plugin-data="layout.plugin_data"
      :interactive="false"
      :mirrored="false"
    />
  </div>
</template>
