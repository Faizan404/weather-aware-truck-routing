import { maplibregl } from '../lib/maplibre'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useMemo, useRef, useState } from 'react'

import type { HeatmapResponse, PlanResponse } from '../api/types'
import {
  checkpointFeatureId,
  checkpointsGeoJSON,
  endpointsGeoJSON,
  heatmapGeoJSON,
  planBounds,
  routeLinesGeoJSON,
  routeSegmentsGeoJSON,
  type HeatMetric,
} from '../lib/geojson'
import type { HeatScales } from '../lib/riskRules'
import type { Theme } from '../hooks/useTheme'
import { addAppLayers, EMPTY, heatColorExpression, STYLE_URL } from '../lib/mapLayers'
import { popupHtml } from '../lib/mapPopup'

export interface CheckpointRef {
  routeId: string
  index: number
}

interface Props {
  theme: Theme
  plan: PlanResponse | null
  heatmap: HeatmapResponse | null
  heatMetric: HeatMetric
  /** Wind/rain/snow band breaks from /risk-rules/ (null: not loaded). */
  heatScales: HeatScales | null
  heatHour: number
  showHeatmap: boolean
  selectedRouteId: string | null
  onSelectRoute: (id: string) => void
  hoveredCheckpoint: CheckpointRef | null
  onHoverCheckpoint: (ref: CheckpointRef | null) => void
}

