#!/usr/bin/env bash
# Post-deploy smoke test. Run after every deploy:
#
#   scripts/smoke.sh https://your-api.onrender.com https://your-app.vercel.app
#
# Checks health, risk rules, place search, one small plan (Dallas -> Houston,
# every 50 mi) and its heatmap, and a CORS preflight from the app's origin.
# Exits non-zero on the first failure. Needs curl and python3.
# The first call may take up to a minute while a sleeping free-plan server starts.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <API_URL> <APP_URL>   e.g. $0 https://your-api.onrender.com https://your-app.vercel.app" >&2
  exit 2
fi
API="${1%/}/api/v1"
APP="${2%/}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass() { printf '  \033[32mok\033[0m   %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1" >&2; [[ -n "${2:-}" ]] && printf '%s\n' "$2" | head -c 600 >&2 && echo >&2; exit 1; }

# request METHOD PATH [JSON_BODY] -> writes body to $TMP/body, prints status
request() {
  local method="$1" path="$2" body="${3:-}"
  local args=(-sS -o "$TMP/body" -w '%{http_code}' --max-time 120 -X "$method" "$API$path")
  [[ -n "$body" ]] && args+=(-H 'Content-Type: application/json' --data "$body")
  curl "${args[@]}" || echo "000"
}

# check NAME PYTHON_EXPR: evaluates EXPR with `d` = parsed JSON body
check() {
  python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if ($2) else 1)" "$TMP/body" 2>/dev/null \
    || fail "$1" "$(cat "$TMP/body")"
}

echo "Smoke test: API $API, app $APP"

status=$(request GET /health/)
[[ "$status" == 200 ]] || fail "GET /health/ returned $status" "$(cat "$TMP/body")"
check "health payload" "d['status'] == 'ok' and 'version' in d and d['weather_budget_minute_left'] >= 0"
pass "health ($(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print('version', d['version'], '- weather budget', d['weather_budget_minute_left'])" "$TMP/body"))"

status=$(request GET /risk-rules/)
[[ "$status" == 200 ]] || fail "GET /risk-rules/ returned $status" "$(cat "$TMP/body")"
check "risk rules" "len(d['levels']) == 6 and set(d['conditions']) == {'wind', 'rain', 'snow'} and len(d['load_rules']) == 3"
pass "risk rules"

status=$(request GET "/geocode/?q=Chicago")
[[ "$status" == 200 ]] || fail "GET /geocode/?q=Chicago returned $status" "$(cat "$TMP/body")"
check "geocode results" "any('Chicago' in r['label'] for r in d['results'])"
pass "geocode"

departure=$(python3 -c "from datetime import datetime, timedelta, UTC; print((datetime.now(UTC) + timedelta(hours=1)).isoformat())")
plan_body=$(cat <<JSON
{"origin": {"label": "Dallas, TX", "lat": 32.7767, "lon": -96.797},
 "destination": {"label": "Houston, TX", "lat": 29.7604, "lon": -95.3698},
 "departure_time": "$departure", "load_weight_lbs": 35000, "interval_miles": 50}
JSON
)
status=$(request POST /plan/ "$plan_body")
[[ "$status" == 200 ]] || fail "POST /plan/ returned $status" "$(cat "$TMP/body")"
check "plan payload" "1 <= len(d['routes']) <= 3 and d['recommendation']['route_id'] in [r['id'] for r in d['routes']] and all(r['checkpoints'] for r in d['routes'])"
pass "plan Dallas -> Houston ($(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(len(d['routes']), 'routes, recommends', d['recommendation']['route_id'])" "$TMP/body"))"

heat_body=$(python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
print(json.dumps({'polylines': [r['geometry'] for r in d['routes']],
                  'departure_time': d['request']['departure_time'],
                  'load_weight_lbs': d['request']['load_weight_lbs']}))" "$TMP/body")
status=$(request POST /heatmap/ "$heat_body")
[[ "$status" == 200 ]] || fail "POST /heatmap/ returned $status" "$(cat "$TMP/body")"
check "heatmap payload" "len(d['hours']) == 49 and len(d['points']) > 0 and len(d['risk']) == len(d['points'])"
pass "heatmap ($(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(len(d['points']), 'cells')" "$TMP/body"))"

headers=$(curl -sS -o /dev/null -D - --max-time 30 -X OPTIONS "$API/plan/" \
  -H "Origin: $APP" -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: content-type' || true)
allow=$(printf '%s' "$headers" | tr -d '\r' | awk -F': ' 'tolower($1) == "access-control-allow-origin" {print $2}')
[[ "$allow" == "$APP" ]] || fail "CORS preflight from $APP not allowed (Access-Control-Allow-Origin: '${allow:-none}'); check CORS_ALLOWED_ORIGINS" "$headers"
pass "CORS preflight from $APP"

echo "All smoke checks passed."
