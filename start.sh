#!/bin/bash
set -e

cd /root/newvk
PYTHON="${PYTHON:-python3}"
SERVICE_NAME="newvk-bot.service"
mkdir -p logs

if ! "$PYTHON" - <<'PY' >/dev/null 2>&1
import aiohttp
import dotenv
import flask
import flask_admin
import flask_login
import flask_sqlalchemy
import pydantic
import requests
import vkbottle
PY
then
    "$PYTHON" -m pip install -r requirements.txt
fi

if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    if [ ! -f "/etc/systemd/system/$SERVICE_NAME" ]; then
        cp /root/newvk/newvk-bot.service "/etc/systemd/system/$SERVICE_NAME"
        systemctl daemon-reload
        systemctl enable "$SERVICE_NAME"
    fi
    systemctl restart "$SERVICE_NAME"
    systemctl --no-pager --full status "$SERVICE_NAME"
else
    pkill -f '[v]k_bot.py' || true
    nohup "$PYTHON" vk_bot.py > logs/vk_bot.log 2>&1 &
    echo $! > logs/bot.pid
    echo "Bot started (PID saved in logs/bot.pid)"
fi
