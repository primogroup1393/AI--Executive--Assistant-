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
# Deployment mode
# ---------------------------------------------------------------------------
# MODE controls the default privacy posture:
#   "private" -> everything runs locally: local Whisper + local LLM (Ollama).
#                No audio or text ever leaves your machine.
#   "cloud"   -> use Anthropic + OpenAI APIs (best quality, least setup).
#   "auto"    -> use whichever keys/services are configured (default).
MODE = os.getenv("MODE", "auto").strip().lower()

# ---------------------------------------------------------------------------
# AI providers
# ---------------------------------------------------------------------------
# LLM (understanding / extraction / chat): "anthropic" | "ollama" | "mock" | "auto".
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").strip().lower()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5").strip()

# Local LLM via Ollama (fully private).
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").strip().rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b").strip()

# Transcription: "openai" | "local" | "mock" | "auto".
TRANSCRIBE_PROVIDER = os.getenv("TRANSCRIBE_PROVIDER", "auto").strip().lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1").strip()

# Local Whisper (fully private, via faster-whisper).
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small").strip()      # tiny|base|small|medium|large-v3
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu").strip()      # cpu|cuda
WHISPER_COMPUTE = os.getenv("WHISPER_COMPUTE", "int8").strip()   # int8|float16|float32

# ---------------------------------------------------------------------------
# AI Phone Agent (answers calls, records, summarizes)  — cloud-only feature.
# ---------------------------------------------------------------------------
# Publicly reachable base URL of THIS server, e.g. https://brain.example.com
# Twilio needs it to open the media stream back to us. Leave empty to disable.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")

# Twilio (telephony / phone number).
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "").strip()

# OpenAI Realtime (voice conversation). Uses OPENAI_API_KEY.
REALTIME_MODEL = os.getenv("REALTIME_MODEL", "gpt-4o-realtime-preview").strip()
REALTIME_VOICE = os.getenv("REALTIME_VOICE", "alloy").strip()

# The AI agent's identity & behavior.
CEO_NAME = os.getenv("CEO_NAME", "the executive").strip()
AGENT_NAME = os.getenv("AGENT_NAME", "the AI assistant").strip()
AGENT_GREETING = os.getenv(
    "AGENT_GREETING",
    "Hello, you've reached {ceo}'s AI assistant. This call may be recorded so I "
    "can take notes. May I ask who's calling, and how I can help?",
).strip()
# Whether to also record the call audio via Twilio (transcript is always kept).
CALL_RECORDING_ENABLED = os.getenv("CALL_RECORDING_ENABLED", "true").lower() == "true"

# ---------------------------------------------------------------------------
# Email notifications (post-call summaries sent to the CEO).
# ---------------------------------------------------------------------------
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", "").strip() or SMTP_USER
SMTP_TLS = os.getenv("SMTP_TLS", "true").lower() == "true"
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", "").strip()

# Respect the outbound proxy configured in this environment, if any.
HTTPS_PROXY = os.getenv("HTTPS_PROXY", "") or os.getenv("https_proxy", "")


def phone_agent_enabled() -> bool:
    return bool(PUBLIC_BASE_URL and TWILIO_ACCOUNT_SID and OPENAI_API_KEY)


def email_enabled() -> bool:
    return bool(SMTP_HOST and SMTP_FROM and NOTIFY_EMAIL)


def resolved_llm_provider() -> str:
    if LLM_PROVIDER != "auto":
        return LLM_PROVIDER
    if MODE == "private":
        return "ollama"
    if MODE == "cloud":
        return "anthropic"
    return "anthropic" if ANTHROPIC_API_KEY else "mock"


def resolved_transcribe_provider() -> str:
    if TRANSCRIBE_PROVIDER != "auto":
        return TRANSCRIBE_PROVIDER
    if MODE == "private":
        return "local"
    if MODE == "cloud":
        return "openai"
    if OPENAI_API_KEY:
        return "openai"
    return "mock"
