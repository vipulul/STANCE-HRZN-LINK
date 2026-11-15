export type FlapState = 'open' | 'closed' | 'custom'
export type FrameFormat = 'RGB565' | 'JPEG'

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

export interface StateSnapshot {
  type?: string
  config: HrznConfig
  device: DeviceStatus
  preview_data_url?: string
}
