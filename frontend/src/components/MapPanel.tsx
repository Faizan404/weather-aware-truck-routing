import { LoaderCircle, MapPinned } from 'lucide-react'
import { lazy, Suspense } from 'react'

import type { TripPlan } from '../hooks/useTripPlan'
import type { Theme } from '../hooks/useTheme'
import { errorMessages } from '../lib/errors'
import { COLD_START_MESSAGE } from '../lib/slowRequest'
import { ForecastSlider } from './ForecastSlider'
import { Legend } from './Legend'

// MapLibre is ~1 MB: load it in its own chunk so the form is usable first.
const MapView = lazy(() => import('./MapView').then((m) => ({ default: m.MapView })))

function MapLoading() {
  return (
    <div className="flex h-full w-full items-center justify-center bg-well" role="status">
      <span className="flex items-center gap-2 text-[13px] font-semibold text-muted">
        <LoaderCircle size={15} className="animate-spin" aria-hidden />
        Loading map…
      </span>
    </div>
  )
}

/** The map with its legend, empty/loading overlays and the forecast panel. */
export function MapPanel({ theme, trip }: { theme: Theme; trip: TripPlan }) {
  const { plan, heatmap: heat } = trip
  return (
    <>
      <Suspense fallback={<MapLoading />}>
        <MapView
          theme={theme}
          plan={plan}
          heatmap={heat.data}
          heatMetric={heat.metric}
          heatScales={heat.scales}
          heatHour={heat.hour}
          showHeatmap={heat.visible}
          selectedRouteId={trip.selectedRouteId}
          onSelectRoute={trip.selectRoute}
          hoveredCheckpoint={trip.hovered}
          onHoverCheckpoint={trip.onHover}
        />
      </Suspense>

      <div className="pointer-events-none absolute inset-x-3 top-3 bottom-3 flex max-w-[600px] flex-col items-start pr-12 sm:inset-x-4 sm:top-4">
        <Legend rules={trip.rules} />
      </div>

      {!plan && !trip.isLoading && (
        <div className="pointer-events-none absolute inset-0 flex items-end justify-center p-4 pb-14 sm:items-center sm:p-6">
          <div className="clay flex max-w-xs flex-col items-center gap-2 rounded-[24px] px-6 py-5 text-center">
            <span className="clay-pressed flex h-11 w-11 items-center justify-center rounded-2xl text-accent" aria-hidden>
              <MapPinned size={22} strokeWidth={1.9} />
            </span>
            <p className="text-[15px] font-bold text-ink">Plan a trip to compare routes</p>
            <p className="text-[13px] text-muted">Add where you’re starting, where you’re going, when you leave and your load.</p>
          </div>
        </div>
      )}
      {trip.isLoading && (
        <div className="pointer-events-none absolute inset-x-0 top-20 flex justify-center px-4">
          <div className="clay-sm flex max-w-sm items-center gap-2 rounded-2xl px-4 py-2 text-[13px] font-semibold text-ink">
            <LoaderCircle size={15} className="animate-spin shrink-0 text-accent" aria-hidden />
            <span role="status">{trip.isSlow ? COLD_START_MESSAGE : 'Checking the weather along each route…'}</span>
          </div>
        </div>
      )}

      {plan && (
        <div className="pointer-events-none absolute inset-x-2 bottom-7 mx-auto max-w-[580px] sm:inset-x-4 sm:bottom-8">
          <ForecastSlider
            hours={heat.data?.hours ?? null}
            hour={heat.hour}
            onHourChange={heat.setHour}
            metric={heat.metric}
            scales={heat.scales}
            onMetricChange={heat.setMetric}
            visible={heat.visible}
            onVisibleChange={heat.setVisible}
            loading={heat.loading}
            error={heat.error ? errorMessages(heat.error)[0] : null}
            rateLimited={heat.rateLimited}
            hourHasNoData={heat.hourHasNoData}
          />
        </div>
      )}
    </>
  )
}
