import { CalendarClock, OctagonAlert, Ruler, ShieldCheck, TriangleAlert, Weight } from 'lucide-react'
import { memo, useEffect, useRef } from 'react'

import type { PlanResponse } from '../api/types'
import { formatDateTime } from '../lib/format'
import { CheckpointList } from './CheckpointList'
import type { CheckpointRef } from './MapView'
import { Notice } from './Notice'
import { RouteCards } from './RouteCards'

const MemoRouteCards = memo(RouteCards)

interface Props {
  plan: PlanResponse
  /** False while a newer plan loads (the old one stays, faded). */
  isCurrent: boolean
  /** Bumps when new plan data arrives, to scroll the recommendation into view. */
  updatedAt: number
  warnings: string[]
  selectedRouteId: string | null
  onSelect: (id: string) => void
  hovered: CheckpointRef | null
  onHover: (ref: CheckpointRef | null) => void
}

/** The recommendation, warnings, route cards and the selected route's checkpoints. */
export function PlanResults({ plan, isCurrent, updatedAt, warnings, selectedRouteId, onSelect, hovered, onHover }: Props) {
  const rec = plan.recommendation
  const recRoute = plan.routes.find((r) => r.id === rec.route_id)
  const selectedRoute = plan.routes.find((r) => r.id === selectedRouteId) ?? null

  // On stacked layouts (phones, tablets) results sit below the map, so bring
  // the recommendation into view once a plan has loaded.
  const recRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!isCurrent || !recRef.current) return
    if (!window.matchMedia('(max-width: 1023.98px)').matches) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    recRef.current.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
  }, [updatedAt, isCurrent])

  return (
    <section className={`space-y-4 transition-opacity ${isCurrent ? '' : 'opacity-60'}`} aria-busy={!isCurrent} aria-label="Results">
      {rec.no_safe_route && (
        <Notice role="alert" tone="violet" icon={<OctagonAlert size={18} strokeWidth={2} />} title="No safe route at this departure time">
          Every option passes through No Travel conditions. Try a different departure time.
        </Notice>
      )}

      <div ref={recRef} className="clay-sm scroll-mt-3 rounded-[22px] p-4">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-ok-soft text-risk-low" style={{ boxShadow: 'var(--clay-pressed)' }} aria-hidden>
            <ShieldCheck size={20} strokeWidth={2} />
          </span>
          <div className="min-w-0">
            <h2 className="text-[16px] font-extrabold text-ink">
              Take {recRoute?.label}
              {recRoute?.via.length ? <span className="font-semibold text-muted"> via {recRoute.via.join(', ')}</span> : null}
            </h2>
            <p className="mt-0.5 text-[13.5px] text-ink/85">{rec.reason}</p>
            {rec.notes.map((n) => (
              <p key={n} className="mt-1 text-[13px] text-muted">
                {n}
              </p>
            ))}
          </div>
        </div>
        <dl className="mt-3.5 flex flex-wrap gap-x-5 gap-y-1.5 border-t border-line pt-3 text-[12.5px] text-muted">
          <div className="flex items-center gap-1.5">
            <CalendarClock size={14} strokeWidth={2} aria-hidden />
            <dt className="sr-only">Departure</dt>
            <dd>{formatDateTime(plan.request.departure_time)}</dd>
          </div>
          <div className="flex items-center gap-1.5">
            <Weight size={14} strokeWidth={2} aria-hidden />
            <dt className="sr-only">Load</dt>
            <dd className="tabular">{plan.request.load_weight_lbs.toLocaleString()} lb</dd>
          </div>
          <div className="flex items-center gap-1.5">
            <Ruler size={14} strokeWidth={2} aria-hidden />
            <dt className="sr-only">Checkpoint interval</dt>
            <dd>Every {plan.request.interval_miles} mi</dd>
          </div>
        </dl>
      </div>

      {warnings.length > 0 && (
        <Notice role="status" tone="warn" icon={<TriangleAlert size={18} strokeWidth={2} />}>
          <ul className="space-y-1">
            {[...new Set(warnings)].map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </Notice>
      )}

      <div>
        <h2 className="mb-2.5 px-1 text-[15px] font-bold text-ink">Route options</h2>
        <MemoRouteCards plan={plan} selectedRouteId={selectedRouteId} onSelect={onSelect} />
      </div>

      {selectedRoute && (
        <div>
          <h2 className="mb-2.5 flex items-baseline justify-between px-1 text-[15px] font-bold text-ink">
            {selectedRoute.label} checkpoints
            <span className="tabular text-[13px] font-semibold text-muted">{selectedRoute.checkpoints.length} stops</span>
          </h2>
          <CheckpointList route={selectedRoute} hovered={hovered} onHover={onHover} />
        </div>
      )}
    </section>
  )
}
