import { computed, reactive, ref } from 'vue'
import { getDefaultPluginSettings } from '../plugins/registry'
import type {
  DeviceStatus,
  FlapState,
  GridLayoutId,
  HrznConfig,
  LayoutEvaluationResult,
  LayoutMode,
  PluginManifest,
  StateSnapshot,
  WsLogEntry,
} from '../types/hrzn'

declare global {
  interface Window {
    __HRZN_APPLY_STATE__?: (snapshot: StateSnapshot) => void
  }
}

const uiConnected = ref(false)
const saving = ref(false)
const statusMessage = ref<string | null>(null)
const hasUnsavedConfig = ref(false)
const previewDataUrl = ref<string>('/api/preview.png')
const rendererMode = ref<'playwright' | 'pillow-fallback'>('pillow-fallback')
const plugins = ref<PluginManifest[]>([])
const serverLogs = ref<WsLogEntry[]>([])
const clientLogs = ref<WsLogEntry[]>([])

const config = reactive<HrznConfig>({
  servo_closed_us: 1000,
  servo_open_us: 2000,
  sweep_duration_ms: 800,
  settle_detach_ms: 250,
  brightness: 200,
  flap_state: 'open',
  target_angle_pct: 100,
  mirror_vertical: true,
  frame_format: 'RGB565',
  target_fps: 2.5,
  hud_title: 'STANCE // HRZN-01',
  hud_subtitle: 'OPTICAL HUD LINK',
  display_width: 480,
  display_height: 320,
  layout_mode: 'manual',
  manual_layout: '1x1',
  grid_slots: ['clock', null, null, null],
  plugin_configs: {
    clock: getDefaultPluginSettings('clock'),
  },
  dynamic_rules: {
    night_mode_enabled: true,
    night_start_hour: 22,
    night_end_hour: 7,
    night_style_preset: 'minimal',
  },
})

const device = reactive<DeviceStatus>({
  connected: false,
  device_id: null,
  hw_version: 'HRZN-01',
  fw_version: null,
  display_width: 480,
  display_height: 320,
  uptime_s: 0,
  rssi_dbm: null,
  free_heap: null,
  flap_position_pct: 0,
  servo_us: 1000,
  servo_attached: false,
  brightness: 200,
  fps: 0,
  last_seen: null,
})

const layout = reactive<LayoutEvaluationResult>({
  mode: 'manual',
  active_layout: '1x1',
  slot_count: 1,
  slots: ['clock'],
  reason: 'Manual Grid (1x1)',
  night_schedule_active: false,
  effective_plugin_settings: {
    clock: getDefaultPluginSettings('clock'),
  },
  plugin_data: {},
  plugin_statuses: [],
})

let socket: WebSocket | null = null
let reconnectTimer: number | null = null
let statusTimer: number | null = null
let started = false

function pushClientLog(event: string, detail: string, level = 'info') {
  clientLogs.value = [
    ...clientLogs.value.slice(-49),
    {
      ts: new Date().toISOString(),
      source: 'browser_ws',
      event,
      detail,
      level,
    },
  ]
}

function flashStatus(msg: string) {
  statusMessage.value = msg
  if (statusTimer !== null) {
    window.clearTimeout(statusTimer)
  }
  statusTimer = window.setTimeout(() => {
    statusMessage.value = null
  }, 2500)
}

function applySnapshot(snapshot: StateSnapshot, forceConfigSync = false) {
  if (snapshot.config) {
    if (forceConfigSync || !hasUnsavedConfig.value) {
      Object.assign(config, snapshot.config)
    } else {
      config.flap_state = snapshot.config.flap_state
      config.target_angle_pct = snapshot.config.target_angle_pct
      config.brightness = snapshot.config.brightness
      config.layout_mode = snapshot.config.layout_mode
      config.manual_layout = snapshot.config.manual_layout
      config.grid_slots = snapshot.config.grid_slots
      config.plugin_configs = snapshot.config.plugin_configs
      config.dynamic_rules = snapshot.config.dynamic_rules
    }
  }
  if (snapshot.device) {
    Object.assign(device, snapshot.device)
  }
  if (snapshot.layout) {
    Object.assign(layout, snapshot.layout)
  }
  if (snapshot.plugins) {
    plugins.value = snapshot.plugins
  }
  if (snapshot.renderer_mode) {
    rendererMode.value = snapshot.renderer_mode
  }
  if (snapshot.logs) {
    serverLogs.value = snapshot.logs
  }
  if (snapshot.preview_data_url) {
    previewDataUrl.value = snapshot.preview_data_url
  }
}

window.__HRZN_APPLY_STATE__ = (snapshot: StateSnapshot) => {
  applySnapshot(snapshot, true)
}

async function fetchInitialState() {
  try {
    const res = await fetch('/api/state')
    if (res.ok) {
      const data = (await res.json()) as StateSnapshot
      applySnapshot(data, true)
    }
  } catch {
    // WebSocket reconnect handles recovery
  }
}

