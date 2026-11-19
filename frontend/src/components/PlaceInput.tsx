import { useQuery } from '@tanstack/react-query'
import { LoaderCircle, MapPin } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'

import { api } from '../api/client'
import { queryKeys } from '../api/queryKeys'
import type { Place } from '../api/types'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { parseLatLon } from '../lib/format'
import { Field, inputClass } from './Field'

interface Props {
  label: string
  icon: ReactNode
  value: Place | null
  onChange: (place: Place | null) => void
  placeholder?: string
  error?: string
}

/**
 * Place search with suggestions (backend proxies Photon/Nominatim, US only).
 * A place only counts once picked from the list, or typed as "lat, lon".
 */
export function PlaceInput({ label, icon, value, onChange, placeholder, error }: Props) {
  const id = useId()
  const listId = `${id}-list`
  const [text, setText] = useState(value?.label ?? '')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const query = useDebouncedValue(text.trim(), 300)
  const coords = parseLatLon(text)
  const searchable = query.length >= 3 && !coords && query !== value?.label

  const { data: results = [], isFetching, isError } = useQuery({
    queryKey: queryKeys.geocode(query),
    queryFn: ({ signal }) => api.geocode(query, signal),
    enabled: searchable,
    staleTime: 60 * 60 * 1000,
    retry: false,
  })

  const options: Place[] = coords
    ? [{ label: `${coords.lat.toFixed(5)}, ${coords.lon.toFixed(5)}`, ...coords }]
    : searchable
      ? results
      : []

  const pick = (place: Place) => {
    onChange(place)
    setText(place.label)
    setOpen(false)
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || options.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((a) => (a + 1) % options.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => (a - 1 + options.length) % options.length)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      pick(options[Math.min(active, options.length - 1)])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  const showEmpty = open && searchable && !isFetching && !isError && results.length === 0 && query === text.trim()
  const hint = showEmpty
    ? 'No US places match. Trips must start and end in the United States.'
    : open && isError
      ? 'Place search is unavailable right now. You can type “lat, lon”.'
      : undefined

  return (
    <div className="relative">
      <Field
        label={label}
        htmlFor={id}
        icon={icon}
        error={error}
        hint={hint}
        trailing={isFetching ? <LoaderCircle size={16} className="shrink-0 animate-spin text-faint" aria-label="Searching" /> : null}
      >
        <input
          id={id}
          type="text"
          autoComplete="off"
          spellCheck={false}
          role="combobox"
          aria-expanded={open && options.length > 0}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-invalid={!!error}
          aria-describedby={error ? `${id}-error` : undefined}
          value={text}
          placeholder={placeholder}
          onChange={(e) => {
            setText(e.target.value)
            setOpen(true)
            setActive(0)
            if (value) onChange(null)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={onKeyDown}
          className={inputClass}
        />
      </Field>
      {open && options.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          className="clay absolute z-30 mt-2 max-h-72 w-full overflow-auto rounded-2xl p-1.5 text-[14px]"
        >
          {options.map((place, i) => (
            <li
              key={`${place.label}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault()
                pick(place)
              }}
              onMouseEnter={() => setActive(i)}
              className={`flex cursor-pointer items-start gap-2.5 rounded-xl px-3 py-2.5 ${
                i === active ? 'clay-pressed text-ink' : 'text-ink/85'
              }`}
            >
              <MapPin size={15} strokeWidth={1.75} className="mt-0.5 shrink-0 text-faint" aria-hidden />
              <span className="min-w-0">{place.label}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
