"""Helpers for privacy-safe operational and security records."""

from __future__ import annotations

import hmac
from ipaddress import ip_address

from flask import current_app, has_app_context, request

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


def trusted_client_ip() -> str:
    """Return Cloudflare's client IP only when the deployment explicitly trusts it."""
    if not has_app_context():
        return "unknown"
    config = current_app.config.get("APP_CONFIG")
    if config is not None and config.trust_cloudflare_ip_header:
        supplied_secret = (request.headers.get("X-Qinghe-Origin-Secret") or "").strip()
        expected_secret = getattr(config, "cloudflare_origin_secret", None) or ""
        if not expected_secret or not hmac.compare_digest(supplied_secret, expected_secret):
            return request.remote_addr or "unknown"
        candidate = (request.headers.get("CF-Connecting-IP") or "").strip()
        try:
            return str(ip_address(candidate))
        except ValueError:
            pass
    return request.remote_addr or "unknown"
