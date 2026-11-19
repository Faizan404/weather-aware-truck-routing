import { useCallback, useMemo, useState } from 'react'

import type { CheckpointRef } from '../components/MapView'
import type { HeatMetric } from '../lib/geojson'
import { WEATHER_LIMIT_MESSAGE } from '../lib/messages'
import { heatScales as buildHeatScales } from '../lib/riskRules'
import { showPlanError, type TripInput } from '../lib/trip'
import { tripKeyOf } from '../lib/tripScope'
import { useHeatmap } from './useHeatmap'
import { usePlan } from './usePlan'
import { useRiskRules } from './useRiskRules'
import { useSlowPending } from './useSlowPending'
import { useTripScopedState } from './useTripScopedState'

/**
 * Everything about the trip on screen: the submitted trip, its plan and
 * heatmap, the risk rules, which route and forecast hour are shown, and the
 * error banner. App only lays this out.
 */
export function useTripPlan() {
  const [trip, setTrip] = useState<TripInput | null>(null)
  // Time of the last form edit or submit; older server errors stay hidden.
  const [errorHiddenAt, setErrorHiddenAt] = useState(0)
  const [hovered, setHovered] = useState<CheckpointRef | null>(null)
  const [heatMetric, setHeatMetric] = useState<HeatMetric>('risk')
  const [showHeatmap, setShowHeatmap] = useState(true)

  // Thresholds come from the backend once; the legend and heatmap scales are
  // built from them. Without them, only the risk layer can be drawn.
  const rules = useRiskRules().data ?? null
  const heatScales = useMemo(() => (rules ? buildHeatScales(rules) : null), [rules])

  const { query: planQuery, plan, isCurrent } = usePlan(trip)
  const heatQuery = useHeatmap(plan)
  // The free-plan server sleeps when idle; say so if a plan takes a while.
  const isSlow = useSlowPending(planQuery.isFetching)

  // A new trip starts on its recommended route at the departure hour; changing
  // only the interval keeps both.
  const tripKey = tripKeyOf(plan)
  const [selectedRouteId, selectRoute] = useTripScopedState<string | null>(tripKey, plan?.recommendation.route_id ?? null)
  const [heatHour, setHeatHour] = useTripScopedState(tripKey, 0)

  // Re-submitting the same trip (e.g. "try again" after an error) must re-run
  // the request; an identical query key alone wouldn't refetch.
  const refetchPlan = planQuery.refetch
  const submit = useCallback(
    (next: TripInput) => {
      setErrorHiddenAt(Date.now())
      if (trip && JSON.stringify(trip) === JSON.stringify(next)) void refetchPlan()
      else setTrip(next)
    },
    [trip, refetchPlan],
  )
  const hideError = useCallback(() => setErrorHiddenAt(Date.now()), [])
  const onHover = useCallback((ref: CheckpointRef | null) => setHovered(ref), [])

  const warnings = [...new Set([...(plan?.warnings ?? []), ...(heatQuery.data?.warnings ?? [])])]
  const heat = heatQuery.data ?? null

  return {
    trip,
    submit,
    plan,
    planQuery,
    isCurrent,
    isLoading: planQuery.isFetching,
    isSlow,
    error: showPlanError(planQuery, errorHiddenAt) ? planQuery.error : null,
    hideError,
    warnings,
    rules,
    selectedRouteId,
    selectRoute,
    hovered,
    onHover,
    heatmap: {
      data: heat,
      loading: heatQuery.isFetching,
      error: heatQuery.isError ? heatQuery.error : null,
      rateLimited: !!heat?.warnings.includes(WEATHER_LIMIT_MESSAGE),
      scales: heatScales,
      metric: (heatScales ? heatMetric : 'risk') as HeatMetric,
      setMetric: setHeatMetric,
      hour: heatHour,
      setHour: setHeatHour,
      visible: showHeatmap,
      setVisible: setShowHeatmap,
      hourHasNoData: !!heat && heat.risk.length > 0 && heat.risk.every((row) => row[heatHour] === null),
    },
  }
}

export type TripPlan = ReturnType<typeof useTripPlan>
