"""
Long-term memory: resolve people/companies, persist extracted knowledge, and
assemble the per-person / per-company profiles that make this a "second brain"
rather than a pile of isolated transcripts.
"""
from __future__ import annotations

from typing import Any

from . import db


# --- entity resolution -----------------------------------------------------

def resolve_company(conn, name: str) -> int | None:
    name = (name or "").strip()
    if not name:
        return None
    row = conn.execute("SELECT id FROM companies WHERE lower(name)=lower(?)", (name,)).fetchone()
    if row:
        return row["id"]
    # alias match
    row = conn.execute(
        "SELECT id FROM companies WHERE aliases IS NOT NULL AND "
        "instr(lower(','||aliases||','), lower(?)) > 0", (f",{name},",)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO companies(name) VALUES (?)", (name,))
    return cur.lastrowid


def resolve_person(conn, name: str, *, company_id: int | None = None,
                   role: str | None = None) -> int | None:
    name = (name or "").strip()
    if not name:
        return None
    row = conn.execute("SELECT id, company_id FROM people WHERE lower(name)=lower(?)", (name,)).fetchone()
    if row:
        if company_id and not row["company_id"]:
            conn.execute("UPDATE people SET company_id=? WHERE id=?", (company_id, row["id"]))
        return row["id"]
    row = conn.execute(
        "SELECT id FROM people WHERE aliases IS NOT NULL AND "
        "instr(lower(','||aliases||','), lower(?)) > 0", (f",{name},",)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO people(name, company_id, role) VALUES (?,?,?)",
        (name, company_id, role))
    return cur.lastrowid


# --- persist a full extraction --------------------------------------------

def store_extraction(conn, conversation_id: int, ex: dict[str, Any]) -> None:
    """Persist people, companies, links, items and facts; refresh search index."""
    db.clear_index_for_conv(conn, conversation_id)
    conn.execute("DELETE FROM items WHERE conversation_id=?", (conversation_id,))

    # companies first (people reference them)
    name_to_company: dict[str, int] = {}
    for c in ex.get("companies", []):
        cid = resolve_company(conn, c["name"])
        if cid:
            name_to_company[c["name"].lower()] = cid
            _link(conn, "conv_companies", conversation_id, "company_id", cid, "mentioned")
            if c.get("note"):
                _add_fact(conn, company_id=cid, fact=c["note"], source=conversation_id)

    # people
    name_to_person: dict[str, int] = {}
    for p in ex.get("people", []):
        comp_id = name_to_company.get((p.get("company") or "").lower())
        if not comp_id and p.get("company"):
            comp_id = resolve_company(conn, p["company"])
        pid = resolve_person(conn, p["name"], company_id=comp_id,
                             role=p.get("role"))
        if pid:
            name_to_person[p["name"].lower()] = pid
            _link(conn, "conv_people", conversation_id, "person_id", pid,
                  p.get("role") or "mentioned")
            if p.get("note"):
                _add_fact(conn, person_id=pid, fact=p["note"], source=conversation_id)

    # items
    for it in ex.get("items", []):
        pid = name_to_person.get((it.get("person") or "").lower())
        if not pid and it.get("person"):
            pid = resolve_person(conn, it["person"])
        cid = name_to_company.get((it.get("company") or "").lower())
        if not cid and it.get("company"):
            cid = resolve_company(conn, it["company"])
        cur = conn.execute(
            "INSERT INTO items(conversation_id,kind,content,owner,person_id,company_id,"
            "due_date,confidence,source_quote) VALUES (?,?,?,?,?,?,?,?,?)",
            (conversation_id, it["kind"], it["content"], it.get("owner"),
             pid, cid, it.get("due_date"), it.get("confidence"),
             it.get("source_quote")))
        db.index_text(conn, conversation_id=conversation_id, item_id=cur.lastrowid,
                      kind=it["kind"], body=it["content"] + " " + (it.get("source_quote") or ""))

    # durable relationship facts
    for f in ex.get("facts", []):
        pid = name_to_person.get((f.get("about_person") or "").lower())
        if not pid and f.get("about_person"):
            pid = resolve_person(conn, f["about_person"])
        cid = name_to_company.get((f.get("about_company") or "").lower())
        if not cid and f.get("about_company"):
            cid = resolve_company(conn, f["about_company"])
        if pid or cid:
            _add_fact(conn, person_id=pid, company_id=cid, fact=f["fact"], source=conversation_id)

    # index the summary + transcript for search
    conv = conn.execute("SELECT summary, transcript FROM conversations WHERE id=?",
                        (conversation_id,)).fetchone()
    if conv:
        body = (conv["summary"] or "") + "\n" + (conv["transcript"] or "")
        db.index_text(conn, conversation_id=conversation_id, item_id=None,
                      kind="conversation", body=body)


def _link(conn, table: str, conv_id: int, col: str, val: int, role: str) -> None:
    conn.execute(
        f"INSERT OR IGNORE INTO {table}(conversation_id,{col},role) VALUES (?,?,?)",
        (conv_id, val, role))


def _add_fact(conn, *, person_id: int | None = None, company_id: int | None = None,
              fact: str, source: int | None = None) -> None:
    # de-dupe identical facts for the same entity
    exists = conn.execute(
        "SELECT 1 FROM memory_facts WHERE fact=? AND "
        "IFNULL(person_id,0)=IFNULL(?,0) AND IFNULL(company_id,0)=IFNULL(?,0)",
        (fact, person_id, company_id)).fetchone()
    if exists:
        return
    conn.execute(
        "INSERT INTO memory_facts(person_id,company_id,fact,source_conv) VALUES (?,?,?,?)",
        (person_id, company_id, fact, source))


# --- profiles --------------------------------------------------------------

def person_profile(person_id: int) -> dict[str, Any] | None:
    p = db.q1("SELECT p.*, c.name AS company_name FROM people p "
              "LEFT JOIN companies c ON c.id=p.company_id WHERE p.id=?", (person_id,))
    if not p:
        return None
    convs = db.q(
        "SELECT c.id,c.title,c.occurred_at,c.created_at,c.source,c.summary "
        "FROM conversations c JOIN conv_people cp ON cp.conversation_id=c.id "
        "WHERE cp.person_id=? ORDER BY COALESCE(c.occurred_at,c.created_at) DESC", (person_id,))
    return {
        "person": dict(p),
        "conversations": [dict(r) for r in convs],
        "facts": [dict(r) for r in db.q(
            "SELECT * FROM memory_facts WHERE person_id=? ORDER BY created_at DESC", (person_id,))],
        "my_commitments": _items(person_id=person_id, kinds=["my_commitment"]),
        "their_commitments": _items(person_id=person_id, kinds=["their_commitment"]),
        "open_actions": _items(person_id=person_id, kinds=["action_item", "followup"], status="open"),
        "open_issues": _items(person_id=person_id, kinds=["open_issue"], status="open"),
        "decisions": _items(person_id=person_id, kinds=["decision"]),
        "deadlines": _items(person_id=person_id, kinds=["deadline", "date"]),
        "questions_next": _items(person_id=person_id, kinds=["question_next"]),
        "risks": _items(person_id=person_id, kinds=["risk"]),
    }


def company_profile(company_id: int) -> dict[str, Any] | None:
    c = db.q1("SELECT * FROM companies WHERE id=?", (company_id,))
    if not c:
        return None
    convs = db.q(
        "SELECT DISTINCT c.id,c.title,c.occurred_at,c.created_at,c.source,c.summary "
        "FROM conversations c JOIN conv_companies cc ON cc.conversation_id=c.id "
        "WHERE cc.company_id=? ORDER BY COALESCE(c.occurred_at,c.created_at) DESC", (company_id,))
    people = db.q("SELECT id,name,role FROM people WHERE company_id=? ORDER BY name", (company_id,))
    return {
        "company": dict(c),
        "people": [dict(r) for r in people],
        "conversations": [dict(r) for r in convs],
        "facts": [dict(r) for r in db.q(
            "SELECT * FROM memory_facts WHERE company_id=? ORDER BY created_at DESC", (company_id,))],
        "my_commitments": _items(company_id=company_id, kinds=["my_commitment"]),
        "their_commitments": _items(company_id=company_id, kinds=["their_commitment"]),
        "open_actions": _items(company_id=company_id, kinds=["action_item", "followup"], status="open"),
        "open_issues": _items(company_id=company_id, kinds=["open_issue"], status="open"),
        "decisions": _items(company_id=company_id, kinds=["decision"]),
    }


def _items(*, person_id: int | None = None, company_id: int | None = None,
           kinds: list[str], status: str | None = None) -> list[dict]:
    clauses, params = [], []
    if person_id:
        clauses.append("person_id=?"); params.append(person_id)
    if company_id:
        clauses.append("company_id=?"); params.append(company_id)
    placeholders = ",".join("?" for _ in kinds)
    clauses.append(f"kind IN ({placeholders})"); params.extend(kinds)
    if status:
        clauses.append("status=?"); params.append(status)
    sql = ("SELECT i.*, c.title AS conv_title, c.occurred_at AS conv_when "
           "FROM items i LEFT JOIN conversations c ON c.id=i.conversation_id "
           "WHERE " + " AND ".join(clauses) + " ORDER BY i.created_at DESC")
    return [dict(r) for r in db.q(sql, params)]
