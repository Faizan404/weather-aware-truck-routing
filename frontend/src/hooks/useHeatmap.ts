import { skipToken, useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import { api } from '../api/client'
import { queryKeys } from '../api/queryKeys'
import type { PlanResponse } from '../api/types'

/** The corridor heatmap for the plan's routes (loads after the plan). */
export function useHeatmap(plan: PlanResponse | null) {
  const body = useMemo(
    () =>
      plan && {
        polylines: plan.routes.map((r) => r.geometry),
        departure_time: plan.request.departure_time,
        load_weight_lbs: plan.request.load_weight_lbs,
      },
    [plan],
  )
  return useQuery({
    queryKey: queryKeys.heatmap(body),
    queryFn: body ? ({ signal }) => api.heatmap(body, signal) : skipToken,
    staleTime: 10 * 60 * 1000,
    retry: 1,
  })
}
