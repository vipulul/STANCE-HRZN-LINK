import { markRaw, type Component } from 'vue'
import * as Vue from 'vue'
import { compileScript, compileStyle, compileTemplate, parse } from '@vue/compiler-sfc'
import { transform } from 'sucrase'

const PROBE_EXTENSIONS = ['', '.ts', '.js', '.mjs', '.json', '.vue', '/index.ts', '/index.js']

function normalizeSlashes(input: string): string {
  return input.replace(/\\/g, '/')
}

function resolveVirtualPath(fromVirtualFile: string, specifier: string): string {
  const baseParts = normalizeSlashes(fromVirtualFile).split('/')
  baseParts.pop()
  for (const part of specifier.split('/')) {
    if (!part || part === '.') continue
    if (part === '..') {
      baseParts.pop()
    } else {
      baseParts.push(part)
    }
  }
  return `/${baseParts.filter(Boolean).join('/')}`
}

async function fetchPluginAsset(
  pluginId: string,
  targetVirtualPath: string,
  fileCache: Map<string, string>,
): Promise<{ resolvedPath: string; source: string }> {
  const prefix = `/plugins/${pluginId}/`
  const normalizedTarget = normalizeSlashes(targetVirtualPath)
  if (!normalizedTarget.startsWith(prefix)) {
    throw new Error(`Invalid relative plugin import path: ${targetVirtualPath}`)
  }

  const relBase = normalizedTarget.slice(prefix.length)
  const hasExtension = /\.[a-zA-Z0-9]+$/.test(relBase)
  const candidates = hasExtension ? [relBase] : PROBE_EXTENSIONS.map((ext) => `${relBase}${ext}`)

  for (const candidateRel of candidates) {
    const virtualPath = `${prefix}${candidateRel}`
    const cached = fileCache.get(virtualPath)
    if (cached !== undefined) {
      return { resolvedPath: virtualPath, source: cached }
    }

    const url = `/plugins-raw/${encodeURIComponent(pluginId)}/${candidateRel}`
    const res = await fetch(url, { cache: 'no-store' })
    if (res.ok) {
      const source = await res.text()
      fileCache.set(virtualPath, source)
      return { resolvedPath: virtualPath, source }
    }
  }

  throw new Error(`Unable to fetch plugin asset "${targetVirtualPath}" for plugin "${pluginId}"`)
}

function extractRelativeSpecifiers(source: string): string[] {
  const results = new Set<string>()
  const importRe = /(?:import|export)\s+(?:type\s+)?(?:[\s\S]*?\s+from\s+)?['"](\.[^'"]+)['"]/g
  let match: RegExpExecArray | null
  while ((match = importRe.exec(source)) !== null) {
    if (match[1]) {
      results.add(match[1])
    }
  }
  return [...results]
}

async function prefetchDependencies(
  pluginId: string,
  virtualPath: string,
  source: string,
  fileCache: Map<string, string>,
  visited: Set<string>,
): Promise<void> {
  if (visited.has(virtualPath)) return
  visited.add(virtualPath)

  let scanSource = source
  if (virtualPath.endsWith('.vue')) {
    const { descriptor } = parse(source, { filename: virtualPath })
    scanSource = [descriptor.script?.content ?? '', descriptor.scriptSetup?.content ?? ''].join('\n')
  }

  const specifiers = extractRelativeSpecifiers(scanSource)
  for (const spec of specifiers) {
    const target = resolveVirtualPath(virtualPath, spec)
    const { resolvedPath, source: depSource } = await fetchPluginAsset(pluginId, target, fileCache)
    if (!resolvedPath.endsWith('.json')) {
      await prefetchDependencies(pluginId, resolvedPath, depSource, fileCache, visited)
    }
  }
}

function injectPluginStyles(styleKey: string, cssBlocks: string[]): void {
  const existing = document.querySelectorAll(`style[data-hrzn-plugin-style^="${styleKey}:"]`)
  existing.forEach((node) => node.remove())

  cssBlocks.forEach((css, index) => {
    if (!css.trim()) return
    const styleEl = document.createElement('style')
    styleEl.setAttribute('data-hrzn-plugin-style', `${styleKey}:${index}`)
    styleEl.textContent = css
    document.head.appendChild(styleEl)
  })
}

function findCachedModulePath(fromVirtualFile: string, specifier: string, fileCache: Map<string, string>): string {
  const baseTarget = resolveVirtualPath(fromVirtualFile, specifier)
  if (fileCache.has(baseTarget)) return baseTarget
  for (const ext of PROBE_EXTENSIONS) {
    const candidate = `${baseTarget}${ext}`
    if (fileCache.has(candidate)) return candidate
  }
  throw new Error(`Module not preloaded in cache: ${specifier} (from ${fromVirtualFile})`)
}

