"""
Basic Authentication for NAAC Compliance Intelligence System
Simple session-based auth with hardcoded demo users.
No external dependencies beyond what's already in requirements.txt.
"""

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict

# ---------------------------------------------------------------------------
# Demo users — in a real deployment replace with a database lookup
# ---------------------------------------------------------------------------
_USERS: Dict[str, str] = {
    "admin": "naac2025",          # username: password
    "faculty": "mvsr@faculty",
    "demo": "demo1234",
}

# ---------------------------------------------------------------------------
# Session store — in-memory (resets on server restart — fine for demo)
# ---------------------------------------------------------------------------
_SESSIONS: Dict[str, dict] = {}   # token → {username, expires_at}

SESSION_TTL_HOURS = 8


def _hash_password(password: str) -> str:
    """Simple SHA-256 hash. For a production system use bcrypt."""
    return hashlib.sha256(password.encode()).hexdigest()


def authenticate(username: str, password: str) -> Optional[str]:
    """
    Validate credentials and return a session token on success,
    or None on failure.
    """
    stored_password = _USERS.get(username)
    if stored_password is None:
        return None  # unknown user

    # constant-time comparison to avoid timing attacks
    if not hmac.compare_digest(stored_password, password):
        return None

    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = {
        "username": username,
        "expires_at": (datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS)).isoformat(),
    }
    return token


def validate_token(token: str) -> Optional[str]:
    """
    Return the username associated with a valid, non-expired session token,
    or None if invalid / expired.
    """
    session = _SESSIONS.get(token)
    if session is None:
        return None

    expires_at = datetime.fromisoformat(session["expires_at"])
    if datetime.utcnow() > expires_at:
        del _SESSIONS[token]
        return None

    return session["username"]


def logout(token: str) -> bool:
    """Invalidate a session token. Returns True if the token existed."""
    return _SESSIONS.pop(token, None) is not None


def get_session_info(token: str) -> Optional[dict]:
    """Return full session metadata for a valid token."""
    session = _SESSIONS.get(token)
    if session is None:
        return None
    expires_at = datetime.fromisoformat(session["expires_at"])
    if datetime.utcnow() > expires_at:
        del _SESSIONS[token]
        return None
    return {
        "username": session["username"],
        "expires_at": session["expires_at"],
    }
