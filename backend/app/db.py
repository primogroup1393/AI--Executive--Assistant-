"""
SQLite data layer. One file, you own it, easy to encrypt/back up.

Schema overview
---------------
conversations         one row per captured conversation (call/meeting/note)
transcript_segments   diarized transcript lines (speaker + timestamps + text)
people                intelligent profile per person
companies             intelligent profile per company
conv_people           conversation <-> person link (participants/mentions)
conv_companies        conversation <-> company link
items                 every extracted piece of executive knowledge
                      (decision, commitment, action item, deadline, risk, ...)
memory_facts          durable facts about a person/company (relationship memory)

Full-text search is provided by FTS5 when available (it ships with the
SQLite that Python bundles on all mainstream platforms); we degrade to LIKE
queries if a build lacks it, so the app always runs.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterable

from .config import DB_PATH

_local = threading.local()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _connect()
        _local.conn = conn
    return conn


@contextmanager
def tx():
    """Transaction context manager."""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


HAS_FTS5 = False


def _detect_fts5(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(x);")
        conn.execute("DROP TABLE IF EXISTS _fts_probe;")
        return True
    except sqlite3.OperationalError:
        return False


SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL DEFAULT 'Untitled conversation',
    source        TEXT NOT NULL DEFAULT 'upload',   -- phone|whatsapp|in_person|online|voice_note|upload
    occurred_at   TEXT,                             -- ISO8601 (when the conversation happened)
    language      TEXT,                             -- detected: fa|en|mixed
    audio_path    TEXT,                             -- relative path under DATA_DIR/audio, if saved
    duration_sec  REAL,
    transcript    TEXT,                             -- full plain-text transcript
    summary       TEXT,                             -- executive summary (markdown)
    status        TEXT NOT NULL DEFAULT 'new',      -- new|transcribing|extracting|done|error
    error         TEXT,
    consent_ack   INTEGER NOT NULL DEFAULT 0,       -- user acknowledged recording consent
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    idx             INTEGER NOT NULL,
    speaker         TEXT,
    start_ms        INTEGER,
    end_ms          INTEGER,
    text            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_seg_conv ON transcript_segments(conversation_id);

CREATE TABLE IF NOT EXISTS people (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    aliases      TEXT,          -- comma separated alternate names
    role         TEXT,
    company_id   INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    notes        TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_people_name ON people(lower(name));

CREATE TABLE IF NOT EXISTS companies (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    aliases      TEXT,
    notes        TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_companies_name ON companies(lower(name));

CREATE TABLE IF NOT EXISTS conv_people (
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    person_id       INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    role            TEXT,      -- participant|mentioned
    PRIMARY KEY (conversation_id, person_id)
);

CREATE TABLE IF NOT EXISTS conv_companies (
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    company_id      INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    role            TEXT,
    PRIMARY KEY (conversation_id, company_id)
);

-- Every extracted unit of executive knowledge.
CREATE TABLE IF NOT EXISTS items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,     -- topic|decision|my_commitment|their_commitment|
                                       -- action_item|followup|deadline|date|amount|
                                       -- open_issue|question_next|risk|highlight
    content         TEXT NOT NULL,
    owner           TEXT,              -- me|them|<person name>
    person_id       INTEGER REFERENCES people(id) ON DELETE SET NULL,
    company_id      INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    due_date        TEXT,              -- ISO date if any
    status          TEXT NOT NULL DEFAULT 'open',  -- open|done|dismissed
    confidence      REAL,
    source_quote    TEXT,              -- grounding quote from transcript
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_items_conv ON items(conversation_id);
CREATE INDEX IF NOT EXISTS ix_items_kind ON items(kind);
CREATE INDEX IF NOT EXISTS ix_items_person ON items(person_id);
CREATE INDEX IF NOT EXISTS ix_items_company ON items(company_id);
CREATE INDEX IF NOT EXISTS ix_items_status ON items(status);

-- Durable relationship facts (long-term memory) about a person or company.
CREATE TABLE IF NOT EXISTS memory_facts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id    INTEGER REFERENCES people(id) ON DELETE CASCADE,
    company_id   INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    fact         TEXT NOT NULL,
    source_conv  INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_fact_person ON memory_facts(person_id);
CREATE INDEX IF NOT EXISTS ix_fact_company ON memory_facts(company_id);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
    conversation_id UNINDEXED,
    item_id UNINDEXED,
    kind UNINDEXED,
    body,
    tokenize = 'unicode61'
);
"""


def init_db() -> None:
    global HAS_FTS5
    conn = get_conn()
    conn.executescript(SCHEMA)
    HAS_FTS5 = _detect_fts5(conn)
    if HAS_FTS5:
        conn.executescript(FTS_SCHEMA)
    conn.commit()


# --- FTS helpers -----------------------------------------------------------

def index_text(conn: sqlite3.Connection, *, conversation_id: int | None,
               item_id: int | None, kind: str, body: str) -> None:
    if not HAS_FTS5 or not body:
        return
    conn.execute(
        "INSERT INTO search_index(conversation_id,item_id,kind,body) VALUES (?,?,?,?)",
        (conversation_id, item_id, kind, body),
    )


def clear_index_for_conv(conn: sqlite3.Connection, conversation_id: int) -> None:
    if not HAS_FTS5:
        return
    conn.execute("DELETE FROM search_index WHERE conversation_id=?", (conversation_id,))


def fts_search(query: str, limit: int = 40) -> list[sqlite3.Row]:
    conn = get_conn()
    if HAS_FTS5:
        # sanitize: FTS5 treats some chars specially; wrap tokens as a phrase-ish OR
        tokens = [t for t in _tokenize(query) if t]
        if not tokens:
            return []
        match = " OR ".join(f'"{t}"' for t in tokens)
        try:
            rows = conn.execute(
                "SELECT conversation_id, item_id, kind, body, rank "
                "FROM search_index WHERE search_index MATCH ? ORDER BY rank LIMIT ?",
                (match, limit),
            ).fetchall()
            return rows
        except sqlite3.OperationalError:
            pass
    # Fallback: LIKE across conversations + items
    like = f"%{query}%"
    rows = conn.execute(
        "SELECT id AS conversation_id, NULL AS item_id, 'conversation' AS kind, "
        "COALESCE(summary,'')||' '||COALESCE(transcript,'') AS body "
        "FROM conversations WHERE transcript LIKE ? OR summary LIKE ? LIMIT ?",
        (like, like, limit),
    ).fetchall()
    return rows


def _tokenize(text: str) -> list[str]:
    import re
    return re.findall(r"\w+", text.lower(), flags=re.UNICODE)


# --- small query helpers ---------------------------------------------------

def q(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return get_conn().execute(sql, tuple(params)).fetchall()


def q1(sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    return get_conn().execute(sql, tuple(params)).fetchone()
