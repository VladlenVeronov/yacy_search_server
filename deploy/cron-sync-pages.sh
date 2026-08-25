#!/usr/bin/env bash
# Periodic Solr → pgvector sync. Runs sync_pages.py inside the
# yacy-vector-service container (which already has httpx + the script
# baked in via the yacy-fork bind path). Idempotent — script keeps its
# own cursor in /app/.sync_pages.state, so missed cron runs catch up.

set -euo pipefail

STACK_DIR="${STACK_DIR:-/home/vir/stacks/yacy}"
LOG="${STACK_DIR}/deploy/cron-sync-pages.log"
mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

# Skip if a previous run is still alive (long initial sync, transient network).
if pgrep -f "sync_pages.py" >/dev/null; then
  echo "[$(ts)] previous sync_pages still running — skip"
  exit 0
fi

# Make the script visible inside the container without rebuilding the image.
SCRIPT_HOST="${STACK_DIR}/yacy-fork/docs/yacy-project/scripts/sync_pages.py"
docker cp "$SCRIPT_HOST" yacy-vector-service:/tmp/sync_pages.py >/dev/null

echo "[$(ts)] starting sync"
docker exec \
  -e YACY_SOLR_URL="http://yacy:8090/solr/collection1" \
  -e VECTOR_SERVICE_URL="http://127.0.0.1:8001" \
  yacy-vector-service python /tmp/sync_pages.py
echo "[$(ts)] sync done"
