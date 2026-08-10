# Privacy & Security

This system holds highly confidential business conversations. Privacy is a
first-class feature, not an afterthought. This document answers, point by
point, exactly how your data is handled — and where you have control.

## Where your data lives

| Data | Location | Notes |
|---|---|---|
| **Audio recordings** | `backend/data/audio/` on **your** server/host | Never uploaded anywhere except (optionally) to your chosen transcription provider for the seconds it takes to transcribe. |
| **Transcripts** | Your SQLite database (`backend/data/brain.db`) | On your host. |
| **Executive memory** (summaries, items, people, companies, facts) | Same SQLite file | On your host. |
| **Search index** | Same SQLite file | On your host. |
| **Secrets** (session key, password hash) | `backend/data/.secret_key`, `.password_hash` | Local files, `0600` permissions. |

**You own the database file.** Copy it, encrypt it, move it, or delete it at
any time. The entire "second brain" is that one file plus the audio folder.

## What is sent to external AI services (and what is not)

By default the app uses two external APIs. Here is exactly what each receives:

| Service | Receives | Does **not** receive |
|---|---|---|
| **OpenAI Whisper** (transcription) | The **audio file** of a conversation, only when you add one, only to turn it into text. | Your database, other conversations, profiles, or memory. |
| **Anthropic Claude** (understanding, chat, briefings) | The **transcript text** (and, for chat/briefings, the **relevant** retrieved snippets) needed to answer. | Your audio. Your whole database — only the pieces relevant to the current task. |

Both Anthropic and OpenAI state that **API data is not used to train their
models** by default. Still, if a conversation is too sensitive to leave your
premises, use the fully-local option below.

### Fully-local / zero-external option

The provider abstraction supports running **with no external services**:

- **Transcription:** set `TRANSCRIBE_PROVIDER=mock` today (paste transcripts),
  or drop in **local Whisper** (whisper.cpp / faster-whisper) so audio never
  leaves your machine.
- **Understanding:** a local LLM can be added behind the same `LLM` interface.

This is the maximum-control mode: audio and text stay entirely on your
hardware. The trade-off is quality/convenience vs. absolute privacy — you
choose per your risk tolerance, and can even decide per-conversation.

## Encryption

- **In transit:** all API calls use HTTPS/TLS. Deploy the app itself behind
  HTTPS (a reverse proxy such as Caddy/Nginx with an auto TLS certificate).
- **At rest:**
  - Simplest and recommended: run the backend on a host with **full-disk
    encryption** (FileVault on macOS, LUKS on Linux). The DB file and audio are
    then encrypted at rest by the OS.
  - Stronger: use **SQLCipher** (an encrypted SQLite build) for a
    password-encrypted database file — a documented upgrade that keeps the same
    schema.
- **Backups** should be encrypted too (see below).

## Authentication & access control

- The dashboard is **password-protected**. You set `APP_PASSWORD`; if you
  don't, a strong random password is generated and shown once in the server
  console (the app is never left open by default).
- Passwords are stored only as a **PBKDF2-SHA256 hash** (200k iterations),
  never in plaintext.
- Sessions are **HMAC-signed cookies** with an expiry, `HttpOnly` and
  `SameSite=Lax`. No session data is exposed to the browser.
- **Recommended hardening for production:**
  - Put the app behind HTTPS and, ideally, a VPN or IP allow-list so it isn't
    publicly reachable.
  - Add a second factor (the roadmap includes passkeys/TOTP for multi-user).

## Preventing unauthorized access

1. Never expose the app directly to the internet without HTTPS + auth.
2. Prefer a private network / VPN / Tailscale for remote access.
3. Keep `APP_PASSWORD` and `SECRET_KEY` strong and secret (in `.env`, which is
   git-ignored).
4. Use full-disk encryption on the host.
5. Restrict OS file permissions on `backend/data/` to your user only.

## Backups

- The whole system is **one folder**: `backend/data/` (database + audio). Back
  that up.
- Recommended: an **encrypted** backup — e.g. `restic`, `borg`, or an
  encrypted disk image — to a location you control. Example nightly job:
  `restic backup backend/data` to an encrypted repository.
- Because SQLite uses WAL mode, back up with the app briefly stopped, or use
  SQLite's online backup API for consistency.

## Deleting data

- **A single conversation:** the Delete button removes the conversation, its
  transcript, all extracted items, its search-index entries, and its audio
  file — immediately and permanently.
- **Everything:** stop the app and delete `backend/data/`. That erases the
  entire second brain. (Also remove any external backups.)
- Note: external providers process transient copies to fulfil a request;
  neither retains your content for training by default, but you cannot
  "delete" from a third party what was already sent — which is why the
  local-only option exists for the most sensitive material.

## Privacy trade-offs — the honest summary

| Mode | Privacy | Quality / effort |
|---|---|---|
| Cloud STT + cloud LLM (default) | Good (data stays yours except transient API processing; no training use) | Best quality, least effort |
| Cloud LLM + **local** STT | Better (audio never leaves your host) | Great quality; a bit more setup |
| **Fully local** STT + LLM | Maximum (nothing leaves your host) | Good; more setup + a capable machine |

You can mix these, and even choose per conversation. The architecture is built
so that raising your privacy level never means abandoning the product.
