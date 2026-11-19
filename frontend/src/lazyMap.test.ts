import { expect, test } from 'vitest'

// Every source file as text, keyed by path relative to this folder.
const sources = import.meta.glob(['./**/*.ts', './**/*.tsx', '!./**/*.test.*'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

/** Files reachable from `entry` through static, non-type imports. */
function staticGraph(entry: string): Set<string> {
  const seen = new Set<string>()
  const visit = (file: string) => {
    if (seen.has(file)) return
    seen.add(file)
    const code = sources[file] ?? ''
    for (const [, spec] of code.matchAll(/^import\s+(?!type\b)[^'"]*?from\s+'([^']+)'/gm)) {
      if (!spec.startsWith('.')) {
        seen.add(spec)
        continue
      }
      const base = new URL(spec, `file:///src/${file.slice(2)}`).pathname.replace('/src/', './')
      const hit = [`${base}.ts`, `${base}.tsx`, `${base}/index.ts`].find((p) => p in sources)
      if (hit) visit(hit)
    }
  }
  visit(entry)
  return seen
}

test('MapLibre and MapView are not in the first bundle (the form loads first)', () => {
  const graph = staticGraph('./main.tsx')
  expect(graph.has('./App.tsx')).toBe(true)
  expect(graph.has('./components/MapPanel.tsx')).toBe(true)
  expect(graph.has('./components/MapView.tsx')).toBe(false)
  expect([...graph].some((f) => f.startsWith('maplibre-gl'))).toBe(false)
  expect(sources['./components/MapPanel.tsx']).toMatch(/lazy\(\(\) => import\('\.\/MapView'\)/)
})

test('App is layout only', () => {
  expect(sources['./App.tsx'].split('\n').length).toBeLessThan(150)
})
