#!/usr/bin/env bash
# Auto-deploy: pull the latest fork commit on the configured branch,
# rebuild only the services whose code changed, then bring the stack up.
# Designed to be run from cron (every 5 min, say) or a webhook.
#
# Idempotent: if HEAD didn't move, exits early. Logs to deploy/auto-deploy.log
# in the stack dir so you can `tail -f` it.

set -euo pipefail

STACK_DIR="${STACK_DIR:-/home/vir/stacks/yacy}"
FORK_DIR="${STACK_DIR}/yacy-fork"
BRANCH="${BRANCH:-master}"
LOG="${STACK_DIR}/deploy/auto-deploy.log"
LAST_SHA_FILE="${STACK_DIR}/deploy/.last-sha"

mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*"; }

cd "$FORK_DIR"
git fetch origin "$BRANCH" --quiet
local_sha=$(git rev-parse HEAD)
remote_sha=$(git rev-parse "origin/${BRANCH}")

if [[ "$local_sha" == "$remote_sha" ]]; then
  log "no-op: HEAD already at ${remote_sha:0:7}"
  exit 0
fi

log "deploying ${local_sha:0:7} → ${remote_sha:0:7}"

# Find which services need rebuild based on which paths changed.
changed=$(git diff --name-only "$local_sha" "$remote_sha")
need_yacy=0
need_vector=0
echo "$changed" | grep -qE '^(htroot/|source/|defaults/|build\.xml|docker/Dockerfile)' && need_yacy=1 || true
echo "$changed" | grep -qE '^vector_service/'                                              && need_vector=1 || true

git reset --hard "$remote_sha" --quiet
log "checked out $(git rev-parse --short HEAD): $(git log -1 --format=%s)"

cd "$STACK_DIR"

services=()
[[ $need_yacy   -eq 1 ]] && services+=(yacy)
[[ $need_vector -eq 1 ]] && services+=(yacy-vector-service)

if [[ ${#services[@]} -eq 0 ]]; then
  log "no buildable code changed; only restarting compose"
else
  log "building: ${services[*]}"
  docker compose build "${services[@]}"
fi

# Re-apply schema (idempotent CREATE IF NOT EXISTS).
if docker compose ps yacy-pgvector --format '{{.Name}}' | grep -q .; then
  log "applying schema"
  docker compose exec -T yacy-pgvector psql -U "${POSTGRES_USER:-yacy}" -d "${POSTGRES_DB:-yacy_pages}" \
    < "${FORK_DIR}/vector_service/schema.sql" >/dev/null
fi

log "compose up -d"
docker compose up -d

echo "$remote_sha" > "$LAST_SHA_FILE"
log "deploy complete: ${remote_sha:0:7}"
