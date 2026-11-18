import manifest from './plugin.json'

export type FlapDisplayState = 'OPEN' | 'CLOSED' | 'MOVING'
export type DeviceConnectionState = 'ONLINE' | 'OFFLINE'

export interface TelemetrySettings {
  accentColor: string
  showFps: boolean
  showFlapState: boolean
  showServoPulse: boolean
  showDeviceStatus: boolean
  showLatency: boolean
  showLayout: boolean
  compactLabels: boolean
  autoSurfaceOnEvent: boolean
  activeWhenFlapOpen: boolean
  triggerOnFlapMove: boolean
  triggerOnFlapOpen: boolean
  triggerOnDeviceDisconnect: boolean
  triggerOnWeakWifi: boolean
  rssiThresholdDbm: number
  triggerOnHighLatency: boolean
  latencyThresholdMs: number
  triggerOnLowFps: boolean
  minFpsThreshold: number
}

export interface TelemetryPluginData {
  stream_fps?: number
  flap_state?: FlapDisplayState
  servo_pulse_us?: number
  device_connected?: boolean
  device_status?: DeviceConnectionState
  wifi_rssi?: number | null
  frame_latency_ms?: number
  active_layout?: string
  renderer_mode?: string
  target_angle_pct?: number
  flap_position_pct?: number
  servo_attached?: boolean
}

export const DEFAULT_TELEMETRY_SETTINGS: TelemetrySettings =
  manifest.defaultSettings as TelemetrySettings
