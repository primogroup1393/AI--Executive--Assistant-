"""
AI Executive Assistant — FastAPI application.

Serves the CEO dashboard (server-rendered, premium UI) plus a small JSON API
for uploads, chat, briefings and item actions. Heavy work (transcription +
extraction) runs in a background thread pool so the UI stays instant.
"""
from __future__ import annotations

import datetime as dt
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, Form, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import auth, briefing, config, db, memory, pipeline, search
from .providers.llm import get_llm
from .providers.transcription import get_transcriber

BASE = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
_executor = ThreadPoolExecutor(max_workers=2)

app = FastAPI(title="AI Executive Assistant")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

COOKIE = "ceo_session"


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    auth.init_auth()
    banner = [
        "",
        "=" * 64,
        "  AI Executive Assistant is running.",
        f"  Mode:            {config.MODE}",
        f"  Data dir:        {config.DATA_DIR}",
        f"  LLM provider:    {get_llm().name}",
        f"  Transcription:   {get_transcriber().name}",
        f"  Full-text search:{'FTS5' if db.HAS_FTS5 else 'LIKE (fallback)'}",
    ]
    if auth.generated_password:
        banner += ["",
                   "  No APP_PASSWORD was set, so a login password was generated:",
                   f"      ===>  {auth.generated_password}  <===",
                   "  (Set APP_PASSWORD in backend/.env to choose your own.)"]
    banner += ["=" * 64, ""]
    print("\n".join(banner))


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def _logged_in(request: Request) -> bool:
    return auth.valid_session(request.cookies.get(COOKIE))


def _require(request: Request) -> None:
    if not _logged_in(request):
        raise HTTPException(status_code=401, detail="Not authenticated")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if _logged_in(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, password: str = Form(...)):
    if auth.check_password(password):
        resp = RedirectResponse("/", status_code=302)
        resp.set_cookie(COOKIE, auth.issue_session(), httponly=True, samesite="lax",
                        max_age=config.SESSION_TTL_SECONDS)
        return resp
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": "Incorrect password."},
        status_code=401)


@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(COOKIE)
    return resp


# ---------------------------------------------------------------------------
# Dashboard & pages
# ---------------------------------------------------------------------------
def _guard(request: Request):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=302)
    return None


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    if (r := _guard(request)):
        return r
    data = _dashboard_data()
    return templates.TemplateResponse("dashboard.html", {"request": request, **data})


def _dashboard_data() -> dict:
    today = dt.date.today().isoformat()
    todays = db.q(
        "SELECT * FROM conversations WHERE date(COALESCE(occurred_at,created_at))=? "
        "ORDER BY created_at DESC", (today,))
    recent_convs = db.q(
        "SELECT * FROM conversations ORDER BY created_at DESC LIMIT 8")
    recent_people = db.q(
        "SELECT p.*, c.name AS company_name FROM people p LEFT JOIN companies c ON c.id=p.company_id "
        "ORDER BY p.created_at DESC LIMIT 8")
    recent_companies = db.q("SELECT * FROM companies ORDER BY created_at DESC LIMIT 8")
    open_commitments = db.q(
        "SELECT i.*, c.title AS conv_title, p.name AS person_name FROM items i "
        "LEFT JOIN conversations c ON c.id=i.conversation_id "
        "LEFT JOIN people p ON p.id=i.person_id "
        "WHERE i.kind IN ('my_commitment','their_commitment') AND i.status='open' "
        "ORDER BY i.created_at DESC LIMIT 12")
    follow_ups = db.q(
        "SELECT i.*, c.title AS conv_title, p.name AS person_name FROM items i "
        "LEFT JOIN conversations c ON c.id=i.conversation_id "
        "LEFT JOIN people p ON p.id=i.person_id "
        "WHERE i.kind IN ('action_item','followup') AND i.status='open' "
        "ORDER BY i.created_at DESC LIMIT 12")
    decisions = db.q(
        "SELECT i.*, c.title AS conv_title FROM items i LEFT JOIN conversations c "
        "ON c.id=i.conversation_id WHERE i.kind='decision' ORDER BY i.created_at DESC LIMIT 8")
    deadlines = db.q(
        "SELECT i.*, c.title AS conv_title FROM items i LEFT JOIN conversations c "
        "ON c.id=i.conversation_id WHERE i.kind IN ('deadline','date') AND i.due_date IS NOT NULL "
        "AND i.status='open' ORDER BY i.due_date ASC LIMIT 10")
    attention = db.q(
        "SELECT i.*, c.title AS conv_title FROM items i LEFT JOIN conversations c "
        "ON c.id=i.conversation_id WHERE i.kind IN ('risk','open_issue','question_next') "
        "AND i.status='open' ORDER BY i.created_at DESC LIMIT 10")
    counts = {
        "conversations": db.q1("SELECT COUNT(*) n FROM conversations")["n"],
        "people": db.q1("SELECT COUNT(*) n FROM people")["n"],
        "companies": db.q1("SELECT COUNT(*) n FROM companies")["n"],
        "open_items": db.q1("SELECT COUNT(*) n FROM items WHERE status='open'")["n"],
    }
    return {
        "counts": counts,
        "todays": [dict(r) for r in todays],
        "recent_convs": [dict(r) for r in recent_convs],
        "recent_people": [dict(r) for r in recent_people],
        "recent_companies": [dict(r) for r in recent_companies],
        "open_commitments": [dict(r) for r in open_commitments],
        "follow_ups": [dict(r) for r in follow_ups],
        "decisions": [dict(r) for r in decisions],
        "deadlines": [dict(r) for r in deadlines],
        "attention": [dict(r) for r in attention],
        "provider": get_llm().name,
        "transcriber": get_transcriber().name,
    }


