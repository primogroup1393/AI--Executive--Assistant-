"""
Transcription provider abstraction.

Returns a normalized result:
    {
      "text": "<full transcript>",
      "language": "fa|en|mixed|...",
      "segments": [ {"speaker","start_ms","end_ms","text"}, ... ]
    }

Notes on speaker identification (diarization)
---------------------------------------------
OpenAI Whisper produces high-quality multilingual text (incl. Persian and
Persian/English mixed) but does NOT label speakers. True diarization needs a
dedicated model (e.g. pyannote locally, or Deepgram/AssemblyAI). To keep the
MVP self-contained we:
  1) get accurate text + timestamps from Whisper, and
  2) apply a lightweight LLM-assisted speaker split downstream when useful.
The provider interface already carries a `segments` list so a diarizing
backend can be dropped in later with no schema change.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from .. import config


class Transcriber:
    name = "base"

    def transcribe(self, audio_path: Path, language_hint: str | None = None) -> dict[str, Any]:
        raise NotImplementedError


class OpenAIWhisper(Transcriber):
    name = "openai"

    def __init__(self) -> None:
        self.key = config.OPENAI_API_KEY
        self.model = config.OPENAI_TRANSCRIBE_MODEL

    def transcribe(self, audio_path: Path, language_hint: str | None = None) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.key}"}
        data = {"model": self.model, "response_format": "verbose_json"}
        # Whisper autodetects language; only hint when confident (fa/en).
        if language_hint in ("fa", "en"):
            data["language"] = language_hint
        with open(audio_path, "rb") as f:
            files = {"file": (audio_path.name, f, "application/octet-stream")}
            with httpx.Client(timeout=600) as client:
                r = client.post("https://api.openai.com/v1/audio/transcriptions",
                                headers=headers, data=data, files=files)
                r.raise_for_status()
                payload = r.json()
        segments = []
        for i, seg in enumerate(payload.get("segments", []) or []):
            segments.append({
                "speaker": None,
                "start_ms": int(float(seg.get("start", 0)) * 1000),
                "end_ms": int(float(seg.get("end", 0)) * 1000),
                "text": (seg.get("text") or "").strip(),
                "idx": i,
            })
        return {
            "text": (payload.get("text") or "").strip(),
            "language": payload.get("language") or language_hint or "unknown",
            "segments": segments,
        }


class LocalWhisper(Transcriber):
    """
    Fully-local speech-to-text via faster-whisper (CTranslate2). Audio never
    leaves the machine. Handles English, Persian, and mixed speech with
    word/segment timestamps. The model is downloaded once and cached locally.
    """
    name = "local"
    _model = None  # lazy singleton (loading is expensive)

    def __init__(self) -> None:
        self.model_size = config.WHISPER_MODEL
        self.device = config.WHISPER_DEVICE
        self.compute = config.WHISPER_COMPUTE

    def _get_model(self):
        if LocalWhisper._model is None:
            from faster_whisper import WhisperModel  # imported lazily
            LocalWhisper._model = WhisperModel(
                self.model_size, device=self.device, compute_type=self.compute)
        return LocalWhisper._model

    def transcribe(self, audio_path: Path, language_hint: str | None = None) -> dict[str, Any]:
        model = self._get_model()
        kwargs: dict[str, Any] = {"vad_filter": True, "beam_size": 5}
        if language_hint in ("fa", "en"):
            kwargs["language"] = language_hint
        segments_iter, info = model.transcribe(str(audio_path), **kwargs)
        segments, texts = [], []
        for i, seg in enumerate(segments_iter):
            txt = (seg.text or "").strip()
            texts.append(txt)
            segments.append({
                "speaker": None,
                "start_ms": int((seg.start or 0) * 1000),
                "end_ms": int((seg.end or 0) * 1000),
                "text": txt,
                "idx": i,
            })
        return {
            "text": " ".join(texts).strip(),
            "language": getattr(info, "language", None) or language_hint or "unknown",
            "segments": segments,
        }


class MockTranscriber(Transcriber):
    """
    Used when no transcription key is set. It does not invent conversation
    content — it returns a clearly-labelled placeholder and tells the user to
    paste a transcript or add a key. Real product behavior requires a key.
    """
    name = "mock"

    def transcribe(self, audio_path: Path, language_hint: str | None = None) -> dict[str, Any]:
        note = (
            "[No transcription provider configured. The audio was saved but "
            "not transcribed. Add an OPENAI_API_KEY to enable automatic "
            "speech-to-text, or paste the transcript manually.]"
        )
        return {"text": note, "language": "unknown", "segments": []}


_tx: Transcriber | None = None


def get_transcriber() -> Transcriber:
    global _tx
    if _tx is not None:
        return _tx
    provider = config.resolved_transcribe_provider()
    if provider == "openai" and config.OPENAI_API_KEY:
        _tx = OpenAIWhisper()
    elif provider == "local":
        _tx = LocalWhisper()
    else:
        _tx = MockTranscriber()
    return _tx


def reset_transcriber() -> None:
    global _tx
    _tx = None
