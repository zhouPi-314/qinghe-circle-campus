"""Cloudflare Turnstile server-side verification for the login form."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import Config

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
LOGIN_ACTION = "login"


class TurnstileError(Exception):
    """A safe, user-facing Turnstile verification failure."""


def verify_turnstile(
    config: Config,
    token: str,
    *,
    remote_ip: str | None = None,
    timeout_seconds: float = 5.0,
) -> None:
    """Verify one Turnstile response token without logging or persisting it."""
    if not config.turnstile_configured:
        return

    submitted = (token or "").strip()
    if not submitted:
        raise TurnstileError("请先完成安全验证。")

    form = {
        "secret": config.turnstile_secret_key,
        "response": submitted,
    }
    if remote_ip:
        form["remoteip"] = remote_ip

    request = Request(
        SITEVERIFY_URL,
        data=urlencode(form).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as err:
        raise TurnstileError("安全验证服务暂时不可用，请稍后重试。") from err

    if payload.get("success") is not True:
        raise TurnstileError("安全验证未通过，请刷新后重试。")
    if payload.get("action") != LOGIN_ACTION:
        raise TurnstileError("安全验证上下文无效，请刷新后重试。")
