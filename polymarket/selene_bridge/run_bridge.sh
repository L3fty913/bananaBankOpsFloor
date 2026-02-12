#!/usr/bin/env bash
set -euo pipefail
cd /opt/polybot/selene_bridge
# expects OPENAI_API_KEY in /opt/polybot/.env, loaded by systemd/interactive shell if you source it
nohup /opt/polybot/env/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8789 > /opt/polybot/selene_bridge.log 2>&1 < /dev/null &
sleep 1
pgrep -af 'uvicorn app:app --host 0.0.0.0 --port 8789' || true
