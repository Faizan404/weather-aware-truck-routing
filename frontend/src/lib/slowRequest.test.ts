import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { COLD_START_AFTER_MS, COLD_START_MESSAGE, slowPendingWatcher } from './slowRequest'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

test('the cold-start note appears only after 8 s of waiting', () => {
  const seen: boolean[] = []
  const watcher = slowPendingWatcher((slow) => seen.push(slow))
  watcher.update(true)
  vi.advanceTimersByTime(COLD_START_AFTER_MS - 1)
  expect(seen).toEqual([])
  vi.advanceTimersByTime(1)
  expect(seen).toEqual([true])
  expect(COLD_START_AFTER_MS).toBe(8_000)
})

test('a plan that answers in time never shows it', () => {
  const seen: boolean[] = []
  const watcher = slowPendingWatcher((slow) => seen.push(slow))
  watcher.update(true)
  vi.advanceTimersByTime(3_000)
  watcher.update(false)
  vi.advanceTimersByTime(60_000)
  expect(seen).toEqual([])
})

test('it clears when the plan arrives, and restarts for the next one', () => {
  const seen: boolean[] = []
  const watcher = slowPendingWatcher((slow) => seen.push(slow))
  watcher.update(true)
  vi.advanceTimersByTime(9_000)
  watcher.update(false)
  watcher.update(true)
  vi.advanceTimersByTime(7_000)
  expect(seen).toEqual([true, false])
  vi.advanceTimersByTime(1_000)
  expect(seen).toEqual([true, false, true])
})

test('repeated pending updates do not restart the clock', () => {
  const seen: boolean[] = []
  const watcher = slowPendingWatcher((slow) => seen.push(slow))
  watcher.update(true)
  vi.advanceTimersByTime(5_000)
  watcher.update(true) // re-render while still loading
  vi.advanceTimersByTime(3_000)
  expect(seen).toEqual([true])
})

test('dispose stops a pending timer', () => {
  const seen: boolean[] = []
  const watcher = slowPendingWatcher((slow) => seen.push(slow))
  watcher.update(true)
  watcher.dispose()
  vi.advanceTimersByTime(60_000)
  expect(seen).toEqual([])
})

test('the message names the cause and the wait', () => {
  expect(COLD_START_MESSAGE).toBe('The server is starting up — this can take up to a minute on the free plan.')
})
