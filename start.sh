#!/bin/bash
# Start CronPulse — runs app.py (FastAPI) only.
# Legacy monitor (main.py) can be run separately if needed.
set -e

PORT=${PORT:-8080}
echo "[start] Launching CronPulse on port $PORT"
exec uvicorn app:app --host 0.0.0.0 --port "$PORT" --workers 1
