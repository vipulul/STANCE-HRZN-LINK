import manifest from './plugin.json'

export type BambuGcodeState = 'IDLE' | 'PREPARE' | 'RUNNING' | 'PAUSE' | 'FINISH' | 'FAILED'
export type BambuConnectionState = 'CONNECTED' | 'CONNECTING' | 'DISCONNECTED' | 'MOCK_ACTIVE'

export interface BambuSettings {
  dynamicMode?: 'always' | 'on_event' | 'off'
  userPriority?: number
  accentColor: string
  printerIp: string
  serialNumber: string
  accessCode: string
  printerName: string
  mockMode: boolean
  mockState: BambuGcodeState
  showTemperatures: boolean
  showChamberTemp: boolean
  showSecondNozzle: boolean
  showLayerCount: boolean
  showRemainingTime: boolean
  showPrintStage: boolean
  showCornerBrackets: boolean
  triggerOnPrintStart: boolean
  triggerWhilePrinting: boolean
  triggerOnPrintFinish: boolean
  triggerOnErrorOrPause: boolean
}

export interface BambuPluginData {
  connection_state?: BambuConnectionState
  connected?: boolean
  configured?: boolean
  mock_mode?: boolean
  printer_name?: string
  gcode_state?: BambuGcodeState
  mc_percent?: number
  mc_remaining_time?: number
  eta_display?: string
  layer_num?: number
  total_layer_num?: number
  nozzle_temper?: number
  nozzle_target_temper?: number
  nozzle2_temper?: number | null
  nozzle2_target_temper?: number | null
  has_second_nozzle?: boolean
  bed_temper?: number
  bed_target_temper?: number
  chamber_temper?: number | null
  chamber_target_temper?: number | null
  has_chamber?: boolean
  subtask_name?: string
  stg_cur?: number
  stage_label?: string
  print_error?: number
  has_error?: boolean
  last_update_at?: string | null
  error?: string | null
}

export const DEFAULT_BAMBU_SETTINGS: BambuSettings =
  manifest.defaultSettings as BambuSettings
