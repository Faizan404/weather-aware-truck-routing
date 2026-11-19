import type { RiskKey } from '../api/types'
import { RISK_LABEL, RISK_TEXT, riskVar } from '../lib/risk'

export function RiskChip({ level, size = 'md' }: { level: RiskKey; size?: 'sm' | 'md' }) {
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-full font-semibold leading-none ${
        size === 'sm' ? 'px-2 py-1 text-[11px]' : 'px-2.5 py-1.5 text-xs'
      }`}
      style={{ background: riskVar(level), color: RISK_TEXT[level], boxShadow: 'inset 0 -1px 2px rgb(0 0 0 / .15), inset 0 1px 1px rgb(255 255 255 / .25)' }}
    >
      {RISK_LABEL[level]}
    </span>
  )
}

export function RiskDot({ level, className = '' }: { level: RiskKey; className?: string }) {
  return <span className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${className}`} style={{ background: riskVar(level) }} />
}
