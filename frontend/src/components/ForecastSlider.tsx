import { ChevronDown, ChevronUp, CloudOff, CloudRain, Gauge, LoaderCircle, Pause, Play, Snowflake, Wind } from 'lucide-react'
import { useEffect, useId, useState } from 'react'

import { formatShortDate } from '../lib/format'
import { HEAT_METRIC_LABEL, type HeatMetric } from '../lib/geojson'
import { WEATHER_LIMIT_MESSAGE } from '../lib/messages'
import { RISK_LABEL, RISK_ORDER } from '../lib/risk'
import type { HeatScales } from '../lib/riskRules'

interface Props {
  hours: string[] | null // ISO timestamps for hour 0..48
  hour: number
  onHourChange: (hour: number) => void
  metric: HeatMetric
  onMetricChange: (metric: HeatMetric) => void
  visible: boolean
  onVisibleChange: (visible: boolean) => void
  loading: boolean
  error: string | null
  hourHasNoData: boolean
  /** The forecast is missing because the weather service limit was reached. */
  rateLimited: boolean
  /** Wind/rain/snow scales from /risk-rules/; null disables those layers. */
  scales: HeatScales | null
}

const METRICS: HeatMetric[] = ['risk', 'wind', 'rain', 'snow']

const PLAY_STEP_MS = 450
const METRIC_ICON: Record<HeatMetric, typeof Wind> = { risk: Gauge, wind: Wind, rain: CloudRain, snow: Snowflake }
const SCALE = 'linear-gradient(90deg, var(--risk-low), var(--risk-moderate), var(--risk-high), var(--risk-severe), var(--risk-no-travel))'

