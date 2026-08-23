# AI Phone Agent — answers your calls, records them, emails you a summary

This is the feature where an AI voice assistant **answers phone calls**,
**records & transcribes** them, and **emails you an executive summary** of each
call (also saved into your Executive Brain, linked to the caller).

Read the feasibility section first — it explains what is and isn't possible, so
there are no surprises.

---

## Feasibility (the honest truth)

**Can AI answer calls made directly to your iPhone number?** No app can do that.
iOS does not let any app auto-answer a call or inject AI voice into it. This is
an Apple restriction and we do not fake or bypass it.

**What works instead (and is a real product):** a **dedicated AI phone
number**. You either:
- give out this number as your "office/assistant" line, or
- set your iPhone to **forward** calls to it (always, or only when you're busy
  / don't answer).

The AI answers *that* number. This is exactly how "AI receptionist" products
work, and it is fully legitimate.

**Privacy reality:** unlike the rest of Executive Brain (which can run 100%
locally), this feature **cannot be fully private**. A phone call physically
travels through a telephone carrier, and natural real-time voice needs a cloud
voice service. So this feature uses:
- **Twilio** — provides the phone number and connects the call to your app.
- **OpenAI Realtime** — the natural voice conversation (speech in/out + live
  transcript of both sides, in Persian and English).
- **Your server with a public address** — Twilio must reach your app over the
  internet (a home laptop is not enough).

Your transcripts and summaries are still stored in **your** database, and the
summary email goes only to **you**.

**Consent / legality:** the AI announces that the call may be recorded, at the
start of every call. Recording-consent laws vary by country — this is a
compliance aid, not legal advice.

---

## How it works

```
Caller dials your AI number
        │
        ▼
   Twilio  ──POST──▶  /voice/incoming      (your app returns TwiML)
        │
        ▼
   Twilio opens a 2-way audio stream  ──▶  /voice/media (websocket)
        │                                        │
        │            your app bridges audio ◀────┘
        ▼                                        │
   OpenAI Realtime  ◀── speech in / speech out ──┘   (+ live transcript)
        │
   (call ends)
        ▼
   /voice/status  ──▶  build transcript ──▶ extract decisions/commitments/
                       deadlines/etc. ──▶ save to Executive Brain ──▶
                       EMAIL you the summary
```

The AI is instructed to act as your **assistant**, not as you: it takes
messages, captures who called, why, amounts, dates and requests, flags urgent
items — and never makes promises or decisions on your behalf.

---

## What you need to set up (step by step)

You'll need three accounts/pieces. Budget ~30 minutes once.

### 1) A public place to run the app
Twilio must reach your server over the internet with a real domain + HTTPS.
Easiest options:
- A small cloud server (e.g. a $5–10/month VPS) running `./start-private.sh`
  or `./run.sh`, behind HTTPS (Caddy/Nginx auto-TLS), **or**
- A tunnel for testing: install **ngrok** (`ngrok http 8000`) — it gives you a
  temporary public `https://...` URL. Great for trying it out.

Note the public URL (e.g. `https://brain.example.com` or the ngrok URL).

### 2) OpenAI key with Realtime
You already use OpenAI for transcription. The same `OPENAI_API_KEY` is used for
the realtime voice. (Realtime voice costs roughly a few cents per minute.)

### 3) Twilio phone number
1. Sign up at **https://twilio.com** and add funds (a number is ~$1–2/month;
   calls are a few cents/minute).
2. **Phone Numbers → Buy a number** (pick one that supports **Voice**).
3. Open that number's **Configure** page. Under **Voice → A call comes in**:
   - Set it to **Webhook**, method **HTTP POST**, URL:
     `https://YOUR-PUBLIC-URL/voice/incoming`
   - Under **Call status changes** (status callback), set:
     `https://YOUR-PUBLIC-URL/voice/status`
   - Save.
4. Copy your **Account SID** and **Auth Token** from the Twilio console.

### 4) Fill in your `.env`
```
PUBLIC_BASE_URL=https://YOUR-PUBLIC-URL
OPENAI_API_KEY=sk-...
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1...

# Make the assistant yours:
CEO_NAME=Abdi
AGENT_NAME=Nova
# (optional) customize the spoken greeting; {ceo} is replaced with CEO_NAME
# AGENT_GREETING=Hello, you've reached {ceo}'s assistant. This call may be recorded. How can I help?

# Email the summary to yourself (any SMTP; Gmail example shown):
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-gmail-app-password     # create at https://myaccount.google.com/apppasswords
SMTP_FROM=you@gmail.com
NOTIFY_EMAIL=you@gmail.com
```
Restart the app. On startup it will print `Phone agent: ENABLED`.

### 5) Point your iPhone at the AI number (optional)
To have the AI answer when you can't:
- **Settings → Phone → Call Forwarding** → forward to your Twilio number
  (forward always, or use conditional forwarding for "when busy / no answer"
  via your carrier's codes), **or**
- simply hand out the Twilio number as your assistant line.

---

## Try it without a phone first

From the dashboard you can verify the whole "record → understand → email"
pipeline without spending a cent on calls:

```
POST /api/phone/simulate     (form fields: transcript, from_number)
```
It creates a conversation from the transcript, extracts everything, and sends
the summary email (or prints it to the console if SMTP isn't set). Use it to
confirm your email + extraction are working before going live.

Check readiness anytime at `GET /api/phone/status`.

---

## Costs (typical)

- Twilio number: ~$1–2 / month. Inbound calls: ~1–2¢ / minute.
- OpenAI Realtime voice: ~a few ¢ / minute.
- Understanding + summary (Claude or local): a few ¢ per call.
- Server: free (your own machine, if publicly reachable) or ~$5–10 / month VPS.

A busy executive typically spends a few dollars a month — for never missing a
call or a message again.

---

## Limits & roadmap

- Audio archive: the transcript (speaker-separated) is captured natively and is
  the primary record; optional Twilio audio recording is started best-effort.
  Automatic download of that audio file into the app is a documented next step.
- Outbound AI calls (the AI calling people for you) are a natural extension of
  this same stack.
- For a fully-private phone option, a self-hosted SIP + local voice stack is
  possible but heavy; documented as a future path.
