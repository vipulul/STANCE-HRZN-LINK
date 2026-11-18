<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import type { SpotifyPluginData, SpotifySettings } from './types'
import { DEFAULT_SPOTIFY_SETTINGS } from './types'

const props = withDefaults(
  defineProps<{
    settings?: Partial<SpotifySettings>
    data?: SpotifyPluginData
    slotIndex?: number
    layout?: string
  }>(),
  {
    settings: () => ({}),
    data: () => ({}),
    slotIndex: 0,
    layout: '1x1',
  },
)

const mergedSettings = computed<SpotifySettings>(() => ({
  ...DEFAULT_SPOTIFY_SETTINGS,
  ...props.settings,
}))

const isAuthenticated = computed<boolean>(() => Boolean(props.data?.authenticated))
const isPlaying = computed<boolean>(() => Boolean(isAuthenticated.value && props.data?.is_playing))
const trackTitle = computed<string>(() => String(props.data?.title ?? '').trim())
const trackArtist = computed<string>(() => String(props.data?.artist ?? '').trim())
const trackAlbum = computed<string>(() => String(props.data?.album ?? '').trim())
const hasActiveTrack = computed<boolean>(() => isAuthenticated.value && trackTitle.value.length > 0)

const durationMs = computed<number>(() => {
  const raw = Number(props.data?.duration_ms ?? 0)
  return Number.isFinite(raw) && raw > 0 ? Math.round(raw) : 0
})

// Smooth client-side interpolation between server WebSocket/poll ticks
const baseProgressMs = ref(0)
const baseSyncedAtMs = ref(Date.now())
const nowMs = ref(Date.now())
let progressTimer: ReturnType<typeof setInterval> | null = null

function syncProgressAnchor() {
  const raw = Number(props.data?.progress_ms ?? 0)
  baseProgressMs.value = Number.isFinite(raw) && raw > 0 ? Math.round(raw) : 0
  baseSyncedAtMs.value = Date.now()
  nowMs.value = baseSyncedAtMs.value
}

function updateProgressTimer() {
  if (progressTimer !== null) {
    clearInterval(progressTimer)
    progressTimer = null
  }
  if (isPlaying.value && durationMs.value > 0) {
    progressTimer = setInterval(() => {
      nowMs.value = Date.now()
    }, 250)
  }
}

watch(
  () => [props.data?.progress_ms, props.data?.track_id, props.data?.is_playing, props.data?.duration_ms],
  () => {
    syncProgressAnchor()
    updateProgressTimer()
  },
  { immediate: true },
)

const liveProgressMs = computed<number>(() => {
  if (!hasActiveTrack.value) return 0
  if (!isPlaying.value) {
    return durationMs.value > 0 ? Math.min(baseProgressMs.value, durationMs.value) : baseProgressMs.value
  }
  const elapsed = Math.max(0, nowMs.value - baseSyncedAtMs.value)
  const interpolated = baseProgressMs.value + elapsed
  return durationMs.value > 0 ? Math.min(interpolated, durationMs.value) : interpolated
})

const progressPct = computed<number>(() => {
  if (durationMs.value <= 0) return 0
  return Math.max(0, Math.min(100, (liveProgressMs.value / durationMs.value) * 100))
})