export function ForecastSlider({
  hours,
  hour,
  onHourChange,
  metric,
  onMetricChange,
  visible,
  onVisibleChange,
  loading,
  error,
  hourHasNoData,
  rateLimited,
  scales,
}: Props) {
  const [playing, setPlaying] = useState(false)
  // Phones/tablets start with only the slider row; desktop always shows all.
  const [expanded, setExpanded] = useState(false)
  const detailsId = useId()
  const more = expanded ? 'flex' : 'hidden lg:flex'
  const max = hours ? hours.length - 1 : 48
  const disabled = !hours

  useEffect(() => {
    if (!playing || !hours) return
    const t = setInterval(() => onHourChange(hour >= max ? 0 : hour + 1), PLAY_STEP_MS)
    return () => clearInterval(t)
  }, [playing, hour, max, hours, onHourChange])

  const label = HEAT_METRIC_LABEL[metric]
  const raw = metric === 'risk' ? null : (scales?.[metric] ?? null)
  const ticks = metric === 'risk' ? RISK_ORDER.map((k) => RISK_LABEL[k]) : (raw?.labels ?? [])
  const fill = `${(hour / max) * 100}%`

  return (
    <section className="clay pointer-events-auto rounded-[24px] p-3 sm:p-4" aria-label="Weather forecast along the corridor">
      <div id={`${detailsId}-top`} className={`${more} mb-3 flex-wrap items-center justify-between gap-2`}>
        <label className="flex cursor-pointer items-center gap-2.5 text-[14px] font-bold text-ink">
          <span className="relative inline-flex">
            <input
              type="checkbox"
              checked={visible}
              onChange={(e) => onVisibleChange(e.target.checked)}
              className="peer sr-only"
            />
            <span className="clay-pressed h-6 w-10 rounded-full transition-colors peer-checked:bg-accent-soft peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-accent" />
            <span className="clay-sm absolute left-0.5 top-0.5 h-5 w-5 rounded-full transition-transform peer-checked:translate-x-4 peer-checked:bg-accent" />
          </span>
          Forecast map
          {loading && <LoaderCircle size={15} className="animate-spin text-faint" aria-label="Loading forecast" />}
        </label>

        <div className="clay-pressed flex gap-0.5 rounded-full p-1" role="radiogroup" aria-label="Forecast layer">
          {METRICS.map((key) => {
            const Icon = METRIC_ICON[key]
            const active = metric === key
            // Raw layers need the thresholds to be coloured; risk scores don't.
            const unavailable = key !== 'risk' && !scales
            return (
              <button
                key={key}
                type="button"
                role="radio"
                aria-checked={active}
                disabled={unavailable}
                title={unavailable ? 'Risk thresholds unavailable' : undefined}
                onClick={() => onMetricChange(key)}
                className={`focus-ring flex items-center gap-1 rounded-full px-2.5 py-1 text-[12.5px] font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                  active ? 'clay-sm text-ink' : 'text-muted enabled:hover:text-ink'
                }`}
              >
                <Icon size={13} strokeWidth={2} aria-hidden />
                <span className={active ? '' : 'max-[380px]:sr-only'}>{HEAT_METRIC_LABEL[key]}</span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setPlaying((p) => !p)}
          disabled={disabled}
          aria-label={playing ? 'Pause forecast animation' : 'Play forecast animation'}
          className="focus-ring clay-accent flex h-10 w-10 shrink-0 items-center justify-center rounded-full disabled:opacity-40"
        >
          {playing ? <Pause size={16} fill="currentColor" aria-hidden /> : <Play size={16} fill="currentColor" className="translate-x-px" aria-hidden />}
        </button>
        <div className="min-w-0 flex-1">
          <input
            type="range"
            min={0}
            max={max}
            step={1}
            value={hour}
            disabled={disabled}
            onChange={(e) => onHourChange(Number(e.target.value))}
            aria-label="Hours after departure"
            aria-valuetext={hours ? `${hour} hours after departure, ${formatShortDate(hours[hour])}` : undefined}
            className="range w-full"
            style={{ '--fill': fill } as React.CSSProperties}
          />
          <div className="tabular mt-0.5 hidden justify-between text-[11.5px] text-faint sm:flex" aria-hidden>
            <span>Departure</span>
            <span>12 h</span>
            <span>24 h</span>
            <span>36 h</span>
            <span>48 h</span>
          </div>
        </div>
        <div className="w-[5.5rem] shrink-0 text-right">
          <div className="tabular text-[17px] font-extrabold leading-tight text-ink">{hour === 0 ? 'Departure' : `+${hour} h`}</div>
          <div className="text-[12px] text-muted">{hours ? formatShortDate(hours[hour]) : '—'}</div>
        </div>
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          aria-expanded={expanded}
          aria-controls={`${detailsId}-top ${detailsId}-scale`}
          aria-label={expanded ? 'Hide forecast options' : 'Show forecast options'}
          className="focus-ring clay-sm flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-muted lg:hidden"
        >
          {expanded ? <ChevronDown size={17} aria-hidden /> : <ChevronUp size={17} aria-hidden />}
        </button>
      </div>

      <div id={`${detailsId}-scale`} className={`${expanded ? 'block' : 'hidden lg:block'} mt-3`}>
        <div className="h-2 rounded-full" style={{ background: SCALE }} aria-hidden />
        <div className="tabular mt-1 flex justify-between text-[11.5px] text-muted">
          {ticks.map((t) => (
            <span key={t}>{t}</span>
          ))}
        </div>
        <p className="mt-1.5 hidden text-[12px] text-faint sm:block">
          {metric === 'risk' ? 'Risk for your load at each hour of the trip window.' : `Forecast ${label.toLowerCase()} in ${raw?.unit ?? ''}.`}
        </p>
      </div>
      {hourHasNoData && !loading && (
        <p className="mt-2 flex items-center gap-1.5 text-[12.5px] font-medium text-muted">
          <CloudOff size={14} className="shrink-0" aria-hidden />
          {rateLimited ? WEATHER_LIMIT_MESSAGE : 'No forecast for this hour yet. It is beyond the 16-day forecast range.'}
        </p>
      )}
      {error && <p className="mt-2 text-[12.5px] font-medium text-danger">{error}</p>}
    </section>
  )
}
