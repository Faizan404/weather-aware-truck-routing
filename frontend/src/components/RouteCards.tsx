import { Clock, CloudOff, OctagonAlert, Ruler, ShieldCheck, TriangleAlert } from 'lucide-react'
import { useRef, type KeyboardEvent, type ReactNode } from 'react'

import type { PlanResponse, RouteOption } from '../api/types'
import { formatDateTime, formatDuration, formatMiles } from '../lib/format'
import { RISK_LABEL, RISK_ORDER, riskVar } from '../lib/risk'
import { radioKeyTarget, rovingTabStop } from '../lib/roving'
import { RiskChip } from './RiskChip'

function RiskBar({ route }: { route: RouteOption }) {
  const { miles_by_level, unknown_miles } = route.summary
  const total = route.distance_miles || 1
  const parts = [
    ...RISK_ORDER.map((k) => ({ key: k, miles: miles_by_level[k] })),
    { key: 'unknown' as const, miles: unknown_miles },
  ].filter((p) => p.miles > 0)
  const description = parts.map((p) => `${RISK_LABEL[p.key]} ${formatMiles(p.miles)}`).join(', ')
  return (
    <div className="clay-pressed flex h-2.5 w-full gap-px overflow-hidden rounded-full p-px" role="img" aria-label={`Miles by risk: ${description}`}>
      {parts.map((p) => (
        <div
          key={p.key}
          title={`${RISK_LABEL[p.key]}: ${formatMiles(p.miles, 1)}`}
          className="h-full rounded-full"
          style={{ width: `${(p.miles / total) * 100}%`, background: riskVar(p.key) }}
        />
      ))}
    </div>
  )
}

function Stat({ icon, label, value, tone }: { icon: ReactNode; label: string; value: string; tone?: string }) {
  return (
    <div className="min-w-0">
      <dt className="flex items-center gap-1 text-[12px] text-faint">
        <span aria-hidden>{icon}</span>
        {label}
      </dt>
      <dd className={`tabular mt-0.5 truncate text-[15px] font-bold ${tone ?? 'text-ink'}`}>{value}</dd>
    </div>
  )
}

interface Props {
  plan: PlanResponse
  selectedRouteId: string | null
  onSelect: (id: string) => void
}

export function RouteCards({ plan, selectedRouteId, onSelect }: Props) {
  const rec = plan.recommendation
  const order = rec.ranking
  const routes = [...plan.routes].sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id))
  const iconProps = { size: 13, strokeWidth: 2 }
  // Roving tabindex: Tab enters the group on the selected card; arrows,
  // Home and End move the selection (and focus) within it.
  const buttons = useRef<(HTMLButtonElement | null)[]>([])
  const tabStop = rovingTabStop(
    routes.map((r) => r.id),
    selectedRouteId,
  )
  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const target = radioKeyTarget(e.key, index, routes.length)
    if (target === null) return
    e.preventDefault()
    onSelect(routes[target].id)
    buttons.current[target]?.focus()
  }
  return (
    <div className="space-y-3" role="radiogroup" aria-label="Route options" aria-orientation="vertical">
      {routes.map((route, index) => {
        const s = route.summary
        const recommended = route.id === rec.route_id
        const selected = route.id === selectedRouteId
        const severePlus = s.miles_by_level.severe + s.miles_by_level.no_travel
        const noTravel = s.miles_by_level.no_travel
        const subtitle = route.via.length
          ? `Via ${route.via.join(', ')}`
          : route.synthetic
            ? 'Alternative corridor'
            : 'Main route'
        return (
          <button
            key={route.id}
            ref={(el) => {
              buttons.current[index] = el
            }}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={route.id === tabStop ? 0 : -1}
            onClick={() => onSelect(route.id)}
            onKeyDown={(e) => onKeyDown(e, index)}
            className={`focus-ring @container block w-full rounded-[22px] p-4 text-left transition-shadow ${
              selected ? 'clay-pressed' : 'clay-sm hover:brightness-[1.01]'
            }`}
          >
            <div className="flex items-start gap-3">
              <span
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[15px] font-extrabold ${
                  selected ? 'clay-accent' : 'clay-sm text-ink'
                }`}
                aria-hidden
              >
                {route.id}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="text-[15px] font-bold text-ink">{route.label}</span>
                  {recommended && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-ok-soft px-2 py-0.5 text-[11.5px] font-bold text-risk-low">
                      <ShieldCheck size={13} strokeWidth={2.2} aria-hidden />
                      Recommended
                    </span>
                  )}
                </div>
                <p className="truncate text-[13px] text-muted">{subtitle}</p>
              </div>
              <RiskChip level={s.max_level} />
            </div>

            <dl className="mt-3.5 grid grid-cols-2 gap-x-3 gap-y-2.5 @[360px]:grid-cols-4">
              <Stat icon={<Ruler {...iconProps} />} label="Distance" value={formatMiles(route.distance_miles)} />
              <Stat icon={<Clock {...iconProps} />} label="Drive time" value={formatDuration(route.duration_seconds)} />
              <Stat
                icon={<OctagonAlert {...iconProps} />}
                label="Severe+"
                value={formatMiles(severePlus)}
                tone={severePlus > 0 ? 'text-risk-severe' : undefined}
              />
              <Stat
                icon={<TriangleAlert {...iconProps} />}
                label="High"
                value={formatMiles(s.miles_by_level.high)}
                tone={s.miles_by_level.high > 0 ? 'text-risk-high' : undefined}
              />
            </dl>

            <div className="mt-3.5">
              <RiskBar route={route} />
            </div>
            <div className="mt-2 flex flex-wrap justify-between gap-x-3 gap-y-0.5 text-[12.5px] text-muted">
              <span className="tabular">Average risk {s.avg_risk === null ? 'n/a' : s.avg_risk.toFixed(2)} of 4</span>
              <span>Arrives {formatDateTime(route.arrival)}</span>
            </div>
            {noTravel > 0 && (
              <p className="mt-2 flex items-center gap-1.5 text-[12.5px] font-semibold text-risk-no-travel">
                <OctagonAlert size={14} strokeWidth={2.2} aria-hidden />
                {formatMiles(noTravel, 1)} in No Travel conditions
              </p>
            )}
            {s.incomplete && (
              <p className="mt-1.5 flex items-center gap-1.5 text-[12.5px] text-muted">
                <CloudOff size={14} strokeWidth={2} aria-hidden />
                {formatMiles(s.unknown_miles, 1)} without forecast data
              </p>
            )}
          </button>
        )
      })}
    </div>
  )
}