function compileSfcEntry(
  pluginId: string,
  virtualPath: string,
  fileCache: Map<string, string>,
  moduleCache: Map<string, unknown>,
): Component {
  const existing = moduleCache.get(virtualPath)
  if (existing) return existing as Component

  const source = fileCache.get(virtualPath)
  if (source === undefined) {
    throw new Error(`Missing SFC source for ${virtualPath}`)
  }

  const { descriptor, errors } = parse(source, { filename: virtualPath })
  if (errors.length > 0) {
    throw new Error(`SFC parse error in ${virtualPath}: ${errors[0].message}`)
  }

  const cleanSlug = `${pluginId}-${virtualPath.split('/').pop() ?? 'comp'}`
    .replace(/[^a-zA-Z0-9_-]/g, '')
    .toLowerCase()
  const scopeId = `hrzn-${cleanSlug}`
  const scopedAttr = `data-v-${scopeId}`
  const hasScoped = descriptor.styles.some((s) => Boolean(s.scoped))

  let scriptCode = ''
  if (descriptor.script || descriptor.scriptSetup) {
    const compiled = compileScript(descriptor, {
      id: scopeId,
      inlineTemplate: Boolean(descriptor.template),
      templateOptions: {
        id: scopeId,
        scoped: hasScoped,
        compilerOptions: {
          scopeId: hasScoped ? scopedAttr : undefined,
        },
      },
      fs: {
        fileExists: (file: string) => fileCache.has(normalizeSlashes(file)),
        readFile: (file: string) => fileCache.get(normalizeSlashes(file)),
      },
    })
    scriptCode = compiled.content
  } else if (descriptor.template) {
    const tpl = compileTemplate({
      source: descriptor.template.content,
      filename: virtualPath,
      id: scopeId,
      scoped: hasScoped,
      compilerOptions: {
        scopeId: hasScoped ? scopedAttr : undefined,
      },
    })
    scriptCode = `${tpl.code}\nexport default { render }`
  } else {
    scriptCode = 'export default {}'
  }

  const compiledCssBlocks: string[] = []
  for (const styleBlock of descriptor.styles) {
    const styled = compileStyle({
      source: styleBlock.content,
      filename: virtualPath,
      id: scopedAttr,
      scoped: Boolean(styleBlock.scoped),
    })
    if (styled.errors.length > 0) {
      throw new Error(`Style compile error in ${virtualPath}: ${String(styled.errors[0])}`)
    }
    compiledCssBlocks.push(styled.code)
  }
  injectPluginStyles(scopeId, compiledCssBlocks)

  const evalCommonJs = (currentPath: string, code: string): unknown => {
    const cjs = transform(code, { transforms: ['typescript', 'imports'] }).code
    const mod: { exports: Record<string, any> } = { exports: {} }
    const localRequire = (spec: string): unknown => {
      if (spec === 'vue') return Vue
      if (!spec.startsWith('.')) {
        throw new Error(`Unsupported bare import "${spec}" inside runtime plugin ${pluginId}`)
      }
      const depPath = findCachedModulePath(currentPath, spec, fileCache)
      if (moduleCache.has(depPath)) {
        return moduleCache.get(depPath)
      }
      if (depPath.endsWith('.json')) {
        const parsed = JSON.parse(fileCache.get(depPath) ?? '{}')
        moduleCache.set(depPath, parsed)
        return parsed
      }
      if (depPath.endsWith('.vue')) {
        return compileSfcEntry(pluginId, depPath, fileCache, moduleCache)
      }
      const depSource = fileCache.get(depPath) ?? ''
      const depExports = evalCommonJs(depPath, depSource)
      moduleCache.set(depPath, depExports)
      return depExports
    }

    const fn = new Function('exports', 'module', 'require', cjs)
    fn(mod.exports, mod, localRequire)
    return mod.exports
  }

  const exportsObj = evalCommonJs(virtualPath, scriptCode) as Record<string, any>
  const component = (exportsObj.default ?? exportsObj) as Record<string, any>
  if (hasScoped) {
    component.__scopeId = scopedAttr
  }
  const rawComp = markRaw(component) as Component
  moduleCache.set(virtualPath, rawComp)
  return rawComp
}

export async function loadRuntimePluginSfc(
  pluginId: string,
  entryFile: string,
): Promise<Component> {
  const entryVirtualPath = `/plugins/${pluginId}/${entryFile}`
  const fileCache = new Map<string, string>()
  const moduleCache = new Map<string, unknown>()
  const { resolvedPath, source } = await fetchPluginAsset(pluginId, entryVirtualPath, fileCache)
  await prefetchDependencies(pluginId, resolvedPath, source, fileCache, new Set<string>())
  return compileSfcEntry(pluginId, resolvedPath, fileCache, moduleCache)
}
