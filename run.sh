#!/usr/bin/env bash
# Start the AI Executive Assistant.
#   ./run.sh            -> installs deps (first run) and starts the server
#   PORT=9000 ./run.sh  -> custom port
set -euo pipefail
cd "$(dirname "$0")/backend"

PORT="${PORT:-8000}"
PY="${PYTHON:-python3}"

if [ ! -d ".venv" ]; then
  echo "→ Creating virtual environment…"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "→ Installing dependencies…"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

if [ ! -f ".env" ]; then
  echo "→ No .env found; copying .env.example (demo mode until you add keys)."
  cp .env.example .env
fi

echo "→ Starting on http://localhost:${PORT}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
