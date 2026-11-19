import type { HeatmapBody } from './queryKeys'
import type { ApiErrorBody, HeatmapResponse, Place, PlanRequest, PlanResponse, RiskRules } from './types'

const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? '/api/v1'

export class ApiError extends Error {
  code: string
  status: number
  details: Record<string, unknown>

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }

  /** First field-level message, flattened, for showing next to the form. */
  fieldMessages(): string[] {
    const out: string[] = []
    const walk = (value: unknown, path: string) => {
      if (typeof value === 'string')
        // Skip the field prefix when the message already names the field.
        out.push(path && !value.toLowerCase().includes(path.toLowerCase()) ? `${path}: ${value}` : value)
      else if (Array.isArray(value)) value.forEach((v) => walk(v, path))
      else if (value && typeof value === 'object')
        Object.entries(value).forEach(([k, v]) => walk(v, k === 'non_field_errors' ? path : k))
    }
    walk(this.details, '')
    return out
  }
}

/** Per-call time limits. Plan and heatmap can wait out a cold start on the
 *  free plan (up to about a minute) plus the server's own 60 s budget. */
export const TIMEOUT_MS = { plan: 90_000, heatmap: 90_000, geocode: 10_000, riskRules: 10_000 } as const

export const TIMEOUT_MESSAGE = 'The server took too long to respond. Please try again.'

interface RequestOptions {
  method?: 'GET' | 'POST'
  body?: unknown
  signal?: AbortSignal
  timeoutMs: number
}

async function request<T>(path: string, { method = 'GET', body, signal, timeoutMs }: RequestOptions): Promise<T> {
  const timeout = AbortSignal.timeout(timeoutMs)
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout
  let response: Response
  let parsed: unknown
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      // Content-Type only with a body: a plain GET then needs no CORS preflight.
      ...(body === undefined ? {} : { body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } }),
      signal: combined,
    })
    parsed = await response.json().catch((err: unknown) => {
      if (combined.aborted) throw err
      return null
    })
  } catch (err) {
    if (signal?.aborted) throw err // cancelled by the caller (newer request)
    if (timeout.aborted) throw new ApiError(0, 'timeout', TIMEOUT_MESSAGE)
    throw new ApiError(0, 'network_error', 'Cannot reach the server. Check your connection.')
  }
  if (!response.ok) {
    const e = (parsed as ApiErrorBody | null)?.error
    if (e?.code === 'throttled') {
      const wait = Number(response.headers.get('Retry-After'))
      const when = wait > 0 ? `in ${wait} second${wait === 1 ? '' : 's'}` : 'in a minute'
      throw new ApiError(429, e.code, `Too many requests. Try again ${when}.`)
    }
    if (e) throw new ApiError(response.status, e.code, e.message, e.details ?? {})
    // No API error body: a proxy/gateway or a crashed server answered.
    const message =
      response.status >= 500
        ? 'The server is unavailable right now. Please try again in a moment.'
        : `Request failed (${response.status}).`
    throw new ApiError(response.status, 'http_error', message)
  }
  return parsed as T
}

export const api = {
  riskRules: (signal?: AbortSignal) => request<RiskRules>('/risk-rules/', { signal, timeoutMs: TIMEOUT_MS.riskRules }),

  geocode: (q: string, signal?: AbortSignal) =>
    request<{ results: Place[] }>(`/geocode/?q=${encodeURIComponent(q)}`, { signal, timeoutMs: TIMEOUT_MS.geocode }).then(
      (r) => r.results,
    ),

  plan: (body: PlanRequest, signal?: AbortSignal) =>
    request<PlanResponse>('/plan/', { method: 'POST', body, signal, timeoutMs: TIMEOUT_MS.plan }),

  heatmap: (body: HeatmapBody, signal?: AbortSignal) =>
    request<HeatmapResponse>('/heatmap/', { method: 'POST', body, signal, timeoutMs: TIMEOUT_MS.heatmap }),
}
