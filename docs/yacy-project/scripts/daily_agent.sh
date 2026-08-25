#!/bin/bash
# YACY Daily Agent — запускається щодня о 4:00
# Читає PLAN.md, виконує наступний крок, звітує в Telegram
#
# Встановити крон: bash scripts/setup_cron.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$SCRIPT_DIR/daily_agent.log"
PLAN_FILE="$PROJECT_DIR/PLAN.md"
LOCK_FILE="/tmp/yacy_daily_agent.lock"

# ── Env ──────────────────────────────────────────────────────────────────────
source "$HOME/.yacy_env" 2>/dev/null || true
source "$HOME/.yacy_telegram.env" 2>/dev/null || true

TG_BOT_TOKEN="${TG_BOT_TOKEN:-}"
TG_CHAT_ID="${TG_CHAT_ID:-}"
DATE=$(date '+%Y-%m-%d %H:%M')

# ── Helpers ───────────────────────────────────────────────────────────────────

log() { echo "[$DATE] $*" | tee -a "$LOG_FILE"; }

tg_send() {
    local msg="$1"
    if [ -z "$TG_BOT_TOKEN" ] || [ -z "$TG_CHAT_ID" ]; then
        log "[TG] Not configured — skipping Telegram message"
        return
    fi
    curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
        -d chat_id="$TG_CHAT_ID" \
        -d parse_mode="Markdown" \
        --data-urlencode text="$msg" \
        -o /dev/null
}

tg_report() {
    local status="$1"
    local details="$2"
    tg_send "🤖 *YACY Daily Agent* — $DATE
Status: $status
$details"
}

# ── Lock (prevent double run) ─────────────────────────────────────────────────
if [ -f "$LOCK_FILE" ]; then
    log "Already running (lock exists). Exiting."
    exit 0
fi
touch "$LOCK_FILE"
trap "rm -f '$LOCK_FILE'" EXIT

# ── Check plan ────────────────────────────────────────────────────────────────
if [ ! -f "$PLAN_FILE" ]; then
    tg_report "⚠️ Немає плану" "Файл PLAN.md не знайдено. Заповни VISION.md і скажи мені."
    log "PLAN.md not found"
    exit 0
fi

# Find next TODO step in PLAN.md
NEXT_STEP=$(grep -n '^\- \[ \]' "$PLAN_FILE" | head -1)
STEP_LINE=$(echo "$NEXT_STEP" | cut -d: -f1)
STEP_TEXT=$(echo "$NEXT_STEP" | sed 's/^[0-9]*:- \[ \] //')

if [ -z "$NEXT_STEP" ]; then
    tg_report "✅ Всі кроки виконані!" "PLAN.md: більше немає завдань.\nПора оновити VISION.md!"
    log "All steps done"
    exit 0
fi

log "Next step [line $STEP_LINE]: $STEP_TEXT"
tg_send "🌅 *YACY Daily — $DATE*
📋 Наступний крок:
\`$STEP_TEXT\`
Починаю виконання..."

# ── Execute step via Claude Code ──────────────────────────────────────────────
STEP_RESULT_FILE="/tmp/yacy_step_result_$$.md"

# Run Claude with the step as a task
CLAUDE_BIN="$(which claude 2>/dev/null || echo '/usr/local/bin/claude')"

if [ ! -x "$CLAUDE_BIN" ]; then
    log "Claude CLI not found at $CLAUDE_BIN"
    tg_report "❌ Помилка" "Claude CLI не знайдено. Виконай вручну:\n\`$STEP_TEXT\`"
    exit 1
fi

cd "$PROJECT_DIR/yacy_search_server"

# Execute step non-interactively
STEP_OUTPUT=$("$CLAUDE_BIN" \
    --dangerously-skip-permissions \
    -p "Ти виконуєш щоденний план для YACY проекту.
Поточне завдання з PLAN.md (рядок $STEP_LINE):
$STEP_TEXT

Виконай це завдання. Після виконання:
1. Зроби git commit якщо були зміни
2. Познач завдання як виконане в PLAN.md (замінити [ ] на [x])
3. Виведи короткий звіт що зроблено (до 300 символів)

Звіт виведи в кінці у форматі:
REPORT: <текст звіту>" \
    2>&1 | tail -20 || echo "ERROR: Claude execution failed")

# Extract report
REPORT=$(echo "$STEP_OUTPUT" | grep "^REPORT:" | sed 's/^REPORT: //' || echo "Виконано без детального звіту")

# Mark step as done in PLAN.md
if echo "$STEP_OUTPUT" | grep -qv "ERROR"; then
    sed -i '' "${STEP_LINE}s/- \[ \]/- [x]/" "$PLAN_FILE"
    log "Step marked as done"
    tg_report "✅ Крок виконано" "$REPORT"
else
    tg_report "❌ Помилка виконання" "Крок: $STEP_TEXT\nПомилка: $(echo "$STEP_OUTPUT" | tail -3)"
fi

log "Daily agent finished"
