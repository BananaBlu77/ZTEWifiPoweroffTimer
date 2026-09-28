#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="${1:-$(pwd)/zte_wifi_control.py}"
SCRIPT_PATH="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$SCRIPT_PATH")"

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "Script non trovato: $SCRIPT_PATH" >&2
  exit 1
fi

MARK_BEGIN="# zte-wifi-poweroff-timer BEGIN"
MARK_END="# zte-wifi-poweroff-timer END"
ENV_FILE="${2:-$HOME/.config/zte-wifi-timer.env}"
CRON_OFF="0 0 * * * . $ENV_FILE; /usr/bin/env python3 $SCRIPT_PATH off >> /var/log/zte-wifi-timer.log 2>&1"
CRON_ON="0 7 * * * . $ENV_FILE; /usr/bin/env python3 $SCRIPT_PATH on >> /var/log/zte-wifi-timer.log 2>&1"

CURRENT_CRON="$(crontab -l 2>/dev/null || true)"
FILTERED_CRON="$(printf '%s\n' "$CURRENT_CRON" | sed "/$MARK_BEGIN/,/$MARK_END/d")"

{
  printf '%s\n' "$FILTERED_CRON"
  printf '%s\n' "$MARK_BEGIN"
  printf '%s\n' "$CRON_OFF"
  printf '%s\n' "$CRON_ON"
  printf '%s\n' "$MARK_END"
} | crontab -

echo "Cron configurato: Wi-Fi OFF alle 00:00, ON alle 07:00"
echo "Variabili lette da: $ENV_FILE"
