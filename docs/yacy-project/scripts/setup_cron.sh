#!/bin/bash
# Встановлює cron на Mac для YACY Daily Agent
# Запуск: bash scripts/setup_cron.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT="$SCRIPT_DIR/daily_agent.sh"
LOG="$SCRIPT_DIR/cron.log"

chmod +x "$AGENT"

# Mac cron потребує launchd або crontab
# Використовуємо launchd (надійніший на Mac — не залежить від сну)
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_FILE="$PLIST_DIR/com.yacy.daily-agent.plist"

mkdir -p "$PLIST_DIR"

cat > "$PLIST_FILE" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.yacy.daily-agent</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${AGENT}</string>
    </array>

    <!-- Щодня о 4:00 -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>4</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <!-- Запустити якщо пропустили (комп спав) -->
    <key>RunAtLoad</key>
    <false/>

    <key>StandardOutPath</key>
    <string>${LOG}</string>
    <key>StandardErrorPath</key>
    <string>${LOG}</string>

    <!-- Перезапуск якщо впав -->
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
PLIST

# Завантажити/перезавантажити
launchctl unload "$PLIST_FILE" 2>/dev/null || true
launchctl load "$PLIST_FILE"

echo "✅ LaunchAgent встановлено: $PLIST_FILE"
echo "   Запуск: щодня о 04:00"
echo "   Лог: $LOG"
echo ""
echo "Команди управління:"
echo "  launchctl list | grep yacy     — перевірити статус"
echo "  launchctl start com.yacy.daily-agent  — запустити вручну зараз"
echo "  launchctl unload $PLIST_FILE   — вимкнути"

# Перевірити чи є Telegram налаштований
if [ ! -f "$HOME/.yacy_telegram.env" ]; then
    echo ""
    echo "⚠️  Telegram не налаштований!"
    echo "   Створи файл ~/.yacy_telegram.env:"
    echo "   export TG_BOT_TOKEN='your_bot_token'"
    echo "   export TG_CHAT_ID='your_chat_id'"
fi
