import type { Component } from 'vue'
import type { GridLayoutId } from '../types/hrzn'

export interface HudPluginProps<
  TSettings = Record<string, any>,
  TData = Record<string, any>,
> {
  settings: TSettings
  data?: TData
  slotIndex?: number
  layout?: GridLayoutId
}

export interface HudPluginDefinition<TSettings = any> {
  id: string
  name: string
  description: string
  defaultSettings: TSettings
  Widget: Component
  Settings?: Component
}
