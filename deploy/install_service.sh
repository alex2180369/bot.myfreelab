#!/usr/bin/env bash
# Installs the bot as a system service that starts at boot and restarts after a crash.
# Run once on the server:  sudo bash ~/apps/consult-bot/deploy/install_service.sh
# Safe to re-run.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi

APP=/home/mylab/apps/consult-bot
[ -x "$APP/.venv/bin/python" ] || { echo "Virtual environment not found in $APP/.venv" >&2; exit 1; }

# Stop a manually started copy, otherwise two processes would answer the same messages.
pkill -u mylab -f "python -m app.main" 2>/dev/null || true

install -m 644 "$APP/deploy/consult-bot.service" /etc/systemd/system/consult-bot.service
systemctl daemon-reload
systemctl enable --now consult-bot
sleep 3
systemctl --no-pager --lines=12 status consult-bot || true
echo
echo "Logs: journalctl -u consult-bot -f"
