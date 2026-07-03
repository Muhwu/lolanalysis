#!/usr/bin/env bash
# One-time setup: venv, dependencies, .env, data dir.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example — edit it and set RIOT_API_KEY and ACCOUNTS."
    echo "Get an API key at https://developer.riotgames.com (dev keys expire every 24h)."
fi

mkdir -p data
echo "Setup complete. Next steps:"
echo "  1. Edit .env (RIOT_API_KEY, ACCOUNTS)"
echo "  2. ./crawl.sh --limit 5   # small test crawl to validate the key"
echo "  3. ./crawl.sh             # full crawl"
echo "  4. ./run.sh               # web UI at http://localhost:8321"