@app.get("/conversations", response_class=HTMLResponse)
def conversations_page(request: Request):
    if (r := _guard(request)):
        return r
    rows = db.q("SELECT c.*, (SELECT COUNT(*) FROM items WHERE conversation_id=c.id) AS n_items "
                "FROM conversations c ORDER BY c.created_at DESC")
    return templates.TemplateResponse("conversations.html",
                                      {"request": request, "conversations": [dict(r) for r in rows]})


@app.get("/conversation/{cid}", response_class=HTMLResponse)
def conversation_page(request: Request, cid: int):
    if (r := _guard(request)):
        return r
    conv = db.q1("SELECT * FROM conversations WHERE id=?", (cid,))
    if not conv:
        raise HTTPException(404)
    items = db.q("SELECT i.*, p.name AS person_name, co.name AS company_name FROM items i "
                 "LEFT JOIN people p ON p.id=i.person_id LEFT JOIN companies co ON co.id=i.company_id "
                 "WHERE i.conversation_id=? ORDER BY i.kind", (cid,))
    segments = db.q("SELECT * FROM transcript_segments WHERE conversation_id=? ORDER BY idx", (cid,))
    people = db.q("SELECT p.id,p.name FROM people p JOIN conv_people cp ON cp.person_id=p.id "
                  "WHERE cp.conversation_id=?", (cid,))
    companies = db.q("SELECT co.id,co.name FROM companies co JOIN conv_companies cc "
                     "ON cc.company_id=co.id WHERE cc.conversation_id=?", (cid,))
    grouped: dict[str, list] = {}
    for it in items:
        grouped.setdefault(it["kind"], []).append(dict(it))
    return templates.TemplateResponse("conversation.html", {
        "request": request, "conv": dict(conv), "grouped": grouped,
        "segments": [dict(s) for s in segments],
        "people": [dict(p) for p in people], "companies": [dict(c) for c in companies]})


@app.get("/people", response_class=HTMLResponse)
def people_page(request: Request):
    if (r := _guard(request)):
        return r
    rows = db.q(
        "SELECT p.*, c.name AS company_name, "
        "(SELECT COUNT(*) FROM conv_people WHERE person_id=p.id) AS n_convs, "
        "(SELECT COUNT(*) FROM items WHERE person_id=p.id AND status='open') AS n_open "
        "FROM people p LEFT JOIN companies c ON c.id=p.company_id ORDER BY p.name")
    return templates.TemplateResponse("people.html",
                                      {"request": request, "people": [dict(r) for r in rows]})


@app.get("/person/{pid}", response_class=HTMLResponse)
def person_page(request: Request, pid: int):
    if (r := _guard(request)):
        return r
    profile = memory.person_profile(pid)
    if not profile:
        raise HTTPException(404)
    return templates.TemplateResponse("profile.html",
                                      {"request": request, "profile": profile, "kind": "person"})


@app.get("/companies", response_class=HTMLResponse)
def companies_page(request: Request):
    if (r := _guard(request)):
        return r
    rows = db.q(
        "SELECT c.*, (SELECT COUNT(*) FROM conv_companies WHERE company_id=c.id) AS n_convs, "
        "(SELECT COUNT(*) FROM people WHERE company_id=c.id) AS n_people "
        "FROM companies c ORDER BY c.name")
    return templates.TemplateResponse("companies.html",
                                      {"request": request, "companies": [dict(r) for r in rows]})


