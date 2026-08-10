"""
Pre-call CEO briefing. Given a person (or company), assemble a 30-60 second
briefing so the CEO instantly recovers full context before a conversation.

The structured profile is deterministic (straight from the database). The LLM
then writes a tight narrative briefing + suggested talking points from that
profile only, so it stays grounded.
"""
from __future__ import annotations

from typing import Any

from . import memory
from .providers.llm import get_llm

BRIEF_SYSTEM = """You write a pre-call executive briefing for a CEO who is about to speak
with a contact. Use ONLY the structured profile provided. Do not invent facts.

Output concise markdown the CEO can read in ~45 seconds:
- **Who**: one line (name, role, company).
- **Where we left off**: last conversation and its key point.
- **Their open commitments to me** / **My open commitments to them**: bullets (omit if none).
- **Open action items & issues**: bullets (omit if empty).
- **Deadlines / dates to watch**: bullets (omit if none).
- **Remember**: 1-3 durable facts about the relationship.
- **Suggested topics / questions for this call**: 3-5 sharp bullets, including any
  unanswered questions from last time.
If a section has no data, omit it entirely. Match the contact's likely language
(Persian names/topics -> you may write in Persian)."""


def _profile_to_text(profile: dict[str, Any], kind: str) -> str:
    if kind == "person":
        p = profile["person"]
        head = f"Name: {p['name']}\nRole: {p.get('role') or '-'}\nCompany: {p.get('company_name') or '-'}"
    else:
        c = profile["company"]
        head = f"Company: {c['name']}\nPeople: " + ", ".join(x["name"] for x in profile.get("people", []))
    lines = [head, ""]
    convs = profile.get("conversations", [])
    lines.append(f"Total conversations: {len(convs)}")
    if convs:
        last = convs[0]
        when = last.get("occurred_at") or last.get("created_at")
        lines.append(f"Last conversation [#{last['id']}] ({when}): {last['title']}")
        if last.get("summary"):
            lines.append(f"  Summary: {last['summary'][:600]}")

    def dump(label, arr):
        if arr:
            lines.append(f"\n{label}:")
            for it in arr[:8]:
                due = f" (due {it['due_date']})" if it.get("due_date") else ""
                lines.append(f"- {it['content']}{due} [#{it.get('conversation_id')}]")

    dump("Their commitments to me", profile.get("their_commitments"))
    dump("My commitments to them", profile.get("my_commitments"))
    dump("Open action items / follow-ups", profile.get("open_actions"))
    dump("Open issues", profile.get("open_issues"))
    dump("Decisions", profile.get("decisions"))
    dump("Deadlines / dates", profile.get("deadlines"))
    dump("Questions to ask next time", profile.get("questions_next"))
    dump("Risks", profile.get("risks"))
    if profile.get("facts"):
        lines.append("\nDurable facts:")
        for f in profile["facts"][:10]:
            lines.append(f"- {f['fact']}")
    return "\n".join(lines)


def briefing_for_person(person_id: int) -> dict[str, Any] | None:
    profile = memory.person_profile(person_id)
    if not profile:
        return None
    profile_text = _profile_to_text(profile, "person")
    md = get_llm().complete(BRIEF_SYSTEM, "PROFILE:\n" + profile_text,
                            max_tokens=1200, temperature=0.2)
    return {"profile": profile, "briefing": md}


def briefing_for_company(company_id: int) -> dict[str, Any] | None:
    profile = memory.company_profile(company_id)
    if not profile:
        return None
    profile_text = _profile_to_text(profile, "company")
    md = get_llm().complete(BRIEF_SYSTEM, "PROFILE:\n" + profile_text,
                            max_tokens=1200, temperature=0.2)
    return {"profile": profile, "briefing": md}
