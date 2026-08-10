# Setup Guide (for the CEO — no coding required)

This guide is written for a non-programmer. Follow it top to bottom. If you
have technical help, hand them the "Run the app" section; the rest is for you.

There are three things to do:
1. **Get two API keys** (5 minutes) — unlocks transcription + AI.
2. **Run the app** (or have someone run it once on a server/Mac).
3. **Set up 1-tap capture from your iPhone** (optional but recommended).

You can skip step 1 entirely to try the app in **demo mode** first — every
screen works; only real transcription/AI is disabled until keys are added.

---

## Step 1 — Get your API keys

### A) Anthropic (the "brain": summaries, extraction, chat, briefings)
1. Go to **https://console.anthropic.com** and sign up / log in.
2. Add a payment method (usage is pay-as-you-go; typical cost is a few US
   cents per conversation).
3. Open **API Keys → Create Key**. Copy the key (starts with `sk-ant-…`).

### B) OpenAI (speech-to-text: turns audio into text, incl. Persian)
1. Go to **https://platform.openai.com/api-keys** and sign up / log in.
2. Add a payment method (Whisper is about **US$0.006 per minute** of audio).
3. Click **Create new secret key**. Copy it (starts with `sk-…`).

Keep both keys somewhere safe for the next step. **Never share them.**

---

## Step 2 — Run the app

> If you have technical help, this is the only part they need. It runs on a
> Mac, a Linux server, or a small always-on machine.

1. Open the project's `backend` folder and copy `.env.example` to `.env`.
2. Open `.env` in any text editor and fill in:
   ```
   APP_PASSWORD=choose-a-strong-password
   ANTHROPIC_API_KEY=sk-ant-...      (from step 1A)
   OPENAI_API_KEY=sk-...             (from step 1B)
   ```
3. From the project root, run:
   ```
   ./run.sh
   ```
   (First run installs everything automatically. On Windows, use WSL or the
   equivalent `uvicorn app.main:app` command inside `backend/`.)
4. Open **http://localhost:8000** in your browser and sign in with the
   password you chose.

That's it. To make it reachable from your phone securely, ask your technical
helper to put it behind HTTPS + a VPN/Tailscale (see the privacy doc). Never
expose it to the open internet without HTTPS and a password.

---

## Step 3 — Capture conversations

You add a conversation in two ways from the dashboard's **“＋ Add
conversation”** button:
- **Upload an audio file**, or
- **Paste a transcript** (e.g. from Zoom's own transcript, or typed notes).

Here is how to get audio from each source:

### iPhone phone calls (iOS 18.1+)
1. During a call, tap the **Call Recording** button (top-left, the waveform
   icon). Both parties hear an announcement — this is required by Apple.
2. After the call, the recording is saved in the **Notes** app (and often a
   transcript with it).
3. **Share** that audio/transcript into the app (see the 1-tap Shortcut
   below), or upload it manually.

> If your iPhone/region doesn't have Call Recording yet, use the speakerphone +
> Voice Memos method described under WhatsApp.

### WhatsApp calls
WhatsApp calls **cannot** be recorded by any app (they're end-to-end
encrypted). Reliable alternatives:
- Ask the other person to send key points as a **WhatsApp voice note**, then
  share that note into the app; **or**
- Put the call on **speakerphone** and record the room with **Voice Memos** on
  a second device (with consent); **or**
- For important calls, use a **Zoom/Meet** call instead and record it.

### In-person meetings
Open **Voice Memos**, record, then share/upload the file. Best value source.

### Online meetings (Zoom / Google Meet / Teams)
Use the platform's **Record** button. Afterwards upload the audio, or paste the
transcript it produces.

---

## Optional: 1-tap iPhone Shortcut (recommended)

This lets you send any audio to your assistant from the iOS share sheet.

1. Open the **Shortcuts** app on iPhone → **+** to create a shortcut.
2. Add action **“Get Contents of URL”** and configure:
   - **URL:** `https://YOUR-APP-ADDRESS/api/conversations`
   - **Method:** `POST`
   - **Request Body:** `Form`
   - Add fields:
     - `audio` → **Shortcut Input** (the shared audio file)
     - `source` → `phone` (or `in_person`, etc.)
     - `consent_ack` → `true`
3. Name it **“Send to Executive Brain.”**
4. Now, from Notes/Voice Memos/Files, tap **Share → Send to Executive Brain**.
   The conversation is uploaded, transcribed, and analyzed automatically.

> Your technical helper can also add an authentication header/token to this
> Shortcut for security; ask them to enable an API token (a small, documented
> addition) before using it over the public internet.

---

## What you'll see

Within a minute of adding a conversation you get: an **executive summary**,
extracted **decisions / commitments / action items / deadlines / risks**, and
the people & companies get **profiles** that grow over time. Ask the dashboard
chat anything ("What did I promise Ali?"), and click **Pre-call briefing** on
any person before you speak with them again.

---

## Costs at a glance

- **Transcription:** ~US$0.006 / minute of audio (OpenAI Whisper).
- **AI understanding + chat:** typically a few US cents per conversation
  (Anthropic Claude), depending on length.
- **Hosting:** free if you run it on a Mac/PC you already own; a small cloud
  server is ~US$5–10/month.

For a busy CEO this is usually a few dollars a month — far less than the value
of never forgetting a commitment again.
