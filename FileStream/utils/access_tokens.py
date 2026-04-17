from __future__ import annotations

import secrets
from datetime import datetime, timedelta


_access_tokens: dict[str, dict] = {}


def _utcnow() -> datetime:
    return datetime.utcnow()


def _clean_expired_tokens() -> None:
    now = _utcnow()
    expired = [token for token, payload in _access_tokens.items() if payload["expires"] < now]
    for token in expired:
        _access_tokens.pop(token, None)


def create_access_token(
    path: str,
    *,
    kind: str,
    expires_in_seconds: int = 300,
    single_use: bool = False,
    metadata: dict | None = None,
) -> str:
    _clean_expired_tokens()
    token = secrets.token_urlsafe(32)
    _access_tokens[token] = {
        "path": str(path or "").strip(),
        "kind": str(kind or "").strip(),
        "expires": _utcnow() + timedelta(seconds=max(int(expires_in_seconds), 1)),
        "single_use": bool(single_use),
        "used": False,
        "metadata": dict(metadata or {}),
    }
    return token


def validate_access_token(
    token: str,
    *,
    expected_kind: str | None = None,
    consume: bool = False,
) -> dict | None:
    _clean_expired_tokens()
    payload = _access_tokens.get(str(token or "").strip())
    if not payload:
        return None

    if expected_kind and payload.get("kind") != expected_kind:
        return None

    if payload["expires"] < _utcnow():
        _access_tokens.pop(token, None)
        return None

    if payload.get("single_use") and payload.get("used"):
        return None

    if consume and payload.get("single_use"):
        payload["used"] = True
        result = dict(payload)
        _access_tokens.pop(token, None)
        return result

    return dict(payload)


def invalidate_access_tokens_for_path(path: str, *kinds: str) -> None:
    target = str(path or "").strip()
    if not target:
        return

    wanted_kinds = {str(kind or "").strip() for kind in kinds if str(kind or "").strip()}
    expired = []
    for token, payload in _access_tokens.items():
        if payload.get("path") != target:
            continue
        if wanted_kinds and payload.get("kind") not in wanted_kinds:
            continue
        expired.append(token)

    for token in expired:
        _access_tokens.pop(token, None)
