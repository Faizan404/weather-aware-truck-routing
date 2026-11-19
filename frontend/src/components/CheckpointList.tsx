import { CloudRain, Snowflake, Wind } from 'lucide-react'
import { memo } from 'react'

import type { RouteOption } from '../api/types'
import { formatDateTime, formatValue } from '../lib/format'
import type { CheckpointRef } from './MapView'
import { RiskChip } from './RiskChip'

interface Props {
  route: RouteOption
  hovered: CheckpointRef | null
  onHover: (ref: CheckpointRef | null) => void
}

export const CheckpointList = memo(function CheckpointList({ route, hovered, onHover }: Props) {
  const icon = { size: 12, strokeWidth: 2, 'aria-hidden': true } as const
  return (
    <div className="clay-pressed overflow-hidden rounded-[22px] p-1.5">
      <ul onMouseLeave={() => onHover(null)} aria-label={`Weather checkpoints on ${route.label}`}>
        {route.checkpoints.map((cp) => {
          const active = hovered?.routeId === route.id && hovered.index === cp.index
          return (
            <li
              key={cp.index}
              onMouseEnter={() => onHover({ routeId: route.id, index: cp.index })}
              onFocus={() => onHover({ routeId: route.id, index: cp.index })}
              tabIndex={0}
              className={`focus-ring grid cursor-default grid-cols-[3.25rem_1fr_auto] items-center gap-2.5 rounded-2xl px-2.5 py-2 outline-none [contain-intrinsic-size:auto_58px] [content-visibility:auto] ${
                active ? 'clay-sm' : ''
              }`}
            >
              <span className="tabular text-right leading-tight">
                <span className="block text-[15px] font-bold text-ink">{cp.mile.toFixed(0)}</span>
                <span className="block text-[11px] text-faint">mi</span>
              </span>
              <span className="min-w-0">
                <span className="block text-[13px] font-semibold text-ink">{formatDateTime(cp.eta)}</span>
                <span className="tabular mt-0.5 flex flex-wrap gap-x-2.5 text-[12px] text-muted">
                  <span className="inline-flex items-center gap-1">
                    <Wind {...icon} />
                    {formatValue(cp.wind_mph, 'mph', 1)}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <CloudRain {...icon} />
                    {formatValue(cp.rain_in_hr, 'in/hr', 2)}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Snowflake {...icon} />
                    {formatValue(cp.snow_in_hr, 'in/hr', 2)}
                  </span>
                </span>
                {cp.reasons.length > 0 && <span className="mt-0.5 block truncate text-[12px] font-medium text-ink/80">{cp.reasons.join('; ')}</span>}
              </span>
              <RiskChip level={cp.level} size="sm" />
            </li>
          )
        })}
      </ul>
    </div>
  )
})