@app.get("/company/{cid}", response_class=HTMLResponse)
def company_page(request: Request, cid: int):
    if (r := _guard(request)):
        return r
    profile = memory.company_profile(cid)
    if not profile:
        raise HTTPException(404)
    return templates.TemplateResponse("profile.html",
                                      {"request": request, "profile": profile, "kind": "company"})


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------
@app.post("/api/conversations")
async def api_create_conversation(
    request: Request,
    title: str = Form(""),
    source: str = Form("upload"),
    occurred_at: str = Form(""),
    transcript: str = Form(""),
    consent_ack: str = Form("false"),
    audio: UploadFile | None = File(None),
):
    _require(request)
    audio_rel = None
    if audio is not None and audio.filename:
        ext = Path(audio.filename).suffix or ".bin"
        fname = f"{uuid.uuid4().hex}{ext}"
        dest = config.AUDIO_DIR / fname
        content = await audio.read()
        dest.write_bytes(content)
        audio_rel = f"audio/{fname}"

    if not audio_rel and not transcript.strip():
        raise HTTPException(400, "Provide an audio file or a transcript.")

    cid = pipeline.create_conversation(
        title=title.strip(), source=source, occurred_at=occurred_at or None,
        audio_path=audio_rel, transcript=transcript.strip() or None,
        consent_ack=(consent_ack.lower() == "true"))
    _executor.submit(pipeline.process_conversation, cid)
    return {"id": cid, "status": "processing"}


@app.get("/api/conversations/{cid}/status")
def api_status(request: Request, cid: int):
    _require(request)
    row = db.q1("SELECT id,status,error,title FROM conversations WHERE id=?", (cid,))
    if not row:
        raise HTTPException(404)
    return dict(row)


@app.post("/api/conversations/{cid}/reprocess")
def api_reprocess(request: Request, cid: int):
    _require(request)
    if not db.q1("SELECT 1 FROM conversations WHERE id=?", (cid,)):
        raise HTTPException(404)
    _executor.submit(pipeline.process_conversation, cid)
    return {"id": cid, "status": "processing"}


@app.delete("/api/conversations/{cid}")
def api_delete_conversation(request: Request, cid: int):
    _require(request)
    conv = db.q1("SELECT audio_path FROM conversations WHERE id=?", (cid,))
    if not conv:
        raise HTTPException(404)
    with db.tx() as conn:
        db.clear_index_for_conv(conn, cid)
        conn.execute("DELETE FROM conversations WHERE id=?", (cid,))
    if conv["audio_path"]:
        try:
            (config.DATA_DIR / conv["audio_path"]).unlink(missing_ok=True)
        except OSError:
            pass
    return {"deleted": cid}


@app.post("/api/items/{item_id}")
def api_update_item(request: Request, item_id: int, status: str = Form(...)):
    _require(request)
    if status not in ("open", "done", "dismissed"):
        raise HTTPException(400, "bad status")
    with db.tx() as conn:
        conn.execute("UPDATE items SET status=? WHERE id=?", (status, item_id))
    return {"id": item_id, "status": status}


@app.post("/api/chat")
async def api_chat(request: Request):
    _require(request)
    body = await request.json()
    query = (body.get("query") or "").strip()
    if not query:
        raise HTTPException(400, "empty query")
    result = search.chat(query)
    return JSONResponse(result)


@app.get("/api/briefing/person/{pid}")
def api_briefing_person(request: Request, pid: int):
    _require(request)
    result = briefing.briefing_for_person(pid)
    if not result:
        raise HTTPException(404)
    return {"briefing": result["briefing"]}


@app.get("/api/briefing/company/{cid}")
def api_briefing_company(request: Request, cid: int):
    _require(request)
    result = briefing.briefing_for_company(cid)
    if not result:
        raise HTTPException(404)
    return {"briefing": result["briefing"]}


@app.get("/api/audio/{cid}")
def api_audio(request: Request, cid: int):
    _require(request)
    conv = db.q1("SELECT audio_path FROM conversations WHERE id=?", (cid,))
    if not conv or not conv["audio_path"]:
        raise HTTPException(404)
    path = config.DATA_DIR / conv["audio_path"]
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/healthz")
def healthz():
    return {"ok": True, "llm": get_llm().name, "transcriber": get_transcriber().name}
