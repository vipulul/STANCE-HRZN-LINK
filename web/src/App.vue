<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useHrznState } from './composables/useHrznState'
import HardwareDebugView from './views/HardwareDebugView.vue'
import HudRenderView from './views/HudRenderView.vue'
import HudStudioView from './views/HudStudioView.vue'

const { uiConnected, device, statusMessage, startConnection } = useHrznState()

const currentPath = ref<string>(window.location.pathname || '/')

function syncPath() {
  currentPath.value = window.location.pathname || '/'
}

function navigate(path: string) {
  if (currentPath.value === path) return
  window.history.pushState({}, '', path)
  currentPath.value = path
}

const isBareRenderRoute = computed(() => currentPath.value.startsWith('/hud-render'))
const isSettingsRoute = computed(() => currentPath.value.startsWith('/settings'))
const isHeadlessCapture = computed(
  () => isBareRenderRoute.value && window.location.search.includes('headless=1'),
)

onMounted(() => {
  if (!isHeadlessCapture.value) {
    startConnection()
  }
  window.addEventListener('popstate', syncPath)
})

onBeforeUnmount(() => {
  window.removeEventListener('popstate', syncPath)
})
</script>

<template>
  <!-- Bare Headless Render Surface (/hud-render) -->
  <HudRenderView v-if="isBareRenderRoute" />

  <!-- Companion Web UI (/ & /settings) -->
  <div v-else class="min-h-screen bg-slate-950 text-slate-100">
    <header class="border-b border-slate-800/80 bg-slate-900/75 backdrop-blur">
      <div class="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-3.5">
        <div class="flex items-center gap-6">
          <a
            href="/"
            class="flex items-center gap-3"
            @click.prevent="navigate('/')"
          >
            <div class="flex h-9 w-9 items-center justify-center rounded-lg border border-cyan-500/40 bg-cyan-500/10 font-mono text-sm font-bold text-cyan-300">
              HZ
            </div>
            <div>
              <div class="flex items-center gap-2">
                <span class="font-mono text-base font-semibold tracking-wide text-slate-100">
                  STANCE // HRZN-LINK
                </span>
                <span class="rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 font-mono text-[11px] text-cyan-300">
                  HRZN-01
                </span>
              </div>
              <p class="text-[11px] text-slate-400">
                Modular Optical HUD Studio &amp; Calibration Host
              </p>
            </div>
          </a>

          <!-- Primary Navigation -->
          <nav class="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-950/80 p-1 font-mono text-xs">
            <a
              href="/"
              class="rounded-md px-3 py-1.5 font-semibold transition"
              :class="
                !isSettingsRoute
                  ? 'bg-cyan-500/20 text-cyan-200 ring-1 ring-cyan-500/40'
                  : 'text-slate-400 hover:text-slate-200'
              "
              @click.prevent="navigate('/')"
            >
              HUD Studio
            </a>
            <a
              href="/settings"
              class="rounded-md px-3 py-1.5 font-semibold transition"
              :class="
                isSettingsRoute
                  ? 'bg-cyan-500/20 text-cyan-200 ring-1 ring-cyan-500/40'
                  : 'text-slate-400 hover:text-slate-200'
              "
              @click.prevent="navigate('/settings')"
            >
              Hardware &amp; Debug
            </a>
          </nav>
        </div>

        <!-- Connection & Action Status Badges -->
        <div class="flex flex-wrap items-center gap-2.5 font-mono text-xs">
          <span
            v-if="statusMessage"
            class="rounded-md border border-cyan-500/40 bg-cyan-500/10 px-3 py-1.5 text-cyan-200"
          >
            {{ statusMessage }}
          </span>

          <div class="flex items-center gap-2 rounded-md border border-slate-800 bg-slate-950 px-3 py-1.5">
            <span
              class="h-2 w-2 rounded-full"
              :class="uiConnected ? 'bg-emerald-400' : 'bg-rose-500'"
            />
            <span class="text-slate-300">UI {{ uiConnected ? 'LIVE' : 'OFFLINE' }}</span>
          </div>

          <div class="flex items-center gap-2 rounded-md border border-slate-800 bg-slate-950 px-3 py-1.5">
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

    <main class="mx-auto max-w-7xl px-6 py-6">
      <HardwareDebugView v-if="isSettingsRoute" />
      <HudStudioView v-else />
    </main>
  </div>
</template>
