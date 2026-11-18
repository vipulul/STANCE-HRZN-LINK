export type FlapState = 'open' | 'closed' | 'custom'
export type FrameFormat = 'RGB565' | 'JPEG'
export type GridLayoutId =
  | '1x1'
  | '2x1'
  | '1x2'
  | '2x2'
  | '2-big-1-small'
  | '3x1'
  | '4x1'
export type LayoutMode = 'manual' | 'dynamic'
export type PluginDynamicMode = 'always' | 'on_event' | 'off'
export type ClockStylePreset = 'minimal' | 'tactical' | 'segmented'

export interface DynamicRulesConfig {
  night_mode_enabled: boolean
  night_start_hour: number
  night_end_hour: number
  night_style_preset: ClockStylePreset
  event_hold_seconds: number
}

export interface HrznConfig {
  servo_closed_us: number
  servo_open_us: number
  sweep_duration_ms: number
  settle_detach_ms: number
  brightness: number
  flap_state: FlapState
  target_angle_pct: number
  mirror_vertical: boolean
  frame_format: FrameFormat
  target_fps: number
  hud_title: string
  hud_subtitle: string
  display_width: number
  display_height: number
  layout_mode: LayoutMode
  manual_layout: GridLayoutId
  grid_slots: Array<string | null>
  plugin_configs: Record<string, Record<string, unknown>>
  dynamic_rules: DynamicRulesConfig
}

export interface DeviceStatus {
  connected: boolean
  device_id: string | null
  hw_version: string
  fw_version: string | null
  display_width: number
  display_height: number
  uptime_s: number
  rssi_dbm: number | null
  free_heap: number | null
  flap_position_pct: number
  servo_us: number
  servo_attached: boolean
  brightness: number
  fps: number
  last_seen: string | null
}

export interface PluginRuntimeStatus {
  id: string
  name: string
  active: boolean
  priority: number
  dynamic_mode?: PluginDynamicMode
  user_priority?: number
  event_triggered?: boolean
  holding_event?: boolean
  hold_remaining_s?: number
  reason: string
  data: Record<string, unknown>
  settings_override: Record<string, unknown>
}

export interface PluginManifest {
  id: string
  name: string
  description: string
  version?: string
  base_priority: number
  basePriority?: number
  defaultDynamicMode?: PluginDynamicMode
  supportsOnEvent?: boolean
  supports_on_event?: boolean
  default_settings: Record<string, unknown>
  defaultSettings?: Record<string, unknown>
  hasWidget?: boolean
  hasSettings?: boolean
}

export interface LayoutEvaluationResult {
  mode: LayoutMode
  active_layout: GridLayoutId
  slot_count: number
  slots: Array<string | null>
  reason: string
  night_schedule_active: boolean
  effective_plugin_settings: Record<string, Record<string, unknown>>
  plugin_data: Record<string, Record<string, unknown>>
  plugin_statuses: PluginRuntimeStatus[]
}

export interface WsLogEntry {
  ts: string
  source: string
  event: string
  detail: string
  level: string
}

export interface StateSnapshot {
  type?: string
  config: HrznConfig
  device: DeviceStatus
  layout?: LayoutEvaluationResult
  plugins?: PluginManifest[]
  plugin_reload_token?: number
  renderer_mode?: 'playwright' | 'pillow-fallback'
  logs?: WsLogEntry[]
  preview_data_url?: string
}
