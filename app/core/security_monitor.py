"""Helpers for privacy-safe operational and security records."""

from __future__ import annotations

_SENSITIVE_PARTS = (
    "authorization",
    "cookie",
    "password",
    "phone",
    "secret",
    "token",
    "verify_code",
)


def safe_event_detail(value):
    """Recursively redact sensitive keys before persisting operational detail."""
    if isinstance(value, dict):
        return {
            str(key): (
                "[redacted]"
                if any(part in str(key).lower() for part in _SENSITIVE_PARTS)
                else safe_event_detail(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [safe_event_detail(item) for item in value]
    return value
