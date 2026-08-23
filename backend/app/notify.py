"""
Post-call notifications: email the CEO an executive summary of each call.

Uses plain SMTP (stdlib) so it works with any provider (Gmail, Outlook, a
company mail server, SendGrid SMTP, etc.). If SMTP is not configured, we log
the summary instead of failing — the summary is always saved in the app too.
"""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from . import config, db


def _render_summary_email(conv: dict) -> tuple[str, str, str]:
    title = conv.get("title") or "Phone call"
    when = (conv.get("occurred_at") or conv.get("created_at") or "")[:16]
    summary = conv.get("summary") or "(no summary)"

    items = db.q(
        "SELECT kind, content, owner, due_date FROM items WHERE conversation_id=? "
        "ORDER BY kind", (conv["id"],))
    labels = {
        "decision": "Decisions", "my_commitment": "Your commitments",
        "their_commitment": "Their commitments", "action_item": "Action items",
        "followup": "Follow-ups", "deadline": "Deadlines", "open_issue": "Open issues",
        "question_next": "Ask next time", "risk": "Risks",
    }
    grouped: dict[str, list[str]] = {}
    for it in items:
        if it["kind"] in labels:
            due = f" (due {it['due_date']})" if it["due_date"] else ""
            grouped.setdefault(it["kind"], []).append(it["content"] + due)

    lines_txt = [f"{title}", f"{when}", "", summary, ""]
    lines_html = [f"<h2>{title}</h2><p style='color:#666'>{when}</p>",
                  f"<div style='white-space:pre-wrap'>{summary}</div>"]
    for k, lab in labels.items():
        if grouped.get(k):
            lines_txt.append(f"\n{lab}:")
            lines_html.append(f"<h3>{lab}</h3><ul>")
            for c in grouped[k]:
                lines_txt.append(f"  - {c}")
                lines_html.append(f"<li>{c}</li>")
            lines_html.append("</ul>")

    base = config.PUBLIC_BASE_URL or "http://localhost:8000"
    link = f"{base}/conversation/{conv['id']}"
    lines_txt.append(f"\nFull details: {link}")
    lines_html.append(f"<p><a href='{link}'>Open full conversation &amp; transcript</a></p>")

    subject = f"📞 Call summary: {title}"
    return subject, "\n".join(lines_txt), "".join(lines_html)


def send_call_summary(conversation_id: int) -> bool:
    conv = db.q1("SELECT * FROM conversations WHERE id=?", (conversation_id,))
    if not conv:
        return False
    conv = dict(conv)
    subject, body_txt, body_html = _render_summary_email(conv)

    if not config.email_enabled():
        print("\n[notify] Email not configured — summary follows:\n" + body_txt + "\n")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.SMTP_FROM
    msg["To"] = config.NOTIFY_EMAIL
    msg.set_content(body_txt)
    msg.add_alternative(f"<html><body style='font-family:sans-serif'>{body_html}</body></html>",
                        subtype="html")
    try:
        if config.SMTP_TLS:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as s:
                s.starttls(context=ctx)
                if config.SMTP_USER:
                    s.login(config.SMTP_USER, config.SMTP_PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as s:
                if config.SMTP_USER:
                    s.login(config.SMTP_USER, config.SMTP_PASSWORD)
                s.send_message(msg)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[notify] Failed to send summary email: {type(e).__name__}: {e}")
        return False
