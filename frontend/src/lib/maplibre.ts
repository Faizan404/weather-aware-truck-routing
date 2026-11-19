import * as maplibregl from 'maplibre-gl'
// MapLibre 6 loads its tile worker relative to its own module URL, which breaks
// once Vite bundles it. Let Vite bundle the worker and pass its URL explicitly.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

maplibregl.setWorkerUrl(workerUrl)

export { maplibregl }
