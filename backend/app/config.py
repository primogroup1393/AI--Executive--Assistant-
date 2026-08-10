"""
Central configuration. All settings come from environment variables so that
secrets never live in the codebase. See .env.example for the full list.

Design note: the app is built to run in three modes depending on which keys
are present:
  - Full mode:   TRANSCRIBE + LLM providers configured (real product)
  - Hybrid mode: LLM configured, transcription via manual paste
  - Demo mode:   no keys at all -> mock providers so the whole pipeline,
                 UI, profiles, search and briefings still work end-to-end.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the backend/ directory (one level up from app/)
_BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_DIR / ".env")

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
DATA_DIR = Path(os.getenv("DATA_DIR", _BACKEND_DIR / "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_DIR = DATA_DIR / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "brain.db")).resolve()

# ---------------------------------------------------------------------------
# Authentication (single-user MVP; multi-user is a documented future step)
# ---------------------------------------------------------------------------
# The app owner sets APP_PASSWORD. If unset, a random one is generated and
# printed to the console on startup so the app is never left wide open.
APP_PASSWORD = os.getenv("APP_PASSWORD", "").strip()
# Secret used to sign session cookies. Auto-generated & persisted if absent.
SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", str(60 * 60 * 12)))  # 12h

# ---------------------------------------------------------------------------
# AI providers
# ---------------------------------------------------------------------------
# LLM (understanding / extraction / chat). Provider: "anthropic" or "mock".
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").strip().lower()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5").strip()

# Transcription. Provider: "openai", "mock".
TRANSCRIBE_PROVIDER = os.getenv("TRANSCRIBE_PROVIDER", "auto").strip().lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1").strip()

# Respect the outbound proxy configured in this environment, if any.
HTTPS_PROXY = os.getenv("HTTPS_PROXY", "") or os.getenv("https_proxy", "")


def resolved_llm_provider() -> str:
    if LLM_PROVIDER == "auto":
        return "anthropic" if ANTHROPIC_API_KEY else "mock"
    return LLM_PROVIDER


def resolved_transcribe_provider() -> str:
    if TRANSCRIBE_PROVIDER == "auto":
        return "openai" if OPENAI_API_KEY else "mock"
    return TRANSCRIBE_PROVIDER
