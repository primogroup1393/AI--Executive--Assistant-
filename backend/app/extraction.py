"""
Turn a raw transcript into structured executive knowledge using the LLM.

The output is a single JSON object so it maps cleanly onto the database. The
prompt is engineered to:
  * work in English, Persian, and mixed Persian/English,
  * separate MY commitments from THEIR commitments,
  * ground every item in a source quote for later verification,
  * never invent facts (empty arrays instead of guesses).
"""
from __future__ import annotations

from typing import Any

from .providers.llm import get_llm

ITEM_KINDS = [
    "topic", "decision", "my_commitment", "their_commitment", "action_item",
    "followup", "deadline", "date", "amount", "open_issue", "question_next",
    "risk", "highlight",
]

EXTRACTION_SYSTEM = """You are the analytical core of an AI Executive Assistant for a CEO.
You read a transcript of a business conversation (call, meeting, or voice note) and
return JSON only. No prose, no markdown fences.

The transcript may be in English, Persian (Farsi), or a mix of both. Understand all of
them. Keep proper nouns (people, companies, products) in their original script.

CRITICAL RULES:
- Extract only what is actually supported by the transcript. Never invent names,
  numbers, dates, or commitments. If something is not present, use an empty array.
- Distinguish the CEO ("me"/"I"/first person / the owner of this assistant) from
  the other participants. Commitments the CEO makes -> kind "my_commitment".
  Commitments others make -> kind "their_commitment".
- For every item include a short verbatim "source_quote" copied from the transcript
  that supports it (in the original language). This is used for verification.
- "confidence" is 0.0-1.0: how sure you are the item is real and correctly categorized.
- Dates: normalize to ISO (YYYY-MM-DD) in "due_date" when a concrete date/deadline
  is stated or clearly implied; otherwise omit due_date.

Return a JSON object with EXACTLY these keys:
{
  "title": "<=8 word title of the conversation",
  "language": "en" | "fa" | "mixed",
  "summary": "Executive summary in markdown, readable in under 60 seconds. Cover: what
              happened, what was discussed, what was decided, what needs the CEO's
              attention. Use short bullet points. Write it in the same primary language
              as the conversation.",
  "people": [ {"name": "...", "role": "participant"|"mentioned", "company": "<company name or empty>", "note": "<one durable fact about them from this talk, or empty>"} ],
  "companies": [ {"name": "...", "note": "<one durable fact, or empty>"} ],
  "items": [
     {"kind": one of """ + ", ".join(f'"{k}"' for k in ITEM_KINDS) + """,
      "content": "clear, self-contained statement of the item",
      "owner": "me" | "them" | "<person name>" | "",
      "person": "<related person name or empty>",
      "company": "<related company name or empty>",
      "due_date": "YYYY-MM-DD or empty",
      "source_quote": "verbatim supporting quote",
      "confidence": 0.0-1.0 }
  ],
  "facts": [ {"about_person":"<name or empty>","about_company":"<name or empty>","fact":"durable relationship fact worth remembering long-term"} ]
}

Cover these item kinds when present: main topics, decisions made, the CEO's commitments,
other people's commitments, action items, follow-ups, deadlines, important dates,
important numbers/amounts, people mentioned, companies mentioned, unresolved/open issues,
questions the CEO should ask next time, potential risks or sensitive issues, and other
important information that may become relevant later (kind "highlight")."""


def extract(transcript: str, *, source: str = "upload",
            known_people: list[str] | None = None) -> dict[str, Any]:
    """Run structured extraction. Returns a normalized dict (never raises on
    a well-formed-but-partial model response)."""
    context = ""
    if known_people:
        context = ("Known contacts (reuse these exact names if they appear): "
                   + ", ".join(known_people[:60]) + "\n\n")
    user = (
        f"{context}Conversation source: {source}.\n\n"
        "Analyze the following and return the JSON object described.\n\n"
        "--- TRANSCRIPT ---\n" + transcript
    )
    llm = get_llm()
    data = llm.complete_json(EXTRACTION_SYSTEM, user, max_tokens=4000)
    return _normalize(data)


def _normalize(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        data = {}
    out: dict[str, Any] = {
        "title": str(data.get("title") or "Conversation")[:120],
        "language": (data.get("language") or "unknown"),
        "summary": data.get("summary") or "",
        "people": [],
        "companies": [],
        "items": [],
        "facts": [],
    }
    for p in data.get("people") or []:
        if isinstance(p, dict) and p.get("name"):
            out["people"].append({
                "name": str(p["name"]).strip()[:120],
                "role": p.get("role") or "mentioned",
                "company": (p.get("company") or "").strip(),
                "note": (p.get("note") or "").strip(),
            })
    for c in data.get("companies") or []:
        if isinstance(c, dict) and c.get("name"):
            out["companies"].append({
                "name": str(c["name"]).strip()[:120],
                "note": (c.get("note") or "").strip(),
            })
    for it in data.get("items") or []:
        if not isinstance(it, dict) or not it.get("content"):
            continue
        kind = it.get("kind") if it.get("kind") in ITEM_KINDS else "highlight"
        out["items"].append({
            "kind": kind,
            "content": str(it["content"]).strip(),
            "owner": (it.get("owner") or "").strip(),
            "person": (it.get("person") or "").strip(),
            "company": (it.get("company") or "").strip(),
            "due_date": (it.get("due_date") or "").strip() or None,
            "source_quote": (it.get("source_quote") or "").strip(),
            "confidence": _clamp(it.get("confidence")),
        })
    for f in data.get("facts") or []:
        if isinstance(f, dict) and f.get("fact"):
            out["facts"].append({
                "about_person": (f.get("about_person") or "").strip(),
                "about_company": (f.get("about_company") or "").strip(),
                "fact": str(f["fact"]).strip(),
            })
    return out


def _clamp(v: Any) -> float:
    try:
        x = float(v)
        return max(0.0, min(1.0, x))
    except (TypeError, ValueError):
        return 0.5
