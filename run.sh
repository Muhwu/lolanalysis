#!/usr/bin/env bash
# Start the web UI at http://localhost:8321
set -euo pipefail
cd "$(dirname "$0")"
# --reload picks up code changes without restarting the server
exec .venv/bin/uvicorn server.app:app --host 127.0.0.1 --port "${PORT:-8321}" --reload
