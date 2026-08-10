"""
Authentication for the single-CEO MVP.

Security choices:
- Password is never stored in the DB in plaintext; we keep a PBKDF2 hash.
- Sessions are stateless, HMAC-signed cookies with an expiry (no server store).
- If the owner did not set APP_PASSWORD, a strong random one is generated and
  printed to the server console once, so the app is NEVER left open by default.
- SECRET_KEY (for signing) is generated and persisted to a local file with
  0600 permissions if not provided via env.

This is deliberately simple and self-hosted. The architecture doc describes the
upgrade path to per-user accounts + OAuth/passkeys for a multi-user product.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from . import config

_SECRET_FILE = config.DATA_DIR / ".secret_key"
_PW_FILE = config.DATA_DIR / ".password_hash"

_secret: bytes = b""
_pw_hash: str = ""
generated_password: str | None = None  # shown in console if we generated one


def _load_or_create_secret() -> bytes:
    if config.SECRET_KEY:
        return config.SECRET_KEY.encode()
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_bytes()
    key = secrets.token_bytes(32)
    _SECRET_FILE.write_bytes(key)
    try:
        os.chmod(_SECRET_FILE, 0o600)
    except OSError:
        pass
    return key


def _hash_password(password: str, salt: bytes) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return base64.b64encode(salt).decode() + ":" + base64.b64encode(dk).decode()


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_b64, _ = stored.split(":", 1)
        salt = base64.b64decode(salt_b64)
    except (ValueError, Exception):  # noqa: BLE001
        return False
    return hmac.compare_digest(_hash_password(password, salt), stored)


def init_auth() -> None:
    global _secret, _pw_hash, generated_password
    _secret = _load_or_create_secret()

    if config.APP_PASSWORD:
        password = config.APP_PASSWORD
        _pw_hash = _hash_password(password, secrets.token_bytes(16))
    elif _PW_FILE.exists():
        _pw_hash = _PW_FILE.read_text().strip()
    else:
        # generate a strong one-time password and persist its hash
        generated_password = secrets.token_urlsafe(12)
        _pw_hash = _hash_password(generated_password, secrets.token_bytes(16))
        _PW_FILE.write_text(_pw_hash)
        try:
            os.chmod(_PW_FILE, 0o600)
        except OSError:
            pass


def check_password(password: str) -> bool:
    return bool(_pw_hash) and _verify_password(password, _pw_hash)


# --- signed session cookies ------------------------------------------------

def issue_session() -> str:
    exp = int(time.time()) + config.SESSION_TTL_SECONDS
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode()
    sig = hmac.new(_secret, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def valid_session(cookie: str | None) -> bool:
    if not cookie or "." not in cookie:
        return False
    payload, sig = cookie.rsplit(".", 1)
    expected = hmac.new(_secret, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
    except Exception:  # noqa: BLE001
        return False
    return int(data.get("exp", 0)) > int(time.time())
