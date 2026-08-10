#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Executive Brain — start the FULLY PRIVATE version with ONE command.
# Everything runs on YOUR computer. No audio or text ever leaves your machine.
#
#   Usage:  ./start-private.sh
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")"

echo ""
echo "=================================================================="
echo "  Executive Brain — Private Mode"
echo "=================================================================="

# 1) Docker check
if ! command -v docker >/dev/null 2>&1; then
  echo ""
  echo "  Docker is not installed yet. It's a free, one-time install:"
  echo "    → https://www.docker.com/products/docker-desktop/"
  echo "  Install it, open Docker Desktop once, then run this again."
  echo ""
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo ""
  echo "  Docker is installed but not running. Please open Docker Desktop,"
  echo "  wait until it says 'running', then run ./start-private.sh again."
  echo ""
  exit 1
fi

# 2) First-run config: generate a login password + pick model sizes
if [ ! -f .env ]; then
  if command -v python3 >/dev/null 2>&1; then
    PW="$(python3 -c 'import secrets; print(secrets.token_urlsafe(9))')"
  else
    PW="$(openssl rand -base64 9 | tr -d '/+=' )"
  fi
  cat > .env <<EOF
# Your private login password (change it here anytime, then restart).
APP_PASSWORD=${PW}
# Local AI model (understanding/chat). Smaller = faster & less RAM:
#   qwen2.5:7b (best quality, ~8GB RAM) | qwen2.5:3b | llama3.2:3b (light)
OLLAMA_MODEL=qwen2.5:7b
# Local speech-to-text model: tiny | base | small | medium | large-v3
WHISPER_MODEL=small
EOF
  echo ""
  echo "  ✓ Created your private password:   ${PW}"
  echo "    (saved in the .env file — you can change it there)"
fi

# 3) Launch
echo ""
echo "  Starting the app + local AI. The FIRST run downloads the AI model"
echo "  (a few GB) and may take several minutes. Later starts are instant."
echo ""
docker compose up -d --build

echo ""
echo "=================================================================="
echo "  ✓ Executive Brain is starting at:   http://localhost:8000"
echo ""
echo "  • Watch model download progress:   docker compose logs -f ollama-pull"
echo "  • Your password is in the .env file."
echo "  • Stop everything:                 docker compose down"
echo "  • All your data stays in:          ./backend/data"
echo "=================================================================="
echo ""
