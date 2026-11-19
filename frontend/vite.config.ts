import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

const VERCEL_JSON = fileURLToPath(new URL('./vercel.json', import.meta.url))

/** Headers vercel.json sets on every page (also served by `vite preview`). */
function vercelHeaders(): Record<string, string> {
  const config = JSON.parse(readFileSync(VERCEL_JSON, 'utf8')) as {
    headers?: { source: string; headers: { key: string; value: string }[] }[]
  }
  const all = config.headers?.find((h) => h.source === '/(.*)')?.headers ?? []
  return Object.fromEntries(all.map((h) => [h.key, h.value]))
}

/** Production builds must know the API, and the CSP must allow it. */
function checkProductionApi(apiUrl: string | undefined) {
  const url = apiUrl?.trim()
  if (!url) {
    throw new Error(
      'VITE_API_URL is not set. Production builds call the API directly, e.g. ' +
        'VITE_API_URL=https://truck-routing-api-mo4g.onrender.com/api/v1 npm run build (set it in Vercel for deploys).',
    )
  }
  let origin: string
  try {
    origin = new URL(url).origin
  } catch {
    throw new Error(`VITE_API_URL must be an absolute URL, got "${url}".`)
  }
  const csp = vercelHeaders()['Content-Security-Policy'] ?? ''
  const connect = csp.split(';').map((d) => d.trim()).find((d) => d.startsWith('connect-src')) ?? ''
  if (!connect.split(/\s+/).includes(origin)) {
    throw new Error(
      `The Content-Security-Policy in vercel.json doesn't allow ${origin}: add it to connect-src, ` +
        'or every API call will be blocked in production.',
    )
  }
}

export default defineConfig(({ command, mode }) => {
  if (command === 'build' && mode === 'production') {
    checkProductionApi(loadEnv(mode, process.cwd(), 'VITE_').VITE_API_URL)
  }
  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      proxy: {
        '/api': { target: process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8765', changeOrigin: true },
      },
    },
    // `vite preview` serves the production build with the same headers as Vercel.
    preview: { headers: vercelHeaders() },
    worker: { format: 'es' },
    build: {
      // MapLibre alone is ~1 MB minified; it is split into its own cached chunk.
      chunkSizeWarningLimit: 1200,
      rollupOptions: {
        output: {
          manualChunks: (id: string) => (id.includes('node_modules/maplibre-gl') ? 'maplibre' : undefined),
        },
      },
    },
  }
})
