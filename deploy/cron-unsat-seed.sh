#!/usr/bin/env bash
set -euo pipefail
STACK_DIR="${STACK_DIR:-/home/vir/stacks/yacy}"
LOG="${STACK_DIR}/deploy/cron-unsat-seed.log"
mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1
ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

set -a
. "${STACK_DIR}/.env"
set +a

if [[ -z "${ADMIN_TOKEN:-}" || -z "${YACY_ADMIN_USER:-}" || -z "${YACY_ADMIN_PASS:-}" ]]; then
  echo "[$(ts)] missing ADMIN_TOKEN / YACY_ADMIN_USER / YACY_ADMIN_PASS in .env; skip"
  exit 0
fi

# Call gap-analyzer directly via container network — bypasses traefik.
HTTP=$(docker exec yacy-vector-service curl -sS -o /tmp/unsat-plan.json -w "%{http_code}" -m 60 \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  "http://127.0.0.1:8001/unsatisfied/seed?limit_queries=10&hours=168" || echo "000")

case "$HTTP" in
  503) echo "[$(ts)] LLM not configured (LLM_API_URL empty); skip"; exit 0 ;;
  200) ;;
  *)   echo "[$(ts)] gap-analyzer HTTP=$HTTP; skip"; exit 0 ;;
esac

ACCEPTED=$(python3 - <<PY
import json
try:
    d = json.load(open("/tmp/unsat-plan.json"))
    if not isinstance(d, list):
        print(0); raise SystemExit
    print(sum(len(x.get("accepted", [])) for x in d))
except Exception:
    print(0)
PY
)
echo "[$(ts)] accepted URLs from LLM: $ACCEPTED"
[[ "$ACCEPTED" -eq 0 ]] && exit 0

YACY_ADMIN_USER="$YACY_ADMIN_USER" YACY_ADMIN_PASS="$YACY_ADMIN_PASS" python3 - <<PY
import json, os, subprocess, urllib.parse
plan = json.load(open("/tmp/unsat-plan.json"))
user = os.environ["YACY_ADMIN_USER"]; pw = os.environ["YACY_ADMIN_PASS"]
for q in plan if isinstance(plan, list) else []:
    for url in q.get("accepted", []):
        host = urllib.parse.urlparse(url).hostname or url
        kv = [
            ("crawlingMode","url"),("crawlingURL",url),
            ("bookmarkTitle",f"ai-seed-{host}"),
            ("crawlingDepth","2"),("directDocByURL","on"),
            ("range","domain"),("mustmatch",".*"),("ipMustmatch",".*"),
            ("deleteold","off"),("recrawl","nodoubles"),
            ("storeHTCache","on"),("cachePolicy","iffresh"),
            ("indexText","on"),("indexMedia","off"),
            ("agentName","YaCy Internet (cautious)"),
            ("collection","ai-gap"),("crawlingstart","Start_New_Crawl"),
        ]
        data = "&".join(f"{k}={urllib.parse.quote(str(v), safe=chr(0))}" for k,v in kv)
        rc = subprocess.call([
            "curl","-s","-o","/dev/null","-w","%{http_code}\n",
            "--http1.1","--digest","-u",f"{user}:{pw}",
            "-X","POST","https://search.newsgroup.site/Crawler_p.html",
            "-d",data,
        ])
        print(f"  ai-seed: {url}  → curl rc={rc}")
PY
echo "[$(ts)] cron-unsat-seed done"
