import manifest from './plugin.json'

export type ClockStylePreset = 'minimal' | 'tactical' | 'segmented'

export interface ClockSettings {
  format24h: boolean
  showSeconds: boolean
  showDate: boolean
  showArcRing: boolean
  accentColor: string
  stylePreset: ClockStylePreset
}

export interface ClockPluginData {
  iso?: string
  time_24h?: string
  time_12h?: string
  ampm?: string
  hours?: number
  hours_24?: number
  hours_12?: number
  minutes?: number
  seconds?: number
  date_display?: string
  weekday?: string
  day_progress_pct?: number
  minute_progress_pct?: number
}

export const DEFAULT_CLOCK_SETTINGS: ClockSettings =
  manifest.defaultSettings as ClockSettings
