"""Cloudflare Turnstile verification behaviour."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.config import Config
from app.core import turnstile


class _Response:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self._body


def _config(*, configured: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        turnstile_configured=configured,
        turnstile_secret_key="test-secret" if configured else None,
    )


def test_disabled_turnstile_is_a_no_op(monkeypatch):
    def unexpected(*_args, **_kwargs):
        raise AssertionError("urlopen must not run when Turnstile is disabled")

    monkeypatch.setattr(turnstile, "urlopen", unexpected)
    assert turnstile.verify_turnstile(_config(configured=False), "") is None


def test_missing_token_is_rejected():
    with pytest.raises(turnstile.TurnstileError, match="请先完成安全验证"):
        turnstile.verify_turnstile(_config(), "  ")


def test_successful_login_action_passes(monkeypatch):
    monkeypatch.setattr(
        turnstile,
        "urlopen",
        lambda *_args, **_kwargs: _Response({"success": True, "action": "login"}),
    )
    assert turnstile.verify_turnstile(_config(), "valid-token", remote_ip="127.0.0.1") is None


def test_failed_challenge_is_rejected(monkeypatch):
    monkeypatch.setattr(
        turnstile,
        "urlopen",
        lambda *_args, **_kwargs: _Response(
            {"success": False, "error-codes": ["invalid-input-response"]}
        ),
    )
    with pytest.raises(turnstile.TurnstileError, match="安全验证未通过"):
        turnstile.verify_turnstile(_config(), "invalid-token")


def test_action_mismatch_is_rejected(monkeypatch):
    monkeypatch.setattr(
        turnstile,
        "urlopen",
        lambda *_args, **_kwargs: _Response({"success": True, "action": "registration"}),
    )
    with pytest.raises(turnstile.TurnstileError, match="上下文无效"):
        turnstile.verify_turnstile(_config(), "valid-token")


def test_partial_turnstile_configuration_fails_fast(monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://user:password@localhost/example",
    )
    monkeypatch.setenv("TURNSTILE_SITE_KEY", "site-key")
    monkeypatch.delenv("TURNSTILE_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="必须同时配置"):
        Config(project_root=tmp_path).validate()


def test_production_requires_turnstile(monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://user:password@localhost/example",
    )
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.delenv("TURNSTILE_SITE_KEY", raising=False)
    monkeypatch.delenv("TURNSTILE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LOGIN_VERIFICATION_ENABLED", raising=False)

    with pytest.raises(RuntimeError, match="Production 登录安全验证"):
        Config(project_root=tmp_path).validate()
