# Start the web UI at http://localhost:8321 (Windows / PowerShell equivalent of run.sh)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$port = if ($env:PORT) { $env:PORT } else { "8321" }

# --reload picks up code changes without restarting the server.
# `python -m uvicorn` works whether or not uvicorn.exe is on PATH.
& ".\.venv\Scripts\python.exe" -m uvicorn server.app:app --host 127.0.0.1 --port $port --reload
