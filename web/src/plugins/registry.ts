import { defineComponent, h, markRaw, reactive, ref, type Component } from 'vue'
import type { PluginManifest } from '../types/hrzn'
import { loadRuntimePluginSfc } from './sfcLoader'
import type { HudPluginDefinition } from './types'

interface CachedPluginEntry {
  token: number
  definition: HudPluginDefinition<any>
}

export const PLUGIN_LIST = ref<HudPluginDefinition<any>[]>([])
export const PLUGIN_REGISTRY = reactive<Record<string, HudPluginDefinition<any>>>({})

const compiledCache = new Map<string, CachedPluginEntry>()
let syncChain: Promise<void> = Promise.resolve()

function makeErrorWidget(pluginId: string, message: string): Component {
  return markRaw(
    defineComponent({
      name: `PluginError_${pluginId}`,
      setup() {
        return () =>
          h(
            'div',
            {
              class:
                'flex h-full w-full flex-col items-center justify-center bg-black p-2 text-center font-mono text-[10px] text-rose-400',
            },
            [
              h('div', { class: 'font-bold uppercase' }, `Plugin "${pluginId}" Error`),
              h('div', { class: 'mt-1 text-slate-500 break-all' }, message),
            ],
          )
      },
    }),
  )
}

export async function syncRuntimePlugins(
  manifests: PluginManifest[],
  reloadToken = 1,
  forceReload = false,
): Promise<void> {
  if (
    !forceReload &&
    manifests.length === PLUGIN_LIST.value.length &&
    manifests.every((m, idx) => {
      const cached = compiledCache.get(m.id)
      return cached && cached.token === reloadToken && PLUGIN_LIST.value[idx]?.id === m.id
    })
  ) {
    return
  }

  const run = async () => {
    if (forceReload) {
      compiledCache.clear()
    }

    const nextList: HudPluginDefinition<any>[] = []

    for (const manifest of manifests) {
      const id = manifest.id
      const defaults = {
        ...(manifest.defaultSettings ?? manifest.default_settings ?? {}),
      }

      const cached = compiledCache.get(id)
      if (!forceReload && cached && cached.token === reloadToken) {
        const updatedDef: HudPluginDefinition<any> = {
          ...cached.definition,
          name: manifest.name || id,
          description: manifest.description || '',
          defaultSettings: defaults,
        }
        cached.definition = updatedDef
        nextList.push(updatedDef)
        continue
      }

      let WidgetComp: Component
      if (manifest.hasWidget === false) {
        WidgetComp = makeErrorWidget(id, 'Missing Widget.vue')
      } else {
        try {
          WidgetComp = await loadRuntimePluginSfc(id, 'Widget.vue')
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err)
          console.error(`[PLUGINS] Failed to compile ${id}/Widget.vue:`, err)
          WidgetComp = makeErrorWidget(id, msg)
        }
      }

      let SettingsComp: Component | undefined
      if (manifest.hasSettings) {
        try {
          SettingsComp = await loadRuntimePluginSfc(id, 'Settings.vue')
        } catch (err) {
          console.error(`[PLUGINS] Failed to compile ${id}/Settings.vue:`, err)
        }
      }

      const definition: HudPluginDefinition<any> = {
        id,
        name: manifest.name || id,
        description: manifest.description || '',
        defaultSettings: defaults,
        Widget: WidgetComp,
        Settings: SettingsComp,
      }
      compiledCache.set(id, { token: reloadToken, definition })
      nextList.push(definition)
    }

    PLUGIN_LIST.value = nextList
    const activeIds = new Set(nextList.map((p) => p.id))
    for (const existingKey of Object.keys(PLUGIN_REGISTRY)) {
      if (!activeIds.has(existingKey)) {
        delete PLUGIN_REGISTRY[existingKey]
      }
    }
    for (const def of nextList) {
      PLUGIN_REGISTRY[def.id] = def
    }
  }

  syncChain = syncChain.then(run, run)
  return syncChain
}

export function getPluginById(
  id: string | null | undefined,
): HudPluginDefinition<any> | undefined {
  if (!id) return undefined
  return PLUGIN_REGISTRY[id]
}

export function getDefaultPluginSettings(id: string): Record<string, unknown> {
  return { ...(PLUGIN_REGISTRY[id]?.defaultSettings ?? {}) }
}
