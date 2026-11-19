import { ChevronDown, Info } from 'lucide-react'
import { useState } from 'react'

import type { RiskRules } from '../api/types'
import { RISK_LABEL, RISK_ORDER } from '../lib/risk'
import { loadRuleRows, thresholdRows } from '../lib/riskRules'
import { RiskChip, RiskDot } from './RiskChip'

interface Props {
  /** Thresholds from /risk-rules/. Null while loading or if the request
   *  failed: the legend then shows the colours only, with no numbers. */
  rules: RiskRules | null
}

export function Legend({ rules }: Props) {
  const [open, setOpen] = useState(false)
  return (
    <div className="clay pointer-events-auto max-h-[calc(100%-1.5rem)] max-w-full overflow-auto rounded-[20px] p-2.5 text-[12px] sm:rounded-[22px] sm:p-3 sm:text-[13px]">
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 sm:gap-x-3.5 sm:gap-y-1.5 lg:flex-nowrap">
        {[...RISK_ORDER, 'unknown' as const].map((k) => (
          <span key={k} className="flex items-center gap-1.5 whitespace-nowrap text-ink/85">
            <RiskDot level={k} />
            {RISK_LABEL[k]}
          </span>
        ))}
        {rules && (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-controls="risk-rules"
          className="focus-ring ml-auto flex items-center gap-1 whitespace-nowrap rounded-lg px-1.5 py-0.5 font-semibold text-accent"
        >
          <Info size={14} strokeWidth={2} aria-hidden />
          Risk rules
          <ChevronDown size={14} className={`transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden />
        </button>
        )}
      </div>

      {open && rules && (
        <div id="risk-rules" className="mt-3 space-y-3">
          <div className="clay-pressed overflow-x-auto rounded-2xl p-2.5">
            <table className="tabular w-full min-w-[420px] text-[12.5px]">
              <caption className="sr-only">Weather thresholds per risk level</caption>
              <thead>
                <tr className="text-left text-muted">
                  <th className="pb-1.5 pr-2 font-semibold">Condition</th>
                  {RISK_ORDER.map((k) => (
                    <th key={k} className="px-1 pb-1.5 font-semibold">
                      <span className="flex items-center gap-1">
                        <RiskDot level={k} className="h-2 w-2" />
                        {RISK_LABEL[k]}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {thresholdRows(rules).map((row) => (
                  <tr key={row.condition} className="border-t border-line">
                    <th scope="row" className="py-1.5 pr-2 text-left font-semibold text-ink">
                      {row.condition} <span className="font-normal text-faint">{row.unit}</span>
                    </th>
                    {row.values.map((v) => (
                      <td key={v} className="px-1 py-1.5 text-ink/85">
                        {v}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            <p className="mb-1.5 font-semibold text-ink">Heavier loads raise wind risk</p>
            <ul className="space-y-1.5">
              {loadRuleRows(rules).map((r) => (
                <li key={r.wind} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-ink/85">
                  <span>
                    Wind {r.wind}, {r.load}
                  </span>
                  <span className="text-faint" aria-hidden>
                    becomes
                  </span>
                  <RiskChip level={r.result} size="sm" />
                </li>
              ))}
            </ul>
          </div>
          <p className="text-muted">Each checkpoint takes the worst of wind (after load rules), rain and snow.</p>
        </div>
      )}
    </div>
  )
}
