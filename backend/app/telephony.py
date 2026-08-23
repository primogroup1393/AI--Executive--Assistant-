"""
AI Phone Agent — answers phone calls with a natural voice, records/transcribes
them, then runs the executive pipeline and emails you a summary.

How it works (the only architecture that actually works on real phone calls):

    Caller ──▶ Twilio phone number ──▶ (this webhook returns TwiML) ──▶
    Twilio opens a two-way MEDIA STREAM (websocket) to /voice/media ──▶
    we bridge that audio to the OpenAI Realtime API (speech-in, speech-out,
    plus live transcripts of BOTH sides) ──▶ when the call ends we assemble the
    transcript, extract executive knowledge, and email you the summary.

You cannot make an app answer your *iPhone* directly (iOS forbids it). Instead
you forward your iPhone to this dedicated AI number (see docs/05-ai-phone-agent.md).

This feature is cloud-based by nature (telephony + realtime voice). It is
enabled only when PUBLIC_BASE_URL + Twilio + OpenAI are configured; otherwise
the endpoints report that it's disabled.
"""
from __future__ import annotations

import asyncio
import base64
import json
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse

from . import config, notify, pipeline

router = APIRouter()
_post_call_pool = ThreadPoolExecutor(max_workers=2)

# In-memory transcript accumulation per active call (cleared when call ends).
_calls: dict[str, dict] = {}
_calls_lock = threading.Lock()


def agent_instructions() -> str:
    return (
        f"You are {config.AGENT_NAME}, the AI assistant answering the phone on "
        f"behalf of {config.CEO_NAME}. "
        "Speak naturally, warmly, and concisely, like a professional executive "
        "assistant. Detect the caller's language automatically and reply in the "
        "same language — support Persian (Farsi) and English, including a mix. "
        "Your goals: greet the caller, find out who they are, their company, the "
        "reason for the call, and capture any message, requests, dates, amounts, "
        "or deadlines. "
        f"IMPORTANT GUARDRAILS: never claim to be {config.CEO_NAME}; never make "
        "promises, commitments, prices, or decisions on their behalf — instead "
        f"say you'll pass the message to {config.CEO_NAME}. If something is "
        "urgent, acknowledge it and note it. Keep your turns short and let the "
        "caller speak. When the conversation is complete, thank them politely."
    )


# ---------------------------------------------------------------------------
# 1) Incoming call webhook -> TwiML that starts the media stream
# ---------------------------------------------------------------------------
@router.post("/voice/incoming")
async def voice_incoming(request: Request):
    if not config.phone_agent_enabled():
        return PlainTextResponse(
            '<?xml version="1.0" encoding="UTF-8"?><Response><Say>'
            "The AI assistant is not configured yet. Goodbye."
            "</Say><Hangup/></Response>",
            media_type="application/xml")

    form = await request.form()
    call_sid = form.get("CallSid", "")
    from_number = form.get("From", "")
    with _calls_lock:
        _calls[call_sid] = {"from": from_number, "turns": []}

    # Best-effort: start Twilio call recording (audio archive) if enabled.
    if config.CALL_RECORDING_ENABLED:
        _post_call_pool.submit(_start_twilio_recording, call_sid)

    base = config.PUBLIC_BASE_URL.replace("https://", "").replace("http://", "")
    ws_url = f"wss://{base}/voice/media"
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Connect><Stream url="{ws_url}"><Parameter name="callSid" value="{call_sid}"/>'
        "</Stream></Connect>"
        "</Response>"
    )
    return PlainTextResponse(twiml, media_type="application/xml")


@router.post("/voice/status")
async def voice_status(request: Request):
    """Twilio call status callback. Finalize when the call completes."""
    form = await request.form()
    call_sid = form.get("CallSid", "")
    status = form.get("CallStatus", "")
    if status in ("completed", "failed", "busy", "no-answer", "canceled"):
        _finalize_call(call_sid)
    return PlainTextResponse("ok")


