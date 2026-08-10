"""
Ingestion pipeline: audio/transcript -> transcription -> extraction -> memory.

Runs in a background thread so the UI stays responsive. Status is tracked on
the conversation row (new -> transcribing -> extracting -> done|error) and the
dashboard polls it.
"""
from __future__ import annotations

import traceback
from pathlib import Path

from . import db, memory
from .extraction import extract
from .providers.transcription import get_transcriber


def create_conversation(*, title: str, source: str, occurred_at: str | None,
                        audio_path: str | None, transcript: str | None,
                        consent_ack: bool) -> int:
    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO conversations(title,source,occurred_at,audio_path,transcript,"
            "status,consent_ack) VALUES (?,?,?,?,?,?,?)",
            (title or "Untitled conversation", source, occurred_at, audio_path,
             transcript, "new", 1 if consent_ack else 0))
        return cur.lastrowid


def _set_status(conv_id: int, status: str, error: str | None = None) -> None:
    with db.tx() as conn:
        conn.execute("UPDATE conversations SET status=?, error=? WHERE id=?",
                     (status, error, conv_id))


def process_conversation(conv_id: int) -> None:
    """Full processing. Safe to call in a background thread."""
    try:
        conv = db.q1("SELECT * FROM conversations WHERE id=?", (conv_id,))
        if not conv:
            return
        transcript = conv["transcript"]
        language = conv["language"]

        # 1. Transcribe if we have audio but no transcript yet.
        if (not transcript or not transcript.strip()) and conv["audio_path"]:
            _set_status(conv_id, "transcribing")
            from .config import DATA_DIR
            audio_full = DATA_DIR / conv["audio_path"]
            result = get_transcriber().transcribe(Path(audio_full))
            transcript = result["text"]
            language = result.get("language")
            with db.tx() as conn:
                conn.execute("UPDATE conversations SET transcript=?, language=? WHERE id=?",
                             (transcript, language, conv_id))
                # store diarized/timed segments
                for seg in result.get("segments", []):
                    conn.execute(
                        "INSERT INTO transcript_segments(conversation_id,idx,speaker,"
                        "start_ms,end_ms,text) VALUES (?,?,?,?,?,?)",
                        (conv_id, seg.get("idx", 0), seg.get("speaker"),
                         seg.get("start_ms"), seg.get("end_ms"), seg.get("text", "")))

        if not transcript or not transcript.strip():
            _set_status(conv_id, "error", "No transcript available to analyze.")
            return

        # 2. Extract structured knowledge.
        _set_status(conv_id, "extracting")
        known = [r["name"] for r in db.q("SELECT name FROM people ORDER BY created_at DESC LIMIT 60")]
        ex = extract(transcript, source=conv["source"], known_people=known)

        # 3. Persist summary/title/language + all structured items.
        with db.tx() as conn:
            title = conv["title"]
            if (not title or title in ("Untitled conversation", "")) and ex.get("title"):
                title = ex["title"]
            conn.execute(
                "UPDATE conversations SET title=?, summary=?, language=?, status='done', error=NULL "
                "WHERE id=?",
                (title, ex.get("summary"), ex.get("language") or language, conv_id))
            memory.store_extraction(conn, conv_id, ex)
    except Exception as e:  # noqa: BLE001 - surface any failure to the UI
        _set_status(conv_id, "error", f"{type(e).__name__}: {e}")
        traceback.print_exc()


def reprocess(conv_id: int) -> None:
    process_conversation(conv_id)
