<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import type { SpotifySettings } from './types'
import { DEFAULT_SPOTIFY_SETTINGS } from './types'

interface SpotifyStatusResponse {
  authenticated: boolean
  configured: boolean
  redirect_uri?: string
  is_playing?: boolean
  track_id?: string | null
  title?: string | null
  artist?: string | null
  album?: string | null
  error?: string | null
}

const props = defineProps<{
  modelValue?: Partial<SpotifySettings>
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: SpotifySettings): void
}>()

const current = computed<SpotifySettings>(() => ({
  ...DEFAULT_SPOTIFY_SETTINGS,
  ...props.modelValue,
}))

function updateField<K extends keyof SpotifySettings>(key: K, value: SpotifySettings[K]) {
  emit('update:modelValue', {
    ...current.value,
    [key]: value,
  })
}

const showSecret = ref(false)
const copiedUri = ref(false)
const statusLoading = ref(false)
const connecting = ref(false)
const disconnecting = ref(false)
const authenticated = ref(false)
const statusTitle = ref<string | null>(null)
const statusArtist = ref<string | null>(null)
const statusPlaying = ref(false)
const authError = ref('')

let authPollTimer: ReturnType<typeof setInterval> | null = null
let copyResetTimer: ReturnType<typeof setTimeout> | null = null

const LOOPBACK_REDIRECT_URI = 'http://127.0.0.1:8080/api/plugins/spotify/callback'

const redirectUriDisplay = computed(() => {
  const raw = current.value.redirectUri?.trim()
  if (!raw || raw === 'http://localhost:8080/api/plugins/spotify/callback') {
    return LOOPBACK_REDIRECT_URI
  }
  return raw
})

async function fetchWithPluginReload(url: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(url, init)
  if (res.status !== 404) {
    return res
  }
  const reloadRes = await fetch('/api/plugins/reload', { method: 'POST' })
  if (!reloadRes.ok) {
    return res
  }
  return fetch(url, init)
}

async function refreshStatus() {
  statusLoading.value = true
  try {
    const res = await fetchWithPluginReload('/api/plugins/spotify/status', { cache: 'no-store' })
    if (!res.ok) {
      throw new Error(`Status check failed (${res.status})`)
    }
    const payload = (await res.json()) as SpotifyStatusResponse
    authenticated.value = Boolean(payload.authenticated)
    statusPlaying.value = Boolean(payload.is_playing)
    statusTitle.value = payload.title ?? null
    statusArtist.value = payload.artist ?? null
    if (payload.error) {
      authError.value = payload.error
    } else if (authenticated.value) {
      authError.value = ''
    }
  } catch (err) {
    authError.value = err instanceof Error ? err.message : 'Unable to check Spotify status.'
  } finally {
    statusLoading.value = false
  }
}

async function copyRedirectUri() {
  const uri = redirectUriDisplay.value
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(uri)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = uri
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    copiedUri.value = true
    if (copyResetTimer !== null) clearTimeout(copyResetTimer)
    copyResetTimer = setTimeout(() => {
      copiedUri.value = false
    }, 1800)
  } catch {
    authError.value = 'Copy failed — please copy the Redirect URI manually.'
  }
}

function stopAuthPolling() {
  if (authPollTimer !== null) {
    clearInterval(authPollTimer)
    authPollTimer = null
  }
}

async function connectSpotify() {
  authError.value = ''
  const clientId = current.value.clientId.trim()
  const clientSecret = current.value.clientSecret.trim()

  if (!clientId || !clientSecret) {
    authError.value = 'Enter both Client ID and Client Secret before connecting.'
    return
  }

  connecting.value = true
  try {
    // Persist latest credentials immediately so /auth/url and /callback can use them
    const saveRes = await fetch('/api/plugins/spotify/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        settings: {
          ...current.value,
          redirectUri: redirectUriDisplay.value,
        },
      }),
    })
    if (!saveRes.ok) {
      throw new Error(`Failed to save credentials (${saveRes.status})`)
    }

    const urlRes = await fetchWithPluginReload('/api/plugins/spotify/auth/url', { cache: 'no-store' })
    const urlPayload = (await urlRes.json()) as { url?: string; auth_url?: string; detail?: string }
    if (!urlRes.ok) {
      throw new Error(urlPayload.detail || `Failed to build Spotify auth URL (${urlRes.status})`)
    }

    const authUrl = urlPayload.url || urlPayload.auth_url
    if (!authUrl) {
      throw new Error('Server did not return a Spotify authorization URL.')
    }

    const popup = window.open(authUrl, 'spotify-oauth', 'width=520,height=740')
    if (!popup) {
      window.open(authUrl, '_blank', 'noopener,noreferrer')
    }

    stopAuthPolling()
    let attempts = 0
    authPollTimer = setInterval(async () => {
      attempts += 1
      await refreshStatus()
      if (authenticated.value || attempts >= 45 || (popup && popup.closed)) {
        stopAuthPolling()
      }
    }, 2000)
  } catch (err) {
    authError.value = err instanceof Error ? err.message : 'Unable to start Spotify OAuth.'
  } finally {
    connecting.value = false
  }
}

