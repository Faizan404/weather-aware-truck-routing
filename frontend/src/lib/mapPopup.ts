/** HTML for a checkpoint's map popup (MapLibre renders it outside React). */
import type { Checkpoint, RouteOption } from '../api/types'
import { formatDateTime, formatValue } from './format'
import { RISK_LABEL, RISK_TEXT, riskVar } from './risk'

export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
}

export function popupHtml(route: RouteOption, cp: Checkpoint): string {
  const row = (label: string, value: string, level: Checkpoint['level']) =>
    `<tr><td>${label}</td><td>${value}</td><td><span class="dot" style="background:${riskVar(level)}" title="${RISK_LABEL[level]}"></span></td></tr>`
  const reasons = cp.reasons.length
    ? `<ul class="reasons">${cp.reasons.map((r) => `<li>${escapeHtml(r)}</li>`).join('')}</ul>`
    : ''
  return `
    <div class="cp-popup">
      <div class="cp-head">
        <span class="cp-title">${escapeHtml(route.label)}, mile ${cp.mile.toFixed(0)}</span>
        <span class="chip" style="background:${riskVar(cp.level)};color:${RISK_TEXT[cp.level]}">${RISK_LABEL[cp.level]}</span>
      </div>
      <div class="cp-eta">Arrives ${escapeHtml(formatDateTime(cp.eta))}</div>
      <table>
        ${row('Wind', formatValue(cp.wind_mph, 'mph', 1), cp.wind_level)}
        ${row('Rain', formatValue(cp.rain_in_hr, 'in/hr', 2), cp.rain_level)}
        ${row('Snow', formatValue(cp.snow_in_hr, 'in/hr', 2), cp.snow_level)}
      </table>
      ${reasons}
    </div>`
}
