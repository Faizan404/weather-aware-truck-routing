/**
 * Keyboard movement in a vertical radio group: ArrowDown/ArrowUp move to the
 * next/previous option (wrapping), Home/End jump to the first/last.
 * Returns the index to move to, or null for keys the group doesn't handle.
 */
export function radioKeyTarget(key: string, current: number, count: number): number | null {
  if (count <= 0) return null
  switch (key) {
    case 'ArrowDown':
      return (current + 1) % count
    case 'ArrowUp':
      return (current - 1 + count) % count
    case 'Home':
      return 0
    case 'End':
      return count - 1
    default:
      return null
  }
}

/** Roving tabindex: only one option is in the tab order, the checked one,
 *  or the first when none is checked. */
export function rovingTabStop(ids: string[], checkedId: string | null): string | null {
  if (checkedId !== null && ids.includes(checkedId)) return checkedId
  return ids[0] ?? null
}