async function disconnectSpotify() {
  authError.value = ''
  disconnecting.value = true
  stopAuthPolling()
  try {
    const res = await fetchWithPluginReload('/api/plugins/spotify/disconnect', { method: 'POST' })
    if (!res.ok) {
      throw new Error(`Disconnect failed (${res.status})`)
    }
    authenticated.value = false
    statusPlaying.value = false
    statusTitle.value = null
    statusArtist.value = null
  } catch (err) {
    authError.value = err instanceof Error ? err.message : 'Unable to disconnect Spotify.'
  } finally {
    disconnecting.value = false
  }
}

function handleWindowMessage(event: MessageEvent) {
  let hostname = ''
  try {
    hostname = new URL(event.origin).hostname
  } catch {
    hostname = ''
  }
  const isLoopbackOrigin =
    event.origin === window.location.origin ||
    hostname === '127.0.0.1' ||
    hostname === 'localhost'
  if (isLoopbackOrigin && event.data?.type === 'spotify-oauth-success') {
    stopAuthPolling()
    void refreshStatus()
  }
}

function handleWindowFocus() {
  void refreshStatus()
}

onMounted(() => {
  void refreshStatus()
  window.addEventListener('message', handleWindowMessage)
  window.addEventListener('focus', handleWindowFocus)
})

onUnmounted(() => {
  stopAuthPolling()
  if (copyResetTimer !== null) clearTimeout(copyResetTimer)
  window.removeEventListener('message', handleWindowMessage)
  window.removeEventListener('focus', handleWindowFocus)
})

const displayToggles: Array<{ key: keyof SpotifySettings; label: string }> = [
  { key: 'showArtist', label: 'Show Artist' },
  { key: 'showAlbum', label: 'Show Album' },
  { key: 'showProgressBar', label: 'Show Progress Bar' },
  { key: 'showTimeRemaining', label: 'Show Time Remaining' },
  { key: 'showEqualizer', label: 'Show Equalizer' },
]

