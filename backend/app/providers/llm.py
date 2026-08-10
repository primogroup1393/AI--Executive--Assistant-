"""
LLM provider abstraction.

The rest of the app only ever calls `get_llm().complete(...)`. Swapping
providers (Anthropic today; a local model tomorrow) never touches business
logic. A mock provider keeps the whole product runnable with zero keys.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .. import config


class LLM:
    name = "base"
    available = False

    def complete(self, system: str, user: str, *, max_tokens: int = 2000,
                 temperature: float = 0.2) -> str:
        raise NotImplementedError

    def complete_json(self, system: str, user: str, *, max_tokens: int = 4000) -> Any:
        """Return parsed JSON. Robust to models that wrap JSON in prose/fences."""
        raw = self.complete(system, user, max_tokens=max_tokens, temperature=0.1)
        return _parse_json_loose(raw)


class AnthropicLLM(LLM):
    name = "anthropic"
    available = True

    def __init__(self) -> None:
        self.model = config.ANTHROPIC_MODEL
        self.key = config.ANTHROPIC_API_KEY

    def complete(self, system: str, user: str, *, max_tokens: int = 2000,
                 temperature: float = 0.2) -> str:
        headers = {
            "x-api-key": self.key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        with httpx.Client(timeout=120) as client:
            r = client.post("https://api.anthropic.com/v1/messages",
                            headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        return "".join(parts).strip()


class MockLLM(LLM):
    """
    Deterministic, no-network stand-in. It is NOT random: it produces a
    genuine (if shallow) structured extraction from the input text so the
    pipeline, profiles, search and briefings all work for testing/demo.
    """
    name = "mock"
    available = True

    def complete(self, system: str, user: str, *, max_tokens: int = 2000,
                 temperature: float = 0.2) -> str:
        # If the caller asked for JSON extraction, synthesize a plausible object.
        if "return json" in system.lower() or "json" in system.lower():
            return json.dumps(self._mock_extract(user))
        # Otherwise return a short summary-like echo.
        text = _last_transcript_block(user)
        first = text.strip().splitlines()[0] if text.strip() else "conversation"
        return ("**[Demo mode — no AI key configured]**\n\n"
                f"This is a placeholder summary. The conversation opened with: "
                f"\"{first[:160]}\". Add an ANTHROPIC_API_KEY to generate real "
                "executive summaries.")

    def _mock_extract(self, user: str) -> dict:
        text = _last_transcript_block(user)
        sentences = re.split(r"(?<=[.!?۔؟])\s+", text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 8][:6]
        items = []
        for s in sentences:
            low = s.lower()
            if any(k in low for k in ["will ", "i'll", "we'll", "promise", "send", "deliver"]):
                items.append({"kind": "action_item", "content": s, "owner": "me",
                              "source_quote": s, "confidence": 0.4})
            elif any(k in low for k in ["decide", "agreed", "decision", "we chose"]):
                items.append({"kind": "decision", "content": s,
                              "source_quote": s, "confidence": 0.4})
        return {
            "title": (sentences[0][:60] if sentences else "Conversation"),
            "language": "mixed",
            "summary": ("**[Demo mode]** " + (" ".join(sentences[:3]) or "No content.")),
            "people": [],
            "companies": [],
            "items": items or [{"kind": "highlight",
                                "content": (sentences[0] if sentences else "No content extracted."),
                                "confidence": 0.3}],
            "facts": [],
        }


def _last_transcript_block(user: str) -> str:
    # Extraction prompts embed the transcript after a marker; fall back to all.
    m = re.split(r"TRANSCRIPT:|Transcript:|--- TRANSCRIPT ---", user)
    return m[-1] if len(m) > 1 else user


def _parse_json_loose(raw: str) -> Any:
    raw = raw.strip()
    # strip code fences
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # find first {...} or [...] block
        for opener, closer in (("{", "}"), ("[", "]")):
            i, j = raw.find(opener), raw.rfind(closer)
            if i != -1 and j != -1 and j > i:
                try:
                    return json.loads(raw[i:j + 1])
                except json.JSONDecodeError:
                    continue
        raise


_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is not None:
        return _llm
    provider = config.resolved_llm_provider()
    if provider == "anthropic" and config.ANTHROPIC_API_KEY:
        _llm = AnthropicLLM()
    else:
        _llm = MockLLM()
    return _llm


def reset_llm() -> None:
    global _llm
    _llm = None
