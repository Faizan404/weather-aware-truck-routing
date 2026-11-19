import { useQuery } from '@tanstack/react-query'

import { api } from '../api/client'
import { queryKeys } from '../api/queryKeys'

/** The risk thresholds, fetched once per session (they only change with a deploy). */
export function useRiskRules() {
  return useQuery({
    queryKey: queryKeys.riskRules,
    queryFn: ({ signal }) => api.riskRules(signal),
    staleTime: Infinity,
    gcTime: Infinity,
    retry: 1,
  })
}