const swatches = [
  { label: 'Spotify Green', hex: '#1ed760' },
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
    <!-- OAuth Connection Status & Controls -->
    <div class="space-y-3 rounded-lg border border-slate-800 bg-slate-950/70 p-3.5">
      <div class="flex items-center justify-between gap-2">
        <span class="font-mono text-xs uppercase tracking-wider text-slate-400">
          Spotify Account Link
        </span>
        <span
          class="rounded border px-2 py-0.5 font-mono text-[10px] font-semibold uppercase"
          :class="
            authenticated
              ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300'
              : 'border-amber-500/30 bg-amber-500/10 text-amber-300'
          "
        >
          {{ statusLoading && !authenticated ? 'Checking...' : authenticated ? 'Connected' : 'Not Connected' }}
        </span>
      </div>

      <div v-if="authenticated" class="rounded border border-slate-800 bg-slate-900/70 px-2.5 py-2 text-[11px] text-slate-300">
        <span v-if="statusTitle">
          {{ statusPlaying ? 'Playing:' : 'Paused:' }}
          <strong class="text-slate-100">{{ statusTitle }}</strong>
          <span v-if="statusArtist" class="text-slate-400"> — {{ statusArtist }}</span>
        </span>
        <span v-else class="text-slate-400">
          Linked and polling Spotify playback every ~2.5s.
        </span>
      </div>

      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          :disabled="connecting"
          class="flex-1 rounded-lg border border-emerald-500/50 bg-emerald-500/20 px-3 py-2 font-mono text-xs font-semibold text-emerald-200 transition hover:bg-emerald-500/30 disabled:opacity-50"
          @click="connectSpotify"
        >
          {{ connecting ? 'Connecting...' : authenticated ? 'Reconnect Spotify' : 'Connect Spotify' }}
        </button>

        <button
          v-if="authenticated"
          type="button"
          :disabled="disconnecting"
          class="rounded-lg border border-rose-500/40 bg-rose-500/15 px-3 py-2 font-mono text-xs font-semibold text-rose-200 transition hover:bg-rose-500/25 disabled:opacity-50"
          @click="disconnectSpotify"
        >
          {{ disconnecting ? '...' : 'Disconnect' }}
        </button>
      </div>

      <p v-if="authError" class="text-xs text-rose-400">
        {{ authError }}
      </p>
    </div>

    <!-- Spotify API Credentials -->
    <div class="space-y-3">
      <label class="block font-mono text-xs uppercase tracking-wider text-slate-400">
        Spotify Developer App Credentials
      </label>

      <div>
        <label class="mb-1 block text-[11px] text-slate-400">Client ID</label>
        <input
          :value="current.clientId"
          type="text"
          autocomplete="off"
          placeholder="Paste Spotify Client ID..."
          class="w-full rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 font-mono text-xs text-slate-100 placeholder-slate-500 focus:border-cyan-400/70 focus:outline-none"
          @input="updateField('clientId', ($event.target as HTMLInputElement).value)"
        />
      </div>

      <div>
        <label class="mb-1 block text-[11px] text-slate-400">Client Secret</label>
        <div class="flex gap-2">
          <input
            :value="current.clientSecret"
            :type="showSecret ? 'text' : 'password'"
            autocomplete="off"
            placeholder="Paste Spotify Client Secret..."
            class="min-w-0 flex-1 rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 font-mono text-xs text-slate-100 placeholder-slate-500 focus:border-cyan-400/70 focus:outline-none"
            @input="updateField('clientSecret', ($event.target as HTMLInputElement).value)"
          />
          <button
            type="button"
            class="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 font-mono text-[11px] text-slate-300 transition hover:border-cyan-500/50 hover:text-cyan-200"
            @click="showSecret = !showSecret"
          >
            {{ showSecret ? 'Hide' : 'Show' }}
          </button>
        </div>
      </div>

      <div>
        <label class="mb-1 block text-[11px] text-slate-400">Redirect URI (Read-Only)</label>
        <div class="flex gap-2">
          <input
            :value="redirectUriDisplay"
            type="text"
            readonly
            class="min-w-0 flex-1 rounded-lg border border-slate-800 bg-slate-900/80 px-3 py-2 font-mono text-[11px] text-cyan-300 focus:outline-none"
            @focus="($event.target as HTMLInputElement).select()"
          />
          <button
            type="button"
            class="rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 font-mono text-[11px] font-semibold text-cyan-200 transition hover:bg-cyan-500/20"
            @click="copyRedirectUri"
          >
            {{ copiedUri ? 'Copied!' : 'Copy' }}
          </button>
        </div>
        <p class="mt-1.5 text-[11px] text-slate-400">
          Add this exact loopback URI (<code class="text-slate-200">http://127.0.0.1:8080/api/plugins/spotify/callback</code>; Spotify rejects <code class="text-slate-300">localhost</code>) in your
          <strong class="text-slate-200">Spotify Developer Dashboard</strong>
          under App Settings &rarr; Redirect URIs.
        </p>
      </div>
    </div>

    <!-- Display Elements -->
    <div class="space-y-2">
      <label class="block font-mono text-xs uppercase tracking-wider text-slate-400">
        Display Elements
      </label>

      <label
        v-for="item in displayToggles"
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

    <!-- On-Event Trigger Conditions -->
    <div class="space-y-2">
      <label class="block font-mono text-xs uppercase tracking-wider text-amber-300">
        On-Event Trigger Conditions
      </label>
      <p class="text-[11px] text-slate-400">
        Automatically surface Spotify Now Playing in Dynamic Mode and fold back after the hold cooldown.
      </p>

      <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <div>
          <div class="text-xs text-slate-200">While Playing (Hide When Paused)</div>
          <div class="text-[11px] text-slate-400">Keep active continuously while music plays; hide when paused</div>
        </div>
        <input
          :checked="current.triggerWhilePlaying"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField('triggerWhilePlaying', ($event.target as HTMLInputElement).checked)"
        />
      </label>

      <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <div>
          <div class="text-xs text-slate-200">Trigger on Track Change</div>
          <div class="text-[11px] text-slate-400">Surface briefly when the active track changes</div>
        </div>
        <input
          :checked="current.triggerOnTrackChange"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField('triggerOnTrackChange', ($event.target as HTMLInputElement).checked)"
        />
      </label>

      <label class="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5">
        <div>
          <div class="text-xs text-slate-200">Trigger on Playback Start</div>
          <div class="text-[11px] text-slate-400">Surface briefly when playback starts or resumes</div>
        </div>
        <input
          :checked="current.triggerOnPlayStart"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400"
          @change="updateField('triggerOnPlayStart', ($event.target as HTMLInputElement).checked)"
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
