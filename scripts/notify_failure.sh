#!/bin/sh
# Post a Discord webhook message when a systemd service stops abnormally (crash, watchdog kill, start timeout).
# Use from a unit as:  ExecStopPost=/bin/sh /home/ubuntu/<BotFolder>/src/shared/scripts/notify_failure.sh %n
# The webhook URL is read from the file below (a single line, kept out of git).
# A crash-looping service only gets one message per THROTTLE_SECONDS; the next one counts the failures in between.

WEBHOOK_URL_FILE=/home/ubuntu/.config/failure-webhook-url
STATE_DIR=/home/ubuntu/.cache/notify-failure
THROTTLE_SECONDS=1800

[ "$SERVICE_RESULT" = "success" ] && exit 0
[ -r "$WEBHOOK_URL_FILE" ] || exit 0

mkdir -p "$STATE_DIR"
STATE_FILE="$STATE_DIR/$1"
NOW=$(date +%s)
LAST_SENT=0
SUPPRESSED=0
[ -r "$STATE_FILE" ] && read -r LAST_SENT SUPPRESSED < "$STATE_FILE"

if [ $((NOW - LAST_SENT)) -lt "$THROTTLE_SECONDS" ]; then
    echo "$LAST_SENT $((SUPPRESSED + 1))" > "$STATE_FILE"
    exit 0
fi

MESSAGE="<@312204139751014400> 💥 \`$1\` stopped: result=\`$SERVICE_RESULT\` ($EXIT_CODE $EXIT_STATUS)"
if [ "$SUPPRESSED" -gt 0 ]; then
    MESSAGE="$MESSAGE, plus $SUPPRESSED more failure(s) since the previous alert"
fi

curl -fsS -m 10 -H "Content-Type: application/json" \
    -d "{\"content\": \"$MESSAGE\"}" \
    "$(cat "$WEBHOOK_URL_FILE")" || exit 0
echo "$NOW 0" > "$STATE_FILE"
