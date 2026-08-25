#!/usr/bin/env bash
# Load test ramp for YaCy on Hetzner.
# Stages 10 → 50 → 100 → 200 → 500 → 1000 concurrent.
# 30s per stage, 1m cool-down between.
# Aborts when a stage's 5xx rate exceeds ABORT_5XX_PCT (default 5%).
#
# Targets the yacy container directly via its bridge IP (bypass traefik
# and Cloudflare) so we measure the engine, not the edge.
#
# Usage (from Hetzner host):
#   bash load-test.sh [stage1 [stage2 ...]]
#   bash load-test.sh 10 50 100        # only run first three stages

set -euo pipefail

HOST_IP="${HOST_IP:-172.18.0.20}"
PORT="${PORT:-8090}"
DURATION="${DURATION:-30s}"
COOLDOWN="${COOLDOWN:-60}"
THREADS="${THREADS:-8}"
ABORT_5XX_PCT="${ABORT_5XX_PCT:-5}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LUA="${SCRIPT_DIR}/load-test-queries.lua"
OUT_DIR="${SCRIPT_DIR}/../load-test-results"
mkdir -p "$OUT_DIR"
TS="$(date -u +%Y%m%d-%H%M%SZ)"
SUMMARY="${OUT_DIR}/${TS}-summary.txt"

if ! command -v wrk >/dev/null 2>&1; then
  echo "wrk not installed (apt install wrk)" >&2
  exit 1
fi
if [[ ! -f "$LUA" ]]; then
  echo "missing $LUA" >&2
  exit 1
fi

stages=("$@")
if [[ ${#stages[@]} -eq 0 ]]; then
  stages=(10 50 100 200 500 1000)
fi

echo "=== YaCy load test ramp ===" | tee -a "$SUMMARY"
echo "target:    http://${HOST_IP}:${PORT}/" | tee -a "$SUMMARY"
echo "duration:  ${DURATION} per stage, ${COOLDOWN}s cool-down" | tee -a "$SUMMARY"
echo "threads:   ${THREADS}" | tee -a "$SUMMARY"
echo "stages:    ${stages[*]}" | tee -a "$SUMMARY"
echo "abort >${ABORT_5XX_PCT}% 5xx" | tee -a "$SUMMARY"
echo | tee -a "$SUMMARY"

for c in "${stages[@]}"; do
  out="${OUT_DIR}/${TS}-c${c}.log"
  echo "=== stage c=${c} ($(date -u +%H:%M:%SZ) UTC) ===" | tee -a "$SUMMARY"

  # docker stats sample BEFORE
  docker stats --no-stream --format \
    "  pre  {{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}" \
    yacy yacy-vector-service yacy-pgvector yacy-redis 2>/dev/null \
    | tee -a "$SUMMARY" || true

  wrk -t"$THREADS" -c"$c" -d"$DURATION" --latency \
      -s "$LUA" "http://${HOST_IP}:${PORT}" > "$out" 2>&1 || {
    echo "  wrk exited non-zero — see $out" | tee -a "$SUMMARY"
  }

  # parse
  reqs=$(grep -E "Requests/sec" "$out" | awk '{print $NF}')
  total=$(grep -E "[0-9]+ requests in" "$out" | awk '{print $1}')
  p50=$(grep -E "^p50:" "$out" | awk '{print $2}')
  p95=$(grep -E "^p95:" "$out" | awk '{print $2}')
  p99=$(grep -E "^p99:" "$out" | awk '{print $2}')
  e5xx=$(grep -E "^5xx errors:" "$out" | awk '{print $3}')
  e4xx=$(grep -E "^4xx errors:" "$out" | awk '{print $3}')
  socket_err=$(grep -E "Socket errors" "$out" || true)

  : "${total:=0}"; : "${e5xx:=0}"
  pct_5xx=$(awk -v e="$e5xx" -v t="$total" 'BEGIN{ if(t==0) print 0; else printf "%.2f", e*100/t }')

  printf "  rps=%s total=%s p50=%sms p95=%sms p99=%sms 4xx=%s 5xx=%s (%s%%)\n" \
    "$reqs" "$total" "$p50" "$p95" "$p99" "$e4xx" "$e5xx" "$pct_5xx" \
    | tee -a "$SUMMARY"
  [[ -n "$socket_err" ]] && echo "  $socket_err" | tee -a "$SUMMARY"

  # docker stats sample AFTER
  docker stats --no-stream --format \
    "  post {{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}" \
    yacy yacy-vector-service yacy-pgvector yacy-redis 2>/dev/null \
    | tee -a "$SUMMARY" || true

  # abort check
  if awk -v pct="$pct_5xx" -v thr="$ABORT_5XX_PCT" 'BEGIN{exit !(pct+0 > thr+0)}'; then
    echo "  ABORT: 5xx rate ${pct_5xx}% exceeds threshold ${ABORT_5XX_PCT}%" | tee -a "$SUMMARY"
    break
  fi

  echo | tee -a "$SUMMARY"
  if [[ "$c" != "${stages[-1]}" ]]; then
    echo "  cooldown ${COOLDOWN}s..." | tee -a "$SUMMARY"
    sleep "$COOLDOWN"
  fi
done

echo "summary: $SUMMARY"
