import { keepPreviousData, skipToken, useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import { api } from '../api/client'
import { queryKeys } from '../api/queryKeys'
import { toPlanRequest, type TripInput } from '../lib/trip'

/** The plan for the submitted trip. Re-submitting cancels the request in
 *  flight; switching the interval back is served from cache. */
export function usePlan(trip: TripInput | null) {
  const request = useMemo(() => (trip ? toPlanRequest(trip) : null), [trip])
  const query = useQuery({
    queryKey: queryKeys.plan(request),
    queryFn: request ? ({ signal }) => api.plan(request, signal) : skipToken,
    staleTime: 10 * 60 * 1000,
    retry: false,
    placeholderData: keepPreviousData,
  })
  const plan = query.data ?? null
  // While a new plan loads, the previous one stays on screen (faded).
  return { query, plan, isCurrent: !!plan && !query.isPlaceholderData }
}
