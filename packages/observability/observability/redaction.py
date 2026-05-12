from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, cast

from pydantic import BaseModel

REDACTED = "[REDACTED]"

_CAMEL_CASE_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
_TOKEN_ASSIGNMENT = re.compile(
    r"\b((?:access|refresh|id|auth|bearer)[_-]?token|client[_-]?secret|api[_-]?key)"
    r"([\"']?\s*[:=]\s*[\"']?)"
    r"([^\"'\s,;&}]+)",
    re.IGNORECASE,
)
_SENSITIVE_LABEL_VALUE = re.compile(
    r"\b(authorization|proxy[_ -]?authorization|"
    r"(?:access|refresh|id|auth|bearer)[_-]?token|client[_-]?secret|api[_-]?key)"
    r"(\s+)"
    r"([^\"'\s,;&}]{10,})",
    re.IGNORECASE,
)
_AUTH_SCHEME = re.compile(r"\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")

_EXACT_SENSITIVE_KEYS = {
    "authorization",
    "proxy_authorization",
    "x_api_key",
    "api_key",
    "apikey",
    "client_secret",
    "secret",
    "password",
    "passwd",
    "private_key",
    "credential",
    "credentials",
}
_SENSITIVE_PARTS = {
    "secret",
    "password",
    "passwd",
    "credential",
    "credentials",
}


def _normalize_key(key: object) -> str:
    key_text = str(key)
    key_text = _CAMEL_CASE_BOUNDARY.sub(r"\1_\2", key_text)
    return re.sub(r"[^a-z0-9]+", "_", key_text.lower()).strip("_")


def is_sensitive_key(key: object) -> bool:
    normalized = _normalize_key(key)
    if normalized in _EXACT_SENSITIVE_KEYS:
        return True

    parts = [part for part in normalized.split("_") if part]
    if "authorization" in parts or "token" in parts:
        return True
    if any(part in _SENSITIVE_PARTS for part in parts):
        return True

    compact = normalized.replace("_", "")
    return compact.endswith("token") or compact in {"authorization", "apikey", "privatekey"}


def redact_string(value: str) -> str:
    redacted = _AUTH_SCHEME.sub(lambda match: f"{match.group(1)} {REDACTED}", value)
    redacted = _JWT.sub(REDACTED, redacted)
    redacted = _TOKEN_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}",
        redacted,
    )
    return _SENSITIVE_LABEL_VALUE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}",
        redacted,
    )


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return redact_sensitive(value.model_dump(mode="json"))

    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in cast(Mapping[object, Any], value).items():
            key_text = str(key)
            redacted[key_text] = REDACTED if is_sensitive_key(key_text) else redact_sensitive(item)
        return redacted

    if isinstance(value, tuple | list | set | frozenset):
        items = cast(Iterable[Any], value)
        return [redact_sensitive(item) for item in items]

    if isinstance(value, str):
        return redact_string(value)

    return value
