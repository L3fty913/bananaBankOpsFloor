#!/usr/bin/env bash
set -euo pipefail
cd /opt/polybot
mkdir -p /opt/polybot/rag
pkill -f 'collector.py' || true
pkill -f 'uvicorn server:app' || true
nohup env/bin/python3 collector.py > equity_collector.log 2>&1 < /dev/null &
nohup env/bin/python3 -m uvicorn server:app --host 0.0.0.0 --port 8787 > equity_terminal.log 2>&1 < /dev/null &
sleep 1
pgrep -af 'collector.py|uvicorn server:app'