function connectUiSocket() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return
  }
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${window.location.host}/ws/ui`
  socket = new WebSocket(url)

  socket.onopen = () => {
    uiConnected.value = true
    pushClientLog('open', `Connected to ${url}`)
  }

  socket.onmessage = (event: MessageEvent<string>) => {
    try {
      const data = JSON.parse(event.data) as StateSnapshot
      applySnapshot(data)
    } catch {
      // Ignore malformed frames
    }
  }

  socket.onclose = () => {
    uiConnected.value = false
    socket = null
    pushClientLog('close', 'Disconnected from /ws/ui; retrying in 2.5s', 'warn')
    if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
    reconnectTimer = window.setTimeout(connectUiSocket, 2500)
  }

  socket.onerror = () => {
    pushClientLog('error', 'WebSocket transport error', 'error')
    socket?.close()
  }
}

function startConnection() {
  if (started) return
  started = true
  fetchInitialState()
  connectUiSocket()
}

async function updateConfigPatch(
  patch: Partial<HrznConfig>,
  successMessage?: string,
): Promise<boolean> {
  saving.value = true
  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    })
    if (res.ok) {
      const data = (await res.json()) as StateSnapshot
      applySnapshot(data, true)
      if (successMessage) {
        flashStatus(successMessage)
      }
      return true
    }
    flashStatus('Failed to update configuration')
    return false
  } catch {
    flashStatus('Network error while saving configuration')
    return false
  } finally {
    saving.value = false
  }
}

async function saveHardwareConfig() {
  const ok = await updateConfigPatch(
    {
      servo_closed_us: config.servo_closed_us,
      servo_open_us: config.servo_open_us,
      sweep_duration_ms: config.sweep_duration_ms,
      settle_detach_ms: config.settle_detach_ms,
      brightness: config.brightness,
      mirror_vertical: config.mirror_vertical,
      frame_format: config.frame_format,
      target_fps: config.target_fps,
      hud_title: config.hud_title,
      hud_subtitle: config.hud_subtitle,
      display_width: config.display_width,
      display_height: config.display_height,
    },
    'Hardware & stream settings saved',
  )
  if (ok) {
    hasUnsavedConfig.value = false
  }
}

async function updatePluginSettings(
  pluginId: string,
  settings: Record<string, unknown>,
  successMessage?: string,
) {
  saving.value = true
  try {
    const res = await fetch(`/api/plugins/${encodeURIComponent(pluginId)}/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ settings }),
    })
    if (res.ok) {
      const data = (await res.json()) as StateSnapshot
      applySnapshot(data, true)
      flashStatus(successMessage ?? `${pluginId} settings updated`)
      return true
    }
  } catch {
    flashStatus(`Failed to save ${pluginId} settings`)
  } finally {
    saving.value = false
  }
  return false
}

async function sendFlapMove(state: FlapState, positionPct?: number) {
  const targetPct =
    state === 'open' ? 100 : state === 'closed' ? 0 : (positionPct ?? config.target_angle_pct)

  config.flap_state = state
  config.target_angle_pct = targetPct

  try {
    const res = await fetch('/api/flap', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        state,
        position_pct: targetPct,
        duration_ms: config.sweep_duration_ms,
      }),
    })
    if (res.ok) {
      const data = (await res.json()) as StateSnapshot
      applySnapshot(data)
      flashStatus(`Flap -> ${state.toUpperCase()} (${targetPct}%)`)
    }
  } catch {
    flashStatus('Failed to send flap command')
  }
}

async function sendBrightness(brightness: number) {
  config.brightness = brightness
  try {
    const res = await fetch('/api/brightness', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ brightness }),
    })
    if (res.ok) {
      const data = (await res.json()) as StateSnapshot
      applySnapshot(data)
      flashStatus(`Brightness set to ${brightness}/255`)
    }
  } catch {
    flashStatus('Failed to update brightness')
  }
}

async function setLayoutMode(mode: LayoutMode) {
  await updateConfigPatch(
    { layout_mode: mode },
    mode === 'dynamic' ? 'Switched to Dynamic Mode' : 'Switched to Manual Grid',
  )
}

async function setManualLayout(layoutId: GridLayoutId) {
  await updateConfigPatch(
    { layout_mode: 'manual', manual_layout: layoutId },
    `Grid layout set to ${layoutId}`,
  )
}

async function assignSlot(slotIndex: number, pluginId: string | null) {
  const nextSlots = [...config.grid_slots]
  while (nextSlots.length < 4) nextSlots.push(null)
  nextSlots[slotIndex] = pluginId
  await updateConfigPatch(
    { grid_slots: nextSlots },
    pluginId ? `Slot ${slotIndex + 1} -> ${pluginId}` : `Slot ${slotIndex + 1} cleared`,
  )
}

async function swapSlots(fromIndex: number, toIndex: number) {
  const nextSlots = [...config.grid_slots]
  while (nextSlots.length < 4) nextSlots.push(null)
  const tmp = nextSlots[fromIndex] ?? null
  nextSlots[fromIndex] = nextSlots[toIndex] ?? null
  nextSlots[toIndex] = tmp
  await updateConfigPatch(
    { grid_slots: nextSlots },
    `Swapped Slot ${fromIndex + 1} and Slot ${toIndex + 1}`,
  )
}

const combinedLogs = computed(() => {
  const merged = [...serverLogs.value, ...clientLogs.value]
  merged.sort((a, b) => a.ts.localeCompare(b.ts))
  return merged.slice(-120)
})

function clearClientLogs() {
  clientLogs.value = []
}

export function useHrznState() {
  return {
    uiConnected,
    saving,
    statusMessage,
    hasUnsavedConfig,
    previewDataUrl,
    rendererMode,
    plugins,
    serverLogs,
    clientLogs,
    combinedLogs,
    config,
    device,
    layout,
    startConnection,
    flashStatus,
    updateConfigPatch,
    saveHardwareConfig,
    updatePluginSettings,
    sendFlapMove,
    sendBrightness,
    setLayoutMode,
    setManualLayout,
    assignSlot,
    swapSlots,
    clearClientLogs,
  }
}
