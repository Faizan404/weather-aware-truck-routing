import { CalendarClock, Flag, LoaderCircle, MapPin, Route, Weight } from 'lucide-react'
import { useState } from 'react'

import type { Place } from '../api/types'
import { defaultDeparture } from '../lib/format'
import { draftMatchesTrip, INTERVALS, type Interval, type TripInput } from '../lib/trip'
import { Field, inputClass } from './Field'
import { PlaceInput } from './PlaceInput'

export type { Interval, TripInput } from '../lib/trip'
// Cargo weight: 0 (empty trailer) up to the 80,000 lb US federal limit.
const MAX_LOAD = 80_000
const MAX_DAYS_AHEAD = 14

interface Props {
  /** The trip behind the plan on screen, if any. */
  trip: TripInput | null
  onSubmit: (trip: TripInput) => void
  /** Called when any field changes or a submit is attempted (passed only
   *  while there's an error banner to clear, so typing re-renders nothing else). */
  onEdit?: () => void
  loading: boolean
}

type Errors = Partial<Record<'origin' | 'destination' | 'departure' | 'load', string>>

function validate(origin: Place | null, destination: Place | null, departure: string, load: string): Errors {
  const errors: Errors = {}
  if (!origin) errors.origin = 'Pick an origin from the suggestions.'
  if (!destination) errors.destination = 'Pick a destination from the suggestions.'
  if (origin && destination && Math.abs(origin.lat - destination.lat) < 1e-4 && Math.abs(origin.lon - destination.lon) < 1e-4)
    errors.destination = 'Origin and destination must be different.'

  const dep = new Date(departure)
  const now = Date.now()
  if (!departure || Number.isNaN(dep.getTime())) errors.departure = 'Enter a departure date and time.'
  else if (dep.getTime() < now - 15 * 60_000) errors.departure = 'Departure cannot be in the past.'
  else if (dep.getTime() > now + MAX_DAYS_AHEAD * 86_400_000) errors.departure = `Departure must be within ${MAX_DAYS_AHEAD} days.`

  const weight = Number(load)
  if (load.trim() === '' || Number.isNaN(weight)) errors.load = 'Enter the load weight in pounds.'
  else if (weight < 0) errors.load = 'Load weight cannot be negative.'
  else if (weight > MAX_LOAD) errors.load = `Load weight must be at most ${MAX_LOAD.toLocaleString()} lb (US federal limit).`
  return errors
}

export function TripForm({ trip, onSubmit, onEdit, loading }: Props) {
  const [origin, setOrigin] = useState<Place | null>(null)
  const [destination, setDestination] = useState<Place | null>(null)
  const [departure, setDeparture] = useState(defaultDeparture)
  // Until the user edits it, the departure follows "next quarter hour" so a
  // tab left open doesn't submit a stale time.
  const [departureEdited, setDepartureEdited] = useState(false)
  const [load, setLoad] = useState('35000')
  const [intervalMiles, setIntervalMiles] = useState<Interval>(25)
  const [errors, setErrors] = useState<Errors>({})
  const [touched, setTouched] = useState(false)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    onEdit?.()
    setTouched(true)
    let dep = departure
    if (!departureEdited) {
      dep = defaultDeparture()
      setDeparture(dep)
    }
    const found = validate(origin, destination, dep, load)
    setErrors(found)
    if (Object.keys(found).length === 0 && origin && destination) {
      onSubmit({ origin, destination, departureLocal: dep, loadWeightLbs: Number(load), intervalMiles })
    }
  }

  // Re-validate as the user fixes things, once they've tried to submit.
  const revalidate = (o = origin, d = destination, dep = departure, l = load) => {
    onEdit?.()
    if (touched) setErrors(validate(o, d, dep, l))
  }

  // A new interval re-plans at once only while the form still shows the trip
  // on screen; after other edits it waits for "Find safest route".
  const changeInterval = (value: Interval) => {
    setIntervalMiles(value)
    onEdit?.()
    if (trip && value !== trip.intervalMiles && draftMatchesTrip({ origin, destination, departureLocal: departure, load }, trip)) {
      onSubmit({ ...trip, intervalMiles: value })
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate aria-label="Plan a trip">
      <div className="grid gap-4 @2xl:grid-cols-2">
      <PlaceInput
        label="From"
        icon={<MapPin size={17} strokeWidth={1.9} />}
        value={origin}
        placeholder="US city, address or lat, lon"
        error={errors.origin}
        onChange={(p) => {
          setOrigin(p)
          revalidate(p)
        }}
      />
      <PlaceInput
        label="To"
        icon={<Flag size={17} strokeWidth={1.9} />}
        value={destination}
        placeholder="US city, address or lat, lon"
        error={errors.destination}
        onChange={(p) => {
          setDestination(p)
          revalidate(origin, p)
        }}
      />
      </div>

      <div className="grid grid-cols-1 gap-4 @sm:grid-cols-[1.35fr_1fr]">
        <Field label="Departure" htmlFor="departure" icon={<CalendarClock size={17} strokeWidth={1.9} />} error={errors.departure}>
          <input
            id="departure"
            type="datetime-local"
            value={departure}
            onChange={(e) => {
              setDeparture(e.target.value)
              setDepartureEdited(true)
              revalidate(origin, destination, e.target.value)
            }}
            aria-invalid={!!errors.departure}
            aria-describedby={errors.departure ? 'departure-error' : undefined}
            className={`${inputClass} text-[14px] [color-scheme:inherit]`}
          />
        </Field>
        <Field
          label="Load weight"
          htmlFor="load"
          icon={<Weight size={17} strokeWidth={1.9} />}
          error={errors.load}
          trailing={<span className="shrink-0 text-[13px] font-semibold text-faint">lb</span>}
        >
          <input
            id="load"
            type="number"
            inputMode="numeric"
            min={0}
            max={MAX_LOAD}
            step={500}
            value={load}
            onChange={(e) => {
              setLoad(e.target.value)
              revalidate(origin, destination, departure, e.target.value)
            }}
            aria-invalid={!!errors.load}
            aria-describedby={errors.load ? 'load-error' : undefined}
            className={`${inputClass} tabular`}
          />
        </Field>
      </div>

      <div>
        <span id="interval-label" className="mb-1.5 block text-[13px] font-semibold text-muted">
          Check the weather every
        </span>
        <div className="clay-pressed grid grid-cols-3 gap-1 rounded-2xl p-1.5" role="radiogroup" aria-labelledby="interval-label">
          {INTERVALS.map((value) => {
            const selected = intervalMiles === value
            return (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => changeInterval(value)}
                className={`focus-ring tabular h-9 rounded-xl text-[14px] font-semibold transition-colors ${
                  selected ? 'clay-sm text-ink' : 'text-muted hover:text-ink'
                }`}
              >
                {value} mi
              </button>
            )
          })}
        </div>
      </div>

      <button
        type="submit"
        // Stays enabled while loading: a new submit replaces (and cancels) the
        // request in flight, so edits made during a refresh are never dropped.
        aria-busy={loading}
        className="focus-ring clay-accent flex h-12 w-full items-center justify-center gap-2 rounded-2xl text-[15px] font-bold transition-transform active:translate-y-px"
      >
        {loading ? <LoaderCircle size={18} className="animate-spin" aria-hidden /> : <Route size={18} strokeWidth={2} aria-hidden />}
        {loading ? 'Finding the safest route…' : 'Find safest route'}
      </button>
    </form>
  )
}
