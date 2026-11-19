import { useEffect, useRef, useState } from 'react'

import { COLD_START_AFTER_MS, slowPendingWatcher } from '../lib/slowRequest'

/** True once `pending` has lasted longer than `afterMs`. */
export function useSlowPending(pending: boolean, afterMs = COLD_START_AFTER_MS): boolean {
  const [slow, setSlow] = useState(false)
  const watcher = useRef<ReturnType<typeof slowPendingWatcher> | null>(null)
  useEffect(() => {
    const w = slowPendingWatcher(setSlow, afterMs)
    watcher.current = w
    return () => w.dispose()
  }, [afterMs])
  useEffect(() => {
    watcher.current?.update(pending)
  }, [pending])
  return pending && slow
}
