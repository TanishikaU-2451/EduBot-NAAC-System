"""
Basic Authentication for NAAC Compliance Intelligence System
Serverless-safe stateless token auth with hardcoded demo users.
"""

import base64
import hashlib
import hmac
import os
import secrets
import time
import json
from datetime import datetime, timezone
from typing import Optional, Dict

from ..config.settings import get_settings

# ---------------------------------------------------------------------------
# Demo users — in a real deployment replace with a database lookup
# ---------------------------------------------------------------------------
_USERS: Dict[str, str] = {
    "admin": "naac2025",          # username: password
    "faculty": "mvsr@faculty",
    "demo": "demo1234",
}

# ---------------------------------------------------------------------------
# Stateless session token configuration
# ---------------------------------------------------------------------------
_TOKEN_SECRET_CACHE: Optional[bytes] = None
_DEFAULT_DEV_SECRET = "edubot-dev-insecure-secret-change-me"
_REVOKED_TOKEN_HASHES: Dict[str, int] = {}


def _get_session_ttl_hours() -> int:
    try:
        ttl = int(get_settings().auth_token_ttl_hours)
        return max(ttl, 1)
    except Exception:
        return 8


def _get_token_secret() -> bytes:
    global _TOKEN_SECRET_CACHE
    if _TOKEN_SECRET_CACHE is not None:
        return _TOKEN_SECRET_CACHE

    secret = None
    try:
        cfg = get_settings()
        secret = cfg.auth_token_secret or cfg.api_key
    except Exception:
        secret = None

    if not secret:
        secret = os.getenv("AUTH_TOKEN_SECRET") or os.getenv("API_KEY")

    if not secret:
        secret = _DEFAULT_DEV_SECRET

    _TOKEN_SECRET_CACHE = str(secret).encode("utf-8")
    return _TOKEN_SECRET_CACHE


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode((raw + padding).encode("ascii"))


def _token_expiry_timestamp() -> int:
    return int(time.time()) + _get_session_ttl_hours() * 3600


def _build_token(username: str) -> str:
    payload = {
        "sub": username,
        "iat": int(time.time()),
        "exp": _token_expiry_timestamp(),
        "nonce": secrets.token_hex(8),
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64url_encode(payload_json)
    signature = hmac.new(_get_token_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return f"{payload_b64}.{_b64url_encode(signature)}"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _cleanup_revoked(now_ts: int) -> None:
    expired_hashes = [digest for digest, exp in _REVOKED_TOKEN_HASHES.items() if exp <= now_ts]
    for digest in expired_hashes:
        _REVOKED_TOKEN_HASHES.pop(digest, None)


def _decode_payload(token: str) -> Optional[dict]:
    try:
        payload_b64, sig_b64 = token.split(".", 1)
    except ValueError:
        return None

    expected_sig = hmac.new(_get_token_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64url_encode(expected_sig), sig_b64):
        return None

    try:
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None
    return payload


def _validate_payload(payload: dict) -> Optional[dict]:
    sub = str(payload.get("sub", "")).strip()
    if not sub:
        return None

    try:
        exp = int(payload.get("exp", 0))
    except Exception:
        return None

    now_ts = int(time.time())
    _cleanup_revoked(now_ts)
    if exp <= now_ts:
        return None

    if _REVOKED_TOKEN_HASHES.get(_token_hash(payload.get("raw_token", "")), 0) > now_ts:
        return None

    return {"username": sub, "exp": exp}


def _verify_token(token: str) -> Optional[dict]:
    payload = _decode_payload(token)
    if payload is None:
        return None
    payload["raw_token"] = token
    return _validate_payload(payload)


def _hash_password(password: str) -> str:
    """Simple SHA-256 hash. For a production system use bcrypt."""
    return hashlib.sha256(password.encode()).hexdigest()


def authenticate(username: str, password: str) -> Optional[str]:
    """
    Validate credentials and return a signed stateless session token on success,
    or None on failure.
    """
    stored_password = _USERS.get(username)
    if stored_password is None:
        return None  # unknown user

    # constant-time comparison to avoid timing attacks
    if not hmac.compare_digest(stored_password, password):
        return None

    return _build_token(username)


def validate_token(token: str) -> Optional[str]:
    """
    Return the username associated with a valid, non-expired session token,
    or None if invalid / expired.
    """
    verified = _verify_token(token)
    if verified is None:
        return None

    return verified["username"]


def logout(token: str) -> bool:
    """Best-effort token invalidation.

    Tokens are stateless, so revocation is process-local and primarily useful for local runs.
    """
    verified = _verify_token(token)
    if verified is None:
        return False

    _REVOKED_TOKEN_HASHES[_token_hash(token)] = int(verified["exp"])
    return True


def get_session_info(token: str) -> Optional[dict]:
    """Return full session metadata for a valid token."""
    verified = _verify_token(token)
    if verified is None:
        return None

    expires_at = datetime.fromtimestamp(int(verified["exp"]), tz=timezone.utc)
    return {
        "username": verified["username"],
        "expires_at": expires_at.isoformat(),
    }
