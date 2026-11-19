import { expect, test } from 'vitest'

import { radioKeyTarget, rovingTabStop } from './roving'

test('ArrowDown and ArrowUp move one card and wrap around', () => {
  expect(radioKeyTarget('ArrowDown', 0, 3)).toBe(1)
  expect(radioKeyTarget('ArrowDown', 2, 3)).toBe(0)
  expect(radioKeyTarget('ArrowUp', 1, 3)).toBe(0)
  expect(radioKeyTarget('ArrowUp', 0, 3)).toBe(2)
})

test('Home and End jump to the first and last card', () => {
  expect(radioKeyTarget('Home', 2, 3)).toBe(0)
  expect(radioKeyTarget('End', 0, 3)).toBe(2)
})

test('other keys are left alone', () => {
  for (const key of ['Enter', ' ', 'Tab', 'a', 'ArrowLeft', 'ArrowRight']) {
    expect(radioKeyTarget(key, 1, 3)).toBeNull()
  }
  expect(radioKeyTarget('ArrowDown', 0, 0)).toBeNull()
})

test('the tab stop is the checked card, else the first', () => {
  expect(rovingTabStop(['A', 'B', 'C'], 'B')).toBe('B')
  expect(rovingTabStop(['A', 'B', 'C'], null)).toBe('A')
  expect(rovingTabStop(['A', 'B', 'C'], 'Z')).toBe('A')
  expect(rovingTabStop([], null)).toBeNull()
})
