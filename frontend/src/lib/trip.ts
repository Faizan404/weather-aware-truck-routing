import type { Place, PlanRequest } from '../api/types'

export type Interval = 10 | 25 | 50
export const INTERVALS: Interval[] = [10, 25, 50]

/** A submitted trip: what the plan on screen was made from. */
export interface TripInput {
  origin: Place
  destination: Place
  departureLocal: string // value of the datetime-local input
  loadWeightLbs: number
  intervalMiles: Interval
}

export function toPlanRequest(trip: TripInput): PlanRequest {
  return {
    origin: trip.origin,
    destination: trip.destination,
    departure_time: new Date(trip.departureLocal).toISOString(),
    load_weight_lbs: trip.loadWeightLbs,
    interval_miles: trip.intervalMiles,
  }
}

/** The form's current, possibly unsubmitted, values (interval aside). */
export interface TripDraft {
  origin: Place | null
  destination: Place | null
  departureLocal: string
  load: string // raw text of the load input
}

function samePlace(a: Place | null, b: Place): boolean {
  return !!a && a.lat === b.lat && a.lon === b.lon && a.label === b.label
}

/**
 * Whether the form still describes the trip on screen (ignoring the
 * interval). Only then does switching the interval re-plan straight away;
 * otherwise the new interval waits for the next submit.
 */
export function draftMatchesTrip(draft: TripDraft, trip: TripInput | null): boolean {
  if (!trip) return false
  const load = draft.load.trim()
  return (
    samePlace(draft.origin, trip.origin) &&
    samePlace(draft.destination, trip.destination) &&
    draft.departureLocal === trip.departureLocal &&
    load !== '' &&
    Number(load) === trip.loadWeightLbs
  )
}

export interface PlanErrorState {
  isError: boolean
  isFetching: boolean
  errorUpdatedAt: number
}

/**
 * The server error banner shows only for an error newer than the last form
 * edit or submit (`hiddenAt`), and never while a new request is running.
 */
export function showPlanError({ isError, isFetching, errorUpdatedAt }: PlanErrorState, hiddenAt: number): boolean {
  return isError && !isFetching && errorUpdatedAt >= hiddenAt
}