function formatDuration(ms: number): string {
  const totalSec = Math.max(0, Math.floor(ms / 1000))
  const hours = Math.floor(totalSec / 3600)
  const mins = Math.floor((totalSec % 3600) / 60)
  const secs = totalSec % 60
  if (hours > 0) {
    return `${hours}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
  }
  return `${mins}:${String(secs).padStart(2, '0')}`
}

const elapsedDisplay = computed<string>(() => formatDuration(liveProgressMs.value))
const durationDisplay = computed<string>(() => (durationMs.value > 0 ? formatDuration(durationMs.value) : '--:--'))
const remainingDisplay = computed<string>(() => {
  if (durationMs.value <= 0) return '--:--'
  return `-${formatDuration(Math.max(0, durationMs.value - liveProgressMs.value))}`
})

const statusLabel = computed<string>(() => {
  if (!isAuthenticated.value) return 'AUTH REQUIRED'
  if (!hasActiveTrack.value) return 'IDLE'
  return isPlaying.value ? 'NOW PLAYING' : 'PAUSED'
})

const compactBadgeLabel = computed<string>(() => {
  if (!isAuthenticated.value) return 'AUTH REQ'
  if (!hasActiveTrack.value) return 'IDLE'
  return isPlaying.value ? 'NOW PLAYING' : 'PAUSED'
})

// Overflow detection for smooth CSS marquee
const widgetRootRef = ref<HTMLElement | null>(null)
const fullTitleViewportRef = ref<HTMLElement | null>(null)
const fullTitleMeasureRef = ref<HTMLElement | null>(null)
const compactTitleViewportRef = ref<HTMLElement | null>(null)
const compactTitleMeasureRef = ref<HTMLElement | null>(null)

const fullTitleOverflow = ref(false)
const compactTitleOverflow = ref(false)
let resizeObserver: ResizeObserver | null = null

function measureTitleOverflow() {
  if (fullTitleViewportRef.value && fullTitleMeasureRef.value) {
    const vpWidth = fullTitleViewportRef.value.clientWidth
    const textWidth = fullTitleMeasureRef.value.offsetWidth
    fullTitleOverflow.value = vpWidth > 0 && textWidth > vpWidth + 2
  } else {
    fullTitleOverflow.value = false
  }

  if (compactTitleViewportRef.value && compactTitleMeasureRef.value) {
    const vpWidth = compactTitleViewportRef.value.clientWidth
    const textWidth = compactTitleMeasureRef.value.offsetWidth
    compactTitleOverflow.value = vpWidth > 0 && textWidth > vpWidth + 2
  } else {
    compactTitleOverflow.value = false
  }
}

watch(
  () => [trackTitle.value, props.layout, props.slotIndex, hasActiveTrack.value],
  async () => {
    await nextTick()
    measureTitleOverflow()
  },
)

onMounted(async () => {
  await nextTick()
  measureTitleOverflow()
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      measureTitleOverflow()
    })
    if (widgetRootRef.value) resizeObserver.observe(widgetRootRef.value)
    if (fullTitleViewportRef.value) resizeObserver.observe(fullTitleViewportRef.value)
    if (compactTitleViewportRef.value) resizeObserver.observe(compactTitleViewportRef.value)
  }
})

onUnmounted(() => {
  if (progressTimer !== null) {
    clearInterval(progressTimer)
    progressTimer = null
  }
  if (resizeObserver !== null) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
})
</script>

<template>
  <div
    ref="widgetRootRef"
    class="spotify-widget"
    :class="{
      'is-playing': isPlaying,
      'is-unauth': !isAuthenticated,
      'is-idle': isAuthenticated && !hasActiveTrack,
    }"
    :style="{ '--sp-accent': mergedSettings.accentColor }"
  >
    <!-- Tactical corner reticles (hidden in narrow/shallow slots via @container) -->
    <span class="reticle reticle-tl" aria-hidden="true" />
    <span class="reticle reticle-tr" aria-hidden="true" />
    <span class="reticle reticle-bl" aria-hidden="true" />
    <span class="reticle reticle-br" aria-hidden="true" />

    <!-- Medium & Full Slot Layout -->
    <div class="sp-full">
      <header class="sp-header">
        <div class="sp-brand">
          <span class="sp-dot" :class="{ 'dot-live': isPlaying, 'dot-warn': !isAuthenticated }" />
          <span class="sp-header-tag">SPOTIFY // {{ statusLabel }}</span>
        </div>

        <div
          v-if="mergedSettings.showEqualizer && hasActiveTrack"
          class="eq-bars"
          :class="{ 'eq-active': isPlaying }"
          aria-hidden="true"
        >
          <span class="eq-bar bar-1" />
          <span class="eq-bar bar-2" />
          <span class="eq-bar bar-3" />
          <span class="eq-bar bar-4" />
        </div>
      </header>

      <!-- Idle / Unauthenticated Center State -->
      <div v-if="!hasActiveTrack" class="sp-standby">
        <div class="standby-code">
          {{ !isAuthenticated ? 'SPOTIFY // AUTH REQUIRED' : 'SPOTIFY // IDLE' }}
        </div>
        <div class="standby-sub">
          {{ !isAuthenticated ? 'LINK ACCOUNT IN HUD STUDIO' : 'NO ACTIVE PLAYBACK' }}
        </div>
      </div>

      <!-- Active Track Hero & Progress -->
      <template v-else>
        <div class="sp-track-hero">
          <div ref="fullTitleViewportRef" class="title-viewport">
            <div class="title-track" :class="{ 'is-marquee': fullTitleOverflow }">
              <span ref="fullTitleMeasureRef" class="sp-title">{{ trackTitle }}</span>
              <span v-if="fullTitleOverflow" class="sp-title" aria-hidden="true">{{ trackTitle }}</span>
            </div>
          </div>

          <div v-if="mergedSettings.showArtist && trackArtist" class="sp-artist">
            {{ trackArtist }}
          </div>

          <div v-if="mergedSettings.showAlbum && trackAlbum" class="sp-album">
            {{ trackAlbum }}
          </div>
        </div>

        <footer
          v-if="mergedSettings.showProgressBar || mergedSettings.showTimeRemaining"
          class="sp-footer"
        >
          <div v-if="mergedSettings.showTimeRemaining" class="sp-time-row">
            <span class="sp-time-elapsed">{{ elapsedDisplay }}</span>
            <span class="sp-time-total">{{ durationDisplay }}</span>
            <span class="sp-time-rem">{{ remainingDisplay }}</span>
          </div>

          <div
            v-if="mergedSettings.showProgressBar"
            class="sp-progress-track"
            role="progressbar"
            :aria-valuenow="Math.round(progressPct)"
            aria-valuemin="0"
            aria-valuemax="100"
          >
            <div class="sp-progress-fill" :style="{ width: `${progressPct}%` }" />
            <div class="sp-progress-ticks" aria-hidden="true" />
          </div>
        </footer>
      </template>
    </div>

    <!-- Compact Layout (@container max-width: 155px or max-height: 135px) -->
    <div class="sp-compact">
      <div class="compact-head">
        <div class="compact-badge-row">
          <span class="sp-dot" :class="{ 'dot-live': isPlaying, 'dot-warn': !isAuthenticated }" />
          <span class="compact-badge">{{ compactBadgeLabel }}</span>
        </div>

        <div
          v-if="mergedSettings.showEqualizer && hasActiveTrack"
          class="eq-bars eq-compact"
          :class="{ 'eq-active': isPlaying }"
          aria-hidden="true"
        >
          <span class="eq-bar bar-1" />
          <span class="eq-bar bar-2" />
          <span class="eq-bar bar-3" />
          <span class="eq-bar bar-4" />
        </div>
      </div>

      <div v-if="!hasActiveTrack" class="compact-standby">
        <div class="compact-standby-main">
          {{ !isAuthenticated ? 'AUTH REQUIRED' : 'SPOTIFY // IDLE' }}
        </div>
        <div class="compact-standby-sub">
          {{ !isAuthenticated ? 'LINK SPOTIFY' : 'NO TRACK' }}
        </div>
      </div>

      <div v-else class="compact-body">
        <div ref="compactTitleViewportRef" class="title-viewport">
          <div class="title-track" :class="{ 'is-marquee': compactTitleOverflow }">
            <span ref="compactTitleMeasureRef" class="compact-title">{{ trackTitle }}</span>
            <span v-if="compactTitleOverflow" class="compact-title" aria-hidden="true">{{ trackTitle }}</span>
          </div>
        </div>

        <div v-if="mergedSettings.showArtist && trackArtist" class="compact-artist">
          {{ trackArtist }}
        </div>

        <div v-if="mergedSettings.showTimeRemaining" class="compact-time">
          {{ elapsedDisplay }} / {{ durationDisplay }}
        </div>
      </div>

      <div
        v-if="mergedSettings.showProgressBar && hasActiveTrack"
        class="compact-progress-track"
      >
        <div class="compact-progress-fill" :style="{ width: `${progressPct}%` }" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.spotify-widget {
  position: relative;
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  background: #000000;
  color: #ffffff;
  overflow: hidden;
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-variant-numeric: tabular-nums;
  user-select: none;
  padding: clamp(8px, 3.6cqmin, 18px);
}

/* Corner reticles */
.reticle {
  position: absolute;
  width: clamp(7px, 3.4cqmin, 13px);
  height: clamp(7px, 3.4cqmin, 13px);
  border-color: var(--sp-accent);
  pointer-events: none;
  opacity: 0.9;
}

.reticle-tl {
  top: 5px;
  left: 5px;
  border-top: 2px solid;
  border-left: 2px solid;
}

.reticle-tr {
  top: 5px;
  right: 5px;
  border-top: 2px solid;
  border-right: 2px solid;
}

.reticle-bl {
  bottom: 5px;
  left: 5px;
  border-bottom: 2px solid;
  border-left: 2px solid;
}

.reticle-br {
  bottom: 5px;
  right: 5px;
  border-bottom: 2px solid;
  border-right: 2px solid;
}

/* Full / Medium View */
.sp-full {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  width: 100%;
  height: 100%;
  gap: clamp(6px, 3cqh, 14px);
}

.sp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: clamp(4px, 1.8cqh, 8px);
  border-bottom: 1px solid color-mix(in srgb, var(--sp-accent) 42%, #334155);
  flex-shrink: 0;
}

.sp-brand {
  display: flex;
  align-items: center;
  gap: clamp(5px, 1.8cqw, 9px);
  min-width: 0;
}

.sp-dot {
  width: clamp(7px, 2.2cqmin, 10px);
  height: clamp(7px, 2.2cqmin, 10px);
  border-radius: 999px;
  background: #94a3b8;
  flex-shrink: 0;
}

.sp-dot.dot-live {
  background: var(--sp-accent);
  box-shadow: 0 0 8px var(--sp-accent);
}

.sp-dot.dot-warn {
  background: #fbbf24;
  box-shadow: 0 0 8px #fbbf24;
}

.sp-header-tag {
  font-size: clamp(9px, min(3.4cqw, 5cqh), 13px);
  font-weight: 700;
  letter-spacing: 0.11em;
  color: var(--sp-accent);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.spotify-widget.is-unauth .sp-header-tag {
  color: #fbbf24;
}

/* Equalizer Bars */
.eq-bars {
  display: flex;
  align-items: flex-end;
  gap: clamp(2px, 0.8cqw, 4px);
  height: clamp(12px, 6cqh, 22px);
  flex-shrink: 0;
}

.eq-bars.eq-compact {
  height: clamp(10px, 12cqh, 16px);
}

.eq-bar {
  width: clamp(3px, 1cqw, 5px);
  height: 24%;
  background: var(--sp-accent);
  border-radius: 1px;
  transform-origin: bottom;
}

.eq-bars.eq-active .bar-1 {
  animation: sp-eq-a 0.72s ease-in-out infinite;
}

.eq-bars.eq-active .bar-2 {
  animation: sp-eq-b 0.58s ease-in-out 0.14s infinite;
}

.eq-bars.eq-active .bar-3 {
  animation: sp-eq-c 0.82s ease-in-out 0.06s infinite;
}

.eq-bars.eq-active .bar-4 {
  animation: sp-eq-d 0.64s ease-in-out 0.22s infinite;
}

@keyframes sp-eq-a {
  0%, 100% { height: 28%; }
  50% { height: 95%; }
}

@keyframes sp-eq-b {
  0%, 100% { height: 60%; }
  45% { height: 22%; }
  80% { height: 100%; }
}

@keyframes sp-eq-c {
  0%, 100% { height: 35%; }
  40% { height: 88%; }
  75% { height: 30%; }
}

@keyframes sp-eq-d {
  0%, 100% { height: 75%; }
  50% { height: 25%; }
  85% { height: 92%; }
}

/* Standby / Auth Required */
.sp-standby {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: clamp(4px, 2.2cqh, 10px);
  padding: 0 4px;
}

.standby-code {
  font-size: clamp(12px, min(5.2cqw, 8.5cqh), 24px);
  font-weight: 700;
  letter-spacing: 0.1em;
  color: #ffffff;
}

.spotify-widget.is-unauth .standby-code {
  color: #fbbf24;
}

.standby-sub {
  font-size: clamp(9px, min(3.4cqw, 5cqh), 13px);
  font-weight: 600;
  letter-spacing: 0.12em;
  color: #cbd5e1;
}

/* Track Hero */
.sp-track-hero {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: clamp(3px, 1.8cqh, 9px);
}

.title-viewport {
  width: 100%;
  min-width: 0;
  overflow: hidden;
}

.title-track {
  display: inline-flex;
  align-items: baseline;
  white-space: nowrap;
  gap: 32px;
  min-width: 100%;
}

.title-track.is-marquee {
  min-width: auto;
  animation: sp-marquee 11s linear infinite;
}

@keyframes sp-marquee {
  0%, 12% {
    transform: translateX(0);
  }
  88%, 100% {
    transform: translateX(calc(-50% - 16px));
  }
}

.sp-title {
  font-size: clamp(16px, min(7.2cqw, 12cqh), 34px);
  font-weight: 700;
  line-height: 1.15;
  letter-spacing: -0.02em;
  color: #ffffff;
}

.sp-artist {
  font-size: clamp(11px, min(4.6cqw, 7.2cqh), 20px);
  font-weight: 600;
  color: #e2e8f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sp-album {
  font-size: clamp(9px, min(3.4cqw, 5.4cqh), 14px);
  font-weight: 500;
  letter-spacing: 0.04em;
  color: #cbd5e1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Footer Progress & Time */
.sp-footer {
  display: flex;
  flex-direction: column;
  gap: clamp(4px, 1.8cqh, 8px);
  flex-shrink: 0;
}

.sp-time-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  font-size: clamp(10px, min(3.6cqw, 5.4cqh), 15px);
  font-weight: 700;
  letter-spacing: 0.04em;
}

.sp-time-elapsed {
  color: var(--sp-accent);
}

.sp-time-total {
  color: #cbd5e1;
}

.sp-time-rem {
  color: #e2e8f0;
}

.sp-progress-track {
  position: relative;
  width: 100%;
  height: clamp(6px, 2.6cqh, 11px);
  background: #1e293b;
  border: 1px solid color-mix(in srgb, var(--sp-accent) 40%, #334155);
  border-radius: 3px;
  overflow: hidden;
}

.sp-progress-fill {
  height: 100%;
  background: var(--sp-accent);
  transition: width 0.22s linear;
}

.sp-progress-ticks {
  position: absolute;
  inset: 0;
  background-image: repeating-linear-gradient(
    to right,
    transparent,
    transparent calc(10% - 2px),
    #000000 calc(10% - 2px),
    #000000 10%
  );
  pointer-events: none;
}

/* Compact Layout (hidden in medium/full slots) */
.sp-compact {
  display: none;
  position: relative;
  width: 100%;
  height: 100%;
}

.compact-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  flex-shrink: 0;
}

.compact-badge-row {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}

.compact-badge {
  font-size: clamp(8px, min(6cqw, 13cqh), 12px);
  font-weight: 700;
  letter-spacing: 0.09em;
  color: var(--sp-accent);
  white-space: nowrap;
}

.spotify-widget.is-unauth .compact-badge {
  color: #fbbf24;
}

.compact-body {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 2px;
}

.compact-title {
  font-size: clamp(13px, min(11cqw, 26cqh), 24px);
  font-weight: 700;
  line-height: 1.15;
  color: #ffffff;
}

.compact-artist {
  font-size: clamp(10px, min(8cqw, 16cqh), 15px);
  font-weight: 600;
  color: #e2e8f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.compact-time {
  font-size: clamp(9px, min(7.5cqw, 15cqh), 13px);
  font-weight: 700;
  color: var(--sp-accent);
  white-space: nowrap;
}

.compact-standby {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  min-width: 0;
}

.compact-standby-main {
  font-size: clamp(11px, min(9cqw, 22cqh), 18px);
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #ffffff;
}

.spotify-widget.is-unauth .compact-standby-main {
  color: #fbbf24;
}

.compact-standby-sub {
  font-size: clamp(8px, min(6.5cqw, 14cqh), 12px);
  font-weight: 600;
  letter-spacing: 0.1em;
  color: #cbd5e1;
}

.compact-progress-track {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: clamp(3px, 4cqh, 5px);
  background: #1e293b;
  overflow: hidden;
}

.compact-progress-fill {
  height: 100%;
  background: var(--sp-accent);
  transition: width 0.22s linear;
}

/* Medium-narrow vertical slot tweak (e.g., 2x1 at 320x240) */
@container hud-slot (max-width: 220px) {
  .sp-time-total {
    display: none;
  }
}

/* Wide shallow slots (1x2, compact bottom slot of 2-big-1-small) */
@container hud-slot (max-height: 135px) {
  .reticle,
  .sp-full {
    display: none;
  }

  .spotify-widget {
    padding: clamp(6px, 4cqh, 12px) clamp(10px, 3cqw, 18px) clamp(10px, 8cqh, 16px);
  }

  .sp-compact {
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    gap: clamp(10px, 3.5cqw, 20px);
  }

  .compact-head {
    flex-direction: row;
    gap: 8px;
  }

  .compact-body {
    flex: 1;
    justify-content: center;
  }

  .compact-standby {
    flex: 1;
    align-items: flex-end;
    text-align: right;
  }

  .compact-time {
    display: none;
  }

  .compact-title {
    font-size: clamp(14px, 24cqh, 24px);
  }

  .compact-artist {
    font-size: clamp(10px, 15cqh, 14px);
  }
}

/* Narrow vertical strips (3x1, 4x1) */
@container hud-slot (max-width: 155px) {
  .reticle,
  .sp-full {
    display: none;
  }

  .spotify-widget {
    padding: clamp(8px, 3cqw, 12px) clamp(6px, 4cqw, 10px) clamp(12px, 4cqh, 16px);
  }

  .sp-compact {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    justify-content: space-between;
    gap: clamp(8px, 4cqh, 16px);
  }

  .compact-head {
    flex-direction: column;
    align-items: center;
    gap: clamp(6px, 3cqh, 10px);
  }

  .compact-body {
    flex: 1;
    justify-content: center;
    text-align: center;
    gap: clamp(4px, 2cqh, 8px);
  }

  .compact-standby {
    flex: 1;
    align-items: center;
    text-align: center;
  }

  .compact-time {
    display: block;
    font-size: clamp(9px, 8cqw, 13px);
  }

  .compact-title {
    font-size: clamp(13px, min(13cqw, 18cqh), 20px);
  }

  .compact-artist {
    font-size: clamp(10px, 9cqw, 13px);
  }
}
</style>
