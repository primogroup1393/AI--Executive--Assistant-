# Architecture

## Design goals

Reliable · Secure · Simple for a non-technical owner · Maintainable ·
Scalable · Cost-effective · Realistically deployable. Every decision below
optimizes for those, in that order.

## The pipeline (the heart of the product)

```
                 ┌─────────────────────────────────────────────────────────┐
   Capture       │  Apple Call Recording · Voice Memos · Zoom/Meet/Teams     │
   (outside app) │  recording · WhatsApp voice note · any audio file         │
                 └───────────────┬─────────────────────────────────────────┘
                                 │ upload (web / iOS Shortcut share-sheet)
                                 ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  BACKEND  (FastAPI, Python)                                            │
   │                                                                        │
   │  1. Ingest ─ save audio, create conversation record                    │
   │  2. Transcribe ─ Whisper (cloud or local)  ──► text + timestamps       │
   │  3. Extract ─ Claude ──► summary + structured JSON                      │
   │        (decisions, my/their commitments, actions, deadlines, dates,    │
   │         amounts, people, companies, open issues, questions, risks…)    │
   │  4. Resolve & link ─ people / companies (long-term memory)             │
   │  5. Index ─ full-text search (SQLite FTS5)                             │
   └───────────────┬────────────────────────────────────────────────────────┘
                   ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  SQLite database (single file you own)                                 │
   │  conversations · transcript_segments · people · companies · items ·   │
   │  memory_facts · search_index                                          │
   └───────────────┬────────────────────────────────────────────────────────┘
                   ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  CEO experience (server-rendered premium web UI)                       │
   │  Dashboard · Conversation view · Person/Company profiles ·             │
   │  Grounded AI chat (cited) · Pre-call briefings                         │
   └──────────────────────────────────────────────────────────────────────┘
```

## Where each responsibility runs

| Layer | Runs on | Why |
|---|---|---|
| **Capture** | iPhone / meeting platform (outside the app) | Platform limits make in-app call tapping impossible; capture natively, ingest reliably. |
| **Backend + pipeline** | Your server (or your Mac/mini-PC) | You keep control of raw audio and data. Python = best AI ecosystem. |
| **Database** | Single SQLite file on the backend host | Zero-ops, you own the file, trivial encrypted backup. Postgres-ready later. |
| **Transcription (STT)** | External API (OpenAI Whisper) **or** local Whisper | Cloud = best quality/ease; local = maximum privacy. Pluggable. |
| **LLM (understanding)** | External API (Anthropic Claude) **or** local model later | Frontier reasoning today; provider is abstracted for future local models. |
| **Search index** | In the same SQLite DB (FTS5) | No extra infrastructure; grounded retrieval for chat/briefings. |
| **UI** | Browser (desktop + mobile web) | Nothing to install; feels like a premium executive tool. |

## Technology stack (and why)

- **Python + FastAPI** — the richest ecosystem for AI/audio, async, tiny
  footprint, deployable anywhere from a laptop to a container.
- **SQLite (+ FTS5 full-text search)** — the whole database is one file you
  can encrypt, copy, and back up. It comfortably handles years of a single
  executive's conversations. The data layer is written so a move to
  **PostgreSQL + pgvector** (for semantic search at larger scale) is an
  isolated change.
- **Anthropic Claude** for summary/extraction/chat — strong multilingual
  reasoning (incl. Persian) and reliable structured output. Behind a provider
  interface (`app/providers/llm.py`) so it can be swapped.
- **OpenAI Whisper** for transcription — best-in-class Persian + English +
  mixed, with timestamps. Behind a provider interface
  (`app/providers/transcription.py`); local Whisper is a drop-in.
- **Server-rendered UI (Jinja2) + a little vanilla JS** — premium look,
  nothing to build/compile, easy to maintain, fast on mobile.

## Provider abstraction (a key architectural decision)

Business logic never calls a vendor directly. It calls `get_llm()` and
`get_transcriber()`. Each returns:

- a **real** provider when its API key is present, or
- a **mock** provider when it is not — so the *entire* app (UI, pipeline,
  profiles, search, briefings) runs end-to-end with **zero keys and zero
  network**. This is how we guarantee "no dead buttons" and easy local testing,
  and how we keep the door open to fully-local, fully-private deployment.

## Data model (essentials)

- **conversations** — one per call/meeting/note: title, source, time,
  language, audio path, transcript, executive summary, processing status.
- **transcript_segments** — timestamped lines (with a `speaker` slot for
  future diarization).
- **people / companies** — the intelligent profiles; entity resolution merges
  repeat mentions so memory accumulates.
- **items** — every extracted unit of executive knowledge, typed (`decision`,
  `my_commitment`, `their_commitment`, `action_item`, `followup`, `deadline`,
  `date`, `amount`, `open_issue`, `question_next`, `risk`, `highlight`), each
  with an owner, optional due date, status, confidence, and a **source quote**
  for verification.
- **memory_facts** — durable relationship facts per person/company.
- **search_index** — FTS5 index over summaries + items for grounded retrieval.

## Grounding & trust (non-negotiable)

- Every extracted item stores a **verbatim source quote**.
- AI chat answers **only** from retrieved conversations, **cites** the source
  conversation (`[#id]` links), separates **facts** from **interpretation**,
  and says "not in the records" instead of inventing.
- Pre-call briefings are built from the deterministic database profile; the
  model only *phrases* what the data already contains.

## Scaling path (when you outgrow the MVP)

1. **PostgreSQL + pgvector** for semantic (embedding) search across a large
   history — the data layer is isolated for this.
2. **Local Whisper + local LLM** for a fully air-gapped, private deployment.
3. **Real diarization** (pyannote / Deepgram) plugged into the existing
   `segments` structure.
4. **Multi-user / team** accounts with per-user encryption and RBAC.
5. **Background worker queue** (e.g. RQ/Celery) if volume grows beyond the
   built-in thread pool.

None of these require rewriting the product — only swapping a provider or a
storage backend behind the existing interfaces.