# ---------------------------------------------------------------------------
# 2) Media stream bridge:  Twilio  <->  OpenAI Realtime
# ---------------------------------------------------------------------------
@router.websocket("/voice/media")
async def voice_media(ws: WebSocket):
    await ws.accept()
    import websockets  # local import; only needed for the phone feature

    call_sid = ""
    stream_sid = ""
    oai_url = f"wss://api.openai.com/v1/realtime?model={config.REALTIME_MODEL}"
    headers = {
        "Authorization": f"Bearer {config.OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1",
    }

    try:
        async with websockets.connect(oai_url, additional_headers=headers,
                                      max_size=None) as oai:
            # Configure the realtime session for telephony (8kHz mu-law).
            await oai.send(json.dumps({
                "type": "session.update",
                "session": {
                    "turn_detection": {"type": "server_vad"},
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "voice": config.REALTIME_VOICE,
                    "instructions": agent_instructions(),
                    "modalities": ["audio", "text"],
                    "input_audio_transcription": {"model": "whisper-1"},
                },
            }))

            async def twilio_to_oai():
                nonlocal call_sid, stream_sid
                async for raw in ws.iter_text():
                    msg = json.loads(raw)
                    ev = msg.get("event")
                    if ev == "start":
                        stream_sid = msg["start"]["streamSid"]
                        params = msg["start"].get("customParameters", {}) or {}
                        call_sid = params.get("callSid") or msg["start"].get("callSid", "")
                        # Greet first.
                        await oai.send(json.dumps({
                            "type": "response.create",
                            "response": {"instructions":
                                         "Greet the caller now: " + config.AGENT_GREETING.format(
                                             ceo=config.CEO_NAME)},
                        }))
                    elif ev == "media":
                        await oai.send(json.dumps({
                            "type": "input_audio_buffer.append",
                            "audio": msg["media"]["payload"],
                        }))
                    elif ev == "stop":
                        break

            async def oai_to_twilio():
                nonlocal call_sid
                async for raw in oai:
                    data = json.loads(raw)
                    t = data.get("type")
                    if t == "response.audio.delta" and data.get("delta"):
                        await ws.send_text(json.dumps({
                            "event": "media", "streamSid": stream_sid,
                            "media": {"payload": data["delta"]},
                        }))
                    elif t == "input_audio_buffer.speech_started":
                        # Caller barged in — stop our current audio playback.
                        await ws.send_text(json.dumps({
                            "event": "clear", "streamSid": stream_sid}))
                    elif t == "conversation.item.input_audio_transcription.completed":
                        _add_turn(call_sid, "Caller", data.get("transcript", ""))
                    elif t == "response.audio_transcript.done":
                        _add_turn(call_sid, "Assistant", data.get("transcript", ""))

            await asyncio.gather(twilio_to_oai(), oai_to_twilio())

    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        print(f"[telephony] media bridge error: {type(e).__name__}: {e}")
    finally:
        if call_sid:
            _finalize_call(call_sid)


# ---------------------------------------------------------------------------
# Transcript accumulation + post-call processing
# ---------------------------------------------------------------------------
def _add_turn(call_sid: str, speaker: str, text: str) -> None:
    text = (text or "").strip()
    if not call_sid or not text:
        return
    with _calls_lock:
        call = _calls.setdefault(call_sid, {"from": "", "turns": []})
        call["turns"].append((speaker, text))


def _finalize_call(call_sid: str) -> None:
    with _calls_lock:
        call = _calls.pop(call_sid, None)
    if not call or not call.get("turns"):
        return
    _post_call_pool.submit(_process_call, call)


def _process_call(call: dict) -> None:
    """Runs in a worker thread: build transcript -> extract -> email summary."""
    try:
        turns = call.get("turns", [])
        transcript = "\n".join(f"{spk}: {txt}" for spk, txt in turns)
        from_number = call.get("from") or "Unknown caller"
        title = f"Phone call — {from_number}"
        cid = pipeline.create_conversation(
            title=title, source="phone", occurred_at=None,
            audio_path=None, transcript=transcript, consent_ack=True)
        pipeline.process_conversation(cid)   # runs extraction (transcript present)
        notify.send_call_summary(cid)
    except Exception as e:  # noqa: BLE001
        print(f"[telephony] post-call processing failed: {type(e).__name__}: {e}")


def _start_twilio_recording(call_sid: str) -> None:
    """Best-effort: archive the call audio at Twilio. Transcript is primary."""
    if not (config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN and call_sid):
        return
    try:
        import httpx
        url = (f"https://api.twilio.com/2010-04-01/Accounts/"
               f"{config.TWILIO_ACCOUNT_SID}/Calls/{call_sid}/Recordings.json")
        with httpx.Client(timeout=20) as c:
            c.post(url, data={},
                   auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN))
    except Exception as e:  # noqa: BLE001
        print(f"[telephony] could not start recording: {e}")
