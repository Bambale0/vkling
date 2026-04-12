#!/bin/bash
cd /root/newvk
pkill -f vk_bot.py || true
nohup python3 vk_bot.py > logs/vk_bot.log 2>&1 &
echo $! > logs/bot.pid
echo "Bot started (PID saved in logs/bot.pid)"
