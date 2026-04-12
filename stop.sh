#!/bin/bash
cd /root/newvk
if [ -f logs/bot.pid ]; then
  kill $(cat logs/bot.pid) 2>/dev/null || true
  rm -f logs/bot.pid
  echo "Bot stopped by PID"
else
  pkill -f vk_bot.py || true
  echo "Bot stopped by pkill"
fi
