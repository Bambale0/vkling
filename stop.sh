#!/bin/bash
cd /root/newvk
SERVICE_NAME="newvk-bot.service"

if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ] && systemctl list-unit-files "$SERVICE_NAME" >/dev/null 2>&1; then
  systemctl stop "$SERVICE_NAME"
  echo "Bot stopped by systemd"
elif [ -f logs/bot.pid ]; then
  kill $(cat logs/bot.pid) 2>/dev/null || true
  rm -f logs/bot.pid
  echo "Bot stopped by PID"
else
  pkill -f vk_bot.py || true
  echo "Bot stopped by pkill"
fi
