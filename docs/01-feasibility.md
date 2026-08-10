# Feasibility: What is actually possible (and what is not)

This document answers the hard questions honestly, before any promises. The
guiding rule for this product: **we do not fake capabilities and we do not
bypass platform security.** Where a capability is technically or legally
impossible, we say so and provide the best legal workflow instead.

---

## 1. Can an app automatically record iPhone phone calls?

**No — not through any third-party app, including this one.**

- iOS does **not** expose call audio to third-party apps. There is no public
  API to tap the audio stream of a cellular call or a FaceTime call. Apple
  blocks this at the OS level for privacy and security reasons.
- The **only** native call recording on iPhone is Apple's own **Call
  Recording** feature, available on iOS 18.1+ on supported devices. When you
  start it:
  - Both parties hear an announcement that the call is being recorded.
  - The recording (and an automatic transcript on supported devices/regions)
    is saved into the **Notes** app / Phone app.
- Any product on the App Store that claims "automatic background call
  recording" is doing one of: (a) three-way calling through a recorded
  bridge/conference number, (b) VoIP calls inside their own app, or (c)
  operating outside the App Store rules. None of these silently record a
  normal iPhone call.

**Our approach:** use Apple's built-in Call Recording, then let you send the
resulting audio/transcript into this app with **one tap** via an iOS Shortcut
(see the setup guide). This is reliable, legal, and needs no security bypass.

---

## 2. Can an app record WhatsApp calls?

**No.**

- WhatsApp voice and video calls are **end-to-end encrypted** and WhatsApp
  provides **no recording API**. The audio never leaves the encrypted channel
  in a form an app could capture on iOS.
- On iOS there is also no system-wide "record the audio coming from another
  app" capability available to third parties for a live call.

**Practical options that DO work:**
1. **WhatsApp voice notes / shared audio** → share the audio file into this
   app. Fully supported today.
2. **Speakerphone + a second recording device** (e.g. Apple Voice Memos on
   another device, or a dedicated recorder) → upload the file. Low-tech but
   100% reliable and legal *with consent*.
3. For **business** use, move important calls to a platform that supports
   recording (a Zoom/Meet/Teams call, or a VoIP business line) and upload the
   recording.

---

## 3. In-person meetings

**Fully feasible.** Use the iPhone **Voice Memos** app (or the in-app
recorder on the roadmap) and upload the file. Modern phones capture room audio
well. This is the highest-value, lowest-friction source.

---

## 4. Online meetings (Zoom, Google Meet, Microsoft Teams)

**Fully feasible.** All of these have a native "Record meeting" function that
produces an audio/video file. Upload it. (Their own AI-notes features can also
export transcripts you can paste in.)

---

## 5. Voice notes / uploaded audio

**Fully feasible and already implemented.** Any audio file (m4a, mp3, wav,
ogg, mp4/mov) can be uploaded and processed.

---

## 6. Speech-to-text: Persian, English, and mixed

**Feasible today with strong quality.**

- **OpenAI Whisper** (`whisper-1` / newer transcription models) handles
  English and Persian well, including **code-switched** Persian/English speech,
  and returns word/segment **timestamps**. This is our default.
- **Speaker identification (diarization)** — "who said what" — is the one area
  with a caveat. Whisper transcribes accurately but does **not** label
  speakers. True diarization needs a dedicated model. Our architecture stores a
  `segments` list with a `speaker` field so a diarizing backend (local
  `pyannote`, or Deepgram/AssemblyAI) can be added without any schema change.
  For the MVP we ship accurate multilingual transcription + timestamps now, and
  treat full diarization as a documented, drop-in upgrade.

For **maximum privacy**, Whisper can run **locally** (whisper.cpp /
faster-whisper) with no audio leaving your machine. See the privacy doc.

---

## 7. Understanding, extraction, memory, search (the "brain")

**Fully feasible and implemented.** A large language model (Anthropic Claude
by default) reads each transcript and produces the executive summary and the
structured extraction (decisions, commitments, action items, deadlines, risks,
people, companies, etc.). Retrieval + the model power grounded search/chat and
pre-call briefings. This is the core of the product and it works today.

---

## Consent & legality (important, not legal advice)

Call/meeting recording laws vary by country and even by state/region. Some
require **all parties** to consent; some require only one. Because your
conversations are cross-border and high-stakes:

- The app requires you to **acknowledge consent** when adding a recording.
- Prefer explicit, spoken consent at the start of recorded calls.
- Apple's Call Recording announces itself automatically, which helps.

This is a compliance reminder, **not legal advice**. For sensitive
jurisdictions, confirm with counsel.

---

## Bottom line

| Capability | Auto-capture? | Our workflow |
|---|---|---|
| iPhone calls | ❌ impossible for any app | Apple Call Recording → 1-tap Shortcut upload |
| WhatsApp calls | ❌ impossible (E2E encrypted) | Share voice note / external recorder / move to recordable platform |
| In-person | ✅ | Voice Memos → upload |
| Online meetings | ✅ | Native record → upload |
| Voice notes / files | ✅ | Direct upload (implemented) |
| Transcription (fa/en/mixed) | ✅ | Whisper (cloud or local) |
| Diarization | ⚠️ partial | Timestamps now; drop-in speaker model later |
| Summary / extraction / memory / search / briefings | ✅ | Implemented |

The product's real value is everything **after** capture. That is what we
build, fully and for real.
