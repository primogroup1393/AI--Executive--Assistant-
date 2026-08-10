"""
AI search / chat over the business memory (a grounded RAG loop).

Guarantees the user asked for:
  * answers are based on stored conversations, not model imagination,
  * every claim links back to a source conversation,
  * the system says "I don't have that" instead of inventing,
  * facts from conversations are separated from AI interpretation.
"""
from __future__ import annotations

import re
from typing import Any

from . import db
from .providers.llm import get_llm

CHAT_SYSTEM = """You are the CEO's AI business-memory assistant. You answer ONLY from the
provided CONTEXT, which is extracted from the CEO's real recorded conversations.

Rules:
- Base every statement on the CONTEXT. Do NOT use outside knowledge or guess.
- When you state a fact, cite the source conversation id like [#12]. Multiple ok: [#12][#7].
- If the CONTEXT does not contain the answer, say clearly that it is not in the records.
  Do not fabricate names, numbers, dates, or commitments.
- Separate FACTS (things stated in conversations) from INTERPRETATION (your reasoning).
  If you interpret or infer, label it explicitly as "Interpretation:".
- Be concise and executive. The reader is a busy CEO.
- Answer in the language the user asked in (English or Persian)."""


def _candidate_conversations(query: str, limit: int = 8) -> list[dict[str, Any]]:
    rows = db.fts_search(query, limit=40)
    conv_ids: list[int] = []
    seen = set()
    for r in rows:
        cid = r["conversation_id"]
        if cid and cid not in seen:
            seen.add(cid)
            conv_ids.append(cid)
        if len(conv_ids) >= limit:
            break
    # If FTS found nothing (e.g. very short query), fall back to recent convs.
    if not conv_ids:
        conv_ids = [r["id"] for r in db.q(
            "SELECT id FROM conversations WHERE status='done' "
            "ORDER BY COALESCE(occurred_at,created_at) DESC LIMIT ?", (limit,))]
    out = []
    for cid in conv_ids:
        c = db.q1("SELECT id,title,occurred_at,created_at,summary FROM conversations WHERE id=?", (cid,))
        if not c:
            continue
        items = db.q("SELECT kind,content,owner,due_date,source_quote,status "
                     "FROM items WHERE conversation_id=? ORDER BY kind", (cid,))
        people = db.q("SELECT p.name FROM people p JOIN conv_people cp ON cp.person_id=p.id "
                      "WHERE cp.conversation_id=?", (cid,))
        out.append({"conv": dict(c), "items": [dict(i) for i in items],
                    "people": [p["name"] for p in people]})
    return out


def _build_context(cands: list[dict[str, Any]], max_chars: int = 12000) -> str:
    blocks = []
    for cand in cands:
        c = cand["conv"]
        when = c.get("occurred_at") or c.get("created_at") or ""
        lines = [f"### Conversation [#{c['id']}] — {c['title']} ({when})",
                 f"People: {', '.join(cand['people']) or 'unknown'}",
                 f"Summary: {(c.get('summary') or '').strip()[:800]}"]
        if cand["items"]:
            lines.append("Extracted items:")
            for it in cand["items"][:25]:
                due = f" (due {it['due_date']})" if it.get("due_date") else ""
                q = f'  quote: "{it["source_quote"]}"' if it.get("source_quote") else ""
                lines.append(f"- [{it['kind']}|{it.get('owner') or ''}|{it.get('status')}] "
                             f"{it['content']}{due}{q}")
        blocks.append("\n".join(lines))
    ctx = "\n\n".join(blocks)
    return ctx[:max_chars]


def chat(query: str) -> dict[str, Any]:
    cands = _candidate_conversations(query)
    if not cands:
        return {"answer": "I don't have any conversations recorded yet, so there's nothing to "
                          "search. Add a conversation first.", "sources": []}
    context = _build_context(cands)
    user = f"CONTEXT:\n{context}\n\n---\nCEO QUESTION: {query}\n\nAnswer, citing [#id] sources."
    answer = get_llm().complete(CHAT_SYSTEM, user, max_tokens=1500, temperature=0.1)
    cited = sorted({int(m) for m in re.findall(r"#(\d+)", answer)})
    source_ids = cited or [c["conv"]["id"] for c in cands[:3]]
    sources = []
    for sid in source_ids:
        c = db.q1("SELECT id,title,occurred_at,created_at FROM conversations WHERE id=?", (sid,))
        if c:
            sources.append(dict(c))
    return {"answer": answer, "sources": sources}
