/** After this long, a pending plan is probably waiting for the free-plan
 *  server to wake up, so the UI says so. */
export const COLD_START_AFTER_MS = 8_000
export const COLD_START_MESSAGE = 'The server is starting up — this can take up to a minute on the free plan.'

/**
 * Calls onSlow(true) once `pending` has lasted `afterMs`, and onSlow(false)
 * when it ends. update(pending) is called whenever the pending state changes.
 */
export function slowPendingWatcher(onSlow: (slow: boolean) => void, afterMs = COLD_START_AFTER_MS) {
  let timer: ReturnType<typeof setTimeout> | null = null
  let slow = false
  const set = (value: boolean) => {
    if (value !== slow) {
      slow = value
      onSlow(value)
    }
  }
  return {
    update(pending: boolean) {
      if (pending && timer === null && !slow) {
        timer = setTimeout(() => {
          timer = null
          set(true)
        }, afterMs)
      } else if (!pending) {
        if (timer !== null) clearTimeout(timer)
        timer = null
        set(false)
      }
    },
    dispose() {
      if (timer !== null) clearTimeout(timer)
      timer = null
    },
  }
}
