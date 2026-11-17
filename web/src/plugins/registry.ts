import type { Component } from 'vue'
import type { HudPluginDefinition } from './types'

interface RawPluginManifest {
  id?: string
  name?: string
  description?: string
  basePriority?: number
  defaultSettings?: Record<string, unknown>
}

const manifestModules = import.meta.glob<RawPluginManifest>(
  '../../../plugins/*/plugin.json',
  { eager: true, import: 'default' },
)

const widgetModules = import.meta.glob<Component>(
  '../../../plugins/*/Widget.vue',
  { eager: true, import: 'default' },
)

const settingsModules = import.meta.glob<Component>(
  '../../../plugins/*/Settings.vue',
  { eager: true, import: 'default' },
)

function extractFolderName(globPath: string): string {
  const parts = globPath.split('/')
  return parts[parts.length - 2] ?? ''
}

const widgetsByFolder = new Map<string, Component>(
  Object.entries(widgetModules).map(([path, comp]) => [extractFolderName(path), comp]),
)

const settingsByFolder = new Map<string, Component>(
  Object.entries(settingsModules).map(([path, comp]) => [extractFolderName(path), comp]),
)

const discovered: HudPluginDefinition<any>[] = []

for (const [path, manifest] of Object.entries(manifestModules)) {
  const folder = extractFolderName(path)
  const Widget = widgetsByFolder.get(folder)
  if (!folder || !Widget) continue

  const id = manifest.id || folder
  discovered.push({
    id,
    name: manifest.name || id,
    description: manifest.description || '',
    defaultSettings: manifest.defaultSettings ? { ...manifest.defaultSettings } : {},
    Widget,
    Settings: settingsByFolder.get(folder),
  })
}

discovered.sort((a, b) => {
  if (a.id === 'clock') return -1
  if (b.id === 'clock') return 1
  return a.id.localeCompare(b.id)
})

export const PLUGIN_LIST: HudPluginDefinition<any>[] = discovered

export const PLUGIN_REGISTRY: Record<string, HudPluginDefinition<any>> = Object.fromEntries(
  PLUGIN_LIST.map((plugin) => [plugin.id, plugin]),
)

export function getPluginById(
  id: string | null | undefined,
): HudPluginDefinition<any> | undefined {
  if (!id) return undefined
  return PLUGIN_REGISTRY[id]
}

export function getDefaultPluginSettings(id: string): Record<string, unknown> {
  return { ...(PLUGIN_REGISTRY[id]?.defaultSettings ?? {}) }
}