export function MapView({
  theme,
  plan,
  heatmap,
  heatMetric,
  heatScales,
  heatHour,
  showHeatmap,
  selectedRouteId,
  onSelectRoute,
  hoveredCheckpoint,
  onHoverCheckpoint,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const popupRef = useRef<maplibregl.Popup | null>(null)
  const hoveredIdRef = useRef<number | null>(null)
  const fittedKeyRef = useRef<string | null>(null)
  // Bumped each time our layers are (re)built, so data effects re-apply.
  const [styleVersion, setStyleVersion] = useState(0)
  const themeRef = useRef(theme)
  const appliedThemeRef = useRef(theme)

  // Latest values for event handlers registered once at init.
  const handlersRef = useRef({ onSelectRoute, onHoverCheckpoint })
  useEffect(() => {
    handlersRef.current = { onSelectRoute, onHoverCheckpoint }
  }, [onSelectRoute, onHoverCheckpoint])

  const routeById = useMemo(() => new Map(plan?.routes.map((r) => [r.id, r]) ?? []), [plan])

  // --- Init once ------------------------------------------------------------
  useEffect(() => {
    if (!containerRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE_URL[themeRef.current],
      center: [-96, 38.5],
      zoom: 3.6,
      attributionControl: false,
      fadeDuration: 0,
    })
    mapRef.current = map
    if (import.meta.env.DEV) (window as unknown as { __map: maplibregl.Map }).__map = map
    map.on('error', (e) => console.error('[map]', e.error?.message ?? e))
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    // On stacked (phone/tablet) layouts the forecast panel spans the bottom of
    // the map, so the attribution goes under the zoom buttons instead.
    const stacked = window.matchMedia('(max-width: 1023.98px)').matches
    map.addControl(new maplibregl.AttributionControl({ compact: true }), stacked ? 'top-right' : 'bottom-right')
    // MapLibre opens the compact attribution at first; start it collapsed to
    // the (i) button so it doesn't cover the map. It still opens on click.
    map.once('load', () =>
      containerRef.current?.querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show'),
    )
    popupRef.current = new maplibregl.Popup({ closeButton: false, closeOnClick: false, maxWidth: '280px', offset: 10 })

    map.on('style.load', () => {
      addAppLayers(map, appliedThemeRef.current)
      setStyleVersion((v) => v + 1)
    })

    // Layer-bound listeners survive style switches (they attach by layer id).
    map.on('click', 'route-hit', (e) => {
      const id = e.features?.[0]?.properties?.routeId
      if (id) handlersRef.current.onSelectRoute(id)
    })
    map.on('mouseenter', 'route-hit', () => (map.getCanvas().style.cursor = 'pointer'))
    map.on('mouseleave', 'route-hit', () => (map.getCanvas().style.cursor = ''))
    map.on('mousemove', 'checkpoints', (e) => {
      const props = e.features?.[0]?.properties
      if (!props) return
      map.getCanvas().style.cursor = 'pointer'
      handlersRef.current.onHoverCheckpoint({ routeId: props.routeId, index: props.index })
    })
    map.on('mouseleave', 'checkpoints', () => {
      map.getCanvas().style.cursor = ''
      handlersRef.current.onHoverCheckpoint(null)
    })
    map.on('click', 'checkpoints', (e) => {
      const props = e.features?.[0]?.properties
      if (props) handlersRef.current.onSelectRoute(props.routeId)
    })

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // --- Theme: swap the basemap; style.load rebuilds our layers -------------
  useEffect(() => {
    themeRef.current = theme
    const map = mapRef.current
    if (!map || styleVersion === 0 || appliedThemeRef.current === theme) return
    appliedThemeRef.current = theme
    hoveredIdRef.current = null
    map.setStyle(STYLE_URL[theme])
  }, [theme, styleVersion])

  // --- Plan data ----------------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || styleVersion === 0) return
    const set = (id: string, data: GeoJSON.FeatureCollection) =>
      (map.getSource(id) as maplibregl.GeoJSONSource).setData(data)
    if (!plan) {
      ;['route-lines', 'route-segments', 'checkpoints', 'endpoints'].forEach((id) => set(id, EMPTY))
      return
    }
    set('route-lines', routeLinesGeoJSON(plan))
    set('route-segments', routeSegmentsGeoJSON(plan))
    set('checkpoints', checkpointsGeoJSON(plan))
    set('endpoints', endpointsGeoJSON(plan))
    hoveredIdRef.current = null
    // Only re-frame when the routes themselves change (not on an interval
    // switch), so a user's own zoom/pan is kept.
    const geometryKey = plan.routes.map((r) => r.geometry).join('|')
    if (geometryKey === fittedKeyRef.current) return
    fittedKeyRef.current = geometryKey
    // Below 1024px the map is stacked above the panel and the overlays are smaller.
    const isMobile = window.innerWidth < 1024
    map.fitBounds(planBounds(plan), {
      // Keep the route clear of the legend (top) and the forecast slider (bottom).
      padding: isMobile ? { top: 90, bottom: 150, left: 30, right: 50 } : { top: 110, bottom: 240, left: 70, right: 70 },
      duration: 800,
      maxZoom: 13,
    })
  }, [plan, styleVersion])

  // --- Selected route: emphasise it, dim the others -------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || styleVersion === 0) return
    const sel = selectedRouteId ?? ''
    const isSel: maplibregl.ExpressionSpecification = ['==', ['get', 'routeId'], sel]
    map.setPaintProperty('route-segments', 'line-opacity', ['case', isSel, 1, 0.35])
    map.setPaintProperty('route-segments', 'line-width', ['case', isSel, 6, 4])
    map.setPaintProperty('route-casing', 'line-opacity', ['case', isSel, 0.95, 0.5])
    map.setPaintProperty('route-casing', 'line-width', ['case', isSel, 10, 7])
    map.setLayoutProperty('route-segments', 'line-sort-key', ['case', isSel, 10, 0])
    map.setLayoutProperty('route-casing', 'line-sort-key', ['case', isSel, 10, 0])
    map.setPaintProperty('checkpoints', 'circle-opacity', ['case', isSel, 1, 0.45])
    map.setPaintProperty('checkpoints', 'circle-stroke-opacity', ['case', isSel, 1, 0.45])
    map.setLayoutProperty('checkpoints', 'circle-sort-key', ['case', isSel, 10, 0])
  }, [selectedRouteId, styleVersion, plan])

  // --- Heatmap data (only when data or metric change) -----------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || styleVersion === 0) return
    const source = map.getSource('heat') as maplibregl.GeoJSONSource
    source.setData(heatmap ? heatmapGeoJSON(heatmap, heatMetric, heatScales) : EMPTY)
    if (heatmap) {
      // Radius follows the grid spacing so neighbouring cells blend smoothly.
      const pxPerDegAtZ0 = 512 / 360
      const r0 = Math.max(1, heatmap.resolution_deg * 1.4 * pxPerDegAtZ0)
      map.setPaintProperty('heat', 'circle-radius', [
        'interpolate', ['exponential', 2], ['zoom'],
        0, r0,
        12, r0 * 4096,
      ])
    }
  }, [heatmap, heatMetric, heatScales, styleVersion])

  // --- Slider: swap the weight property, nothing else -----------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || styleVersion === 0) return
    map.setPaintProperty('heat', 'circle-color', heatColorExpression(heatHour, appliedThemeRef.current))
  }, [heatHour, styleVersion])

  useEffect(() => {
    const map = mapRef.current
    if (!map || styleVersion === 0) return
    map.setLayoutProperty('heat', 'visibility', showHeatmap ? 'visible' : 'none')
  }, [showHeatmap, styleVersion])

  // --- Hovered checkpoint (from map or list): highlight + popup -------------
  useEffect(() => {
    const map = mapRef.current
    const popup = popupRef.current
    if (!map || styleVersion === 0 || !popup) return
    if (hoveredIdRef.current !== null) {
      map.setFeatureState({ source: 'checkpoints', id: hoveredIdRef.current }, { hover: false })
      hoveredIdRef.current = null
    }
    const route = hoveredCheckpoint ? routeById.get(hoveredCheckpoint.routeId) : undefined
    const cp = route?.checkpoints[hoveredCheckpoint!.index]
    if (!route || !cp) {
      popup.remove()
      return
    }
    const id = checkpointFeatureId(route.id, cp.index)
    map.setFeatureState({ source: 'checkpoints', id }, { hover: true })
    hoveredIdRef.current = id
    popup.setLngLat([cp.lon, cp.lat]).setHTML(popupHtml(route, cp)).addTo(map)
  }, [hoveredCheckpoint, routeById, styleVersion])

  // MapLibre's CSS sets `position: relative` on the map element, so the
  // absolute sizing lives on a wrapper.
  return (
    <div className="absolute inset-0">
      <div ref={containerRef} className="h-full w-full" aria-label="Map of route options" role="region" />
    </div>
  )
}
