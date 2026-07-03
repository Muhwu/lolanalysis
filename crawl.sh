#!/usr/bin/env bash
# Crawl match history. Pass --limit N for a small test batch.
set -euo pipefail
cd "$(dirname "$0")"
exec .venv/bin/python crawl.py "$@"
