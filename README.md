# 🧠 Executive Brain — AI Executive Assistant & Business Memory

Turn every business conversation into durable, searchable executive knowledge.
Record or upload a call/meeting → it's transcribed → AI understands it →
decisions, commitments, deadlines and risks are extracted → everything is
linked to the right people and companies → you search it in plain language and
get a **pre-call briefing** before you speak to anyone again.

Built to be **real and production-evolvable**, not a clickable mock. Every
button works today.

---

## Read this first

Before any code, four short documents answer the important questions:

1. **[Feasibility](docs/01-feasibility.md)** — the honest truth about iPhone &
   WhatsApp call recording (and what we do instead — no fakery, no security
   bypass).
2. **[Architecture](docs/02-architecture.md)** — how it's built and why.
3. **[Privacy & Security](docs/03-privacy-security.md)** — where your data
   lives, what leaves your machine, encryption, backups, deletion.
4. **[Setup Guide](docs/04-setup-guide.md)** — step-by-step for a
   non-programmer (API keys, running it, iPhone capture).

**Executive summary of feasibility:** No app can silently record iPhone calls
or WhatsApp calls — iOS and WhatsApp E2E encryption make that impossible, and
we won't fake it. Instead you capture natively (Apple Call Recording, Voice
Memos, Zoom/Meet recording, voice notes) and send the audio into the app with
one tap. Everything *after* capture — the real value — is fully built.

---

## What it does (the MVP, implemented)

- 🎙 **Capture** — upload any audio (or paste a transcript / notes). iOS
  Shortcut for 1-tap sharing.
- 📝 **Transcribe** — English, Persian, and mixed Persian/English, with
  timestamps (OpenAI Whisper; local option documented).
- ⚡ **Executive summary** — read it in under a minute: what happened, what was
  decided, what needs you.
- 🧩 **Structured extraction** — topics, decisions, **your** commitments vs.
  **their** commitments, action items, follow-ups, deadlines, dates, amounts,
  people, companies, open issues, questions for next time, risks — each with a
  source quote for verification.
- 🧠 **Long-term memory** — a growing profile per **person** and **company**:
  full history, promises made/received, open items, durable facts.
- 🔎 **Grounded AI chat** — ask in plain language; answers come **only** from
  your conversations, **cite their sources**, separate fact from
  interpretation, and never invent.
- ✨ **Pre-call briefings** — a 45-second brief before any conversation:
  context, open commitments, unresolved issues, suggested questions.
- 📊 **CEO dashboard** — today's conversations, open commitments, follow-ups,
  deadlines, decisions, and what needs your attention — at a glance.
- 🔒 **Private by design** — your data in one SQLite file you own; password
  auth; you control what (if anything) reaches external AI; fully-local mode
  possible.

---

## Quick start

### 🔒 Option A — Fully private, one command (recommended)

Everything runs **on your own computer** (local speech-to-text + local AI).
**No audio or text ever leaves your machine.** You only need
[Docker Desktop](https://www.docker.com/products/docker-desktop/) installed.

```bash
./start-private.sh
# then open http://localhost:8000  (your password is shown + saved in .env)
```

The first run downloads the local AI model (a few GB) once; later starts are
instant. Recommended: a computer with ~8 GB free RAM. On a lighter machine set
`OLLAMA_MODEL=llama3.2:3b` in `.env`. See the [Setup Guide](docs/04-setup-guide.md).

### ☁️ Option B — Cloud AI (highest quality, least setup)

```bash
./run.sh          # then open http://localhost:8000
```

- **No API keys?** It still runs in **demo mode** — every screen works; real
  transcription/AI activate the moment you add keys.
- **To use cloud AI:** copy `backend/.env.example` → `backend/.env`, set
  `MODE=cloud`, `APP_PASSWORD`, `ANTHROPIC_API_KEY`, and `OPENAI_API_KEY`.

Either way, if you didn't set `APP_PASSWORD`, a strong one is generated and
shown on startup — the app is never left open.

### Which should I choose?

| | Private (Option A) | Cloud (Option B) |
|---|---|---|
| Data leaves your machine | **Never** | Transcript/audio sent to AI API to process (not used for training) |
| Quality | Very good | Best |
| Setup | Install Docker, one command | Two API keys |
| Cost | Free (your computer) | ~a few $/month usage |
| Needs | ~8 GB RAM | Any machine |

---

## How it works (one glance)

```
Capture (native)  →  Upload  →  Transcribe (Whisper)  →  Understand + Extract (Claude)
      →  Link to people/companies  →  Store (SQLite + full-text search)
      →  Dashboard · Profiles · Grounded chat · Pre-call briefings
```

Details in the [architecture doc](docs/02-architecture.md).

---

## Tech stack

Python · FastAPI · SQLite (+ FTS5 full-text search) · Anthropic Claude
(understanding) · OpenAI Whisper (speech-to-text) · server-rendered Jinja2 UI.
Transcription and LLM sit behind **provider interfaces**, so you can swap in
local/private models — or run the whole thing offline — without touching the
product logic.

---

## Project layout

```
backend/
  app/
    main.py            FastAPI app + routes (dashboard, API)
    config.py          env-driven settings
    db.py              SQLite schema + full-text search
    pipeline.py        ingest → transcribe → extract → store
    extraction.py      LLM prompt → structured executive knowledge
    memory.py          people/company resolution + profiles
    search.py          grounded, cited AI chat (RAG)
    briefing.py        pre-call briefings
    auth.py            password + signed-session login
    providers/
      llm.py           Anthropic + mock (pluggable)
      transcription.py Whisper + mock (pluggable)
  templates/           premium executive UI
  static/              design system (css) + light JS
  requirements.txt
docs/                  feasibility · architecture · privacy · setup
run.sh                 one-command start
```

---

## Status & roadmap

**Done (this MVP):** capture/upload, multilingual transcription with
timestamps, executive summaries, full structured extraction, person/company
memory, grounded cited chat, pre-call briefings, CEO dashboard, auth, privacy
controls, demo mode.

**Documented next steps:** speaker diarization (drop-in), semantic search via
Postgres + pgvector, fully-local STT+LLM mode, encrypted DB (SQLCipher),
multi-user accounts + passkeys, background worker queue, native iOS share
extension.

Not legal advice — recording-consent laws vary by jurisdiction; the app asks
you to acknowledge consent per recording.
