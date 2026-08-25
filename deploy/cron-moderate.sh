#!/usr/bin/env bash
set -euo pipefail
STACK_DIR="${STACK_DIR:-/home/vir/stacks/yacy}"
LOG="${STACK_DIR}/deploy/cron-moderate.log"
mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1

ts() { date -u +'%Y-%m-%dT%H:%M:%SZ'; }

set -a
. "${STACK_DIR}/.env"
set +a

echo "[$(ts)] moderate-batch start"

HTTP=$(docker exec yacy-vector-service curl -sS \
  -o /tmp/moderate-result.json \
  -w "%{http_code}" \
  -m 600 \
  -X POST \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  'http://localhost:8001/admin/moderate-batch?batch_size=40' || echo "000")

case "$HTTP" in
  503) echo "[$(ts)] LLM not configured; skip"; exit 0 ;;
  200) ;;
  *)   echo "[$(ts)] moderate-batch HTTP=$HTTP; skip"; exit 0 ;;
esac

DELETED=$(python3 -c "import json; d=json.load(open('/tmp/moderate-result.json')); print(d.get('deleted',0))" 2>/dev/null || echo 0)
PROCESSED=$(python3 -c "import json; d=json.load(open('/tmp/moderate-result.json')); print(d.get('processed',0))" 2>/dev/null || echo 0)

echo "[$(ts)] processed=$PROCESSED deleted=$DELETED"

[ "$DELETED" -gt 0 ] && cat /tmp/moderate-result.json | python3 -c "
import json,sys
for r in json.load(sys.stdin).get('results',[]):
    if r.get('action')=='deleted':
        print('  BLOCKED',r['verdict'],':',r['url'])
" 2>/dev/null || true

echo "[$(ts)] moderate-batch done"
