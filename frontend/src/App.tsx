import { CircleAlert } from 'lucide-react'

import { AppHeader } from './components/AppHeader'
import { MapPanel } from './components/MapPanel'
import { Notice } from './components/Notice'
import { PlanResults } from './components/PlanResults'
import { TripForm } from './components/TripForm'
import { useTheme } from './hooks/useTheme'
import { useTripPlan } from './hooks/useTripPlan'
import { errorMessages } from './lib/errors'

/** Layout only: the trip state lives in useTripPlan. */
export default function App() {
  const { preference, theme, setPreference } = useTheme()
  const trip = useTripPlan()
  const { plan } = trip
  const headerProps = { theme: preference, onThemeChange: setPreference }

  return (
    <div className="flex min-h-dvh flex-col gap-3 bg-base p-3 text-ink lg:h-dvh lg:flex-row lg:gap-4 lg:p-4">
      {/* On phones the header sits above the map; on desktop it heads the sidebar. */}
      <AppHeader className="order-0 flex px-1 lg:hidden" {...headerProps} />

      <aside className="clay order-2 flex flex-col rounded-[28px] lg:order-1 lg:h-full lg:w-[400px] lg:shrink-0 xl:w-[440px]">
        <AppHeader className="hidden border-b border-line px-5 py-4 lg:flex" {...headerProps} />

        <div className="@container flex-1 space-y-5 p-4 sm:p-5 lg:overflow-y-auto">
          {/* onEdit only while a banner is showing, so typing doesn't re-render the map. */}
          <TripForm
            trip={plan ? trip.trip : null}
            onSubmit={trip.submit}
            onEdit={trip.error ? trip.hideError : undefined}
            loading={trip.isLoading}
          />

          {trip.error !== null && (
            <Notice role="alert" tone="danger" icon={<CircleAlert size={18} strokeWidth={2} />} title="Couldn’t plan this trip">
              {errorMessages(trip.error).map((m) => (
                <p key={m}>{m}</p>
              ))}
            </Notice>
          )}

          {trip.isLoading && !plan && (
            <div className="space-y-3" aria-hidden>
              {[0, 1, 2].map((i) => (
                <div key={i} className="clay-sm h-32 animate-pulse rounded-[22px]" />
              ))}
            </div>
          )}

          {plan && (
            <PlanResults
              plan={plan}
              isCurrent={trip.isCurrent}
              updatedAt={trip.planQuery.dataUpdatedAt}
              warnings={trip.warnings}
              selectedRouteId={trip.selectedRouteId}
              onSelect={trip.selectRoute}
              hovered={trip.hovered}
              onHover={trip.onHover}
            />
          )}
        </div>
      </aside>

      <main className="clay relative order-1 h-[62vh] min-h-[380px] flex-1 overflow-hidden rounded-[28px] lg:order-2 lg:h-full">
        <MapPanel theme={theme} trip={trip} />
      </main>
    </div>
  )
}
