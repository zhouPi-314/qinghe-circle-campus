"""Trusted client IP selection for Cloudflare proxying."""

from __future__ import annotations

import pytest

from app import create_app
from app.config import Config
from app.core.security_monitor import trusted_client_ip


def _app(monkeypatch, *, trust_cloudflare: bool):
    app = create_app(testing=True)
    app.config["APP_CONFIG"].trust_cloudflare_ip_header = trust_cloudflare
    app.config["APP_CONFIG"].cloudflare_origin_secret = "origin-secret"
    monkeypatch.setattr(
        "app.core.security_monitor.has_app_context", lambda: True
    )
    return app


def test_cloudflare_header_is_ignored_by_default(monkeypatch):
    app = _app(monkeypatch, trust_cloudflare=False)
    with app.test_request_context(
        headers={"CF-Connecting-IP": "203.0.113.10"},
        environ_base={"REMOTE_ADDR": "10.0.0.8"},
    ):
        assert trusted_client_ip() == "10.0.0.8"


def test_cloudflare_header_is_used_when_explicitly_trusted(monkeypatch):
    app = _app(monkeypatch, trust_cloudflare=True)
    with app.test_request_context(
        headers={
            "CF-Connecting-IP": "203.0.113.10",
            "X-Qinghe-Origin-Secret": "origin-secret",
        },
        environ_base={"REMOTE_ADDR": "10.0.0.8"},
    ):
        assert trusted_client_ip() == "203.0.113.10"


def test_invalid_cloudflare_header_falls_back(monkeypatch):
    app = _app(monkeypatch, trust_cloudflare=True)
    with app.test_request_context(
        headers={
            "CF-Connecting-IP": "not-an-ip",
            "X-Qinghe-Origin-Secret": "origin-secret",
        },
        environ_base={"REMOTE_ADDR": "10.0.0.8"},
    ):
        assert trusted_client_ip() == "10.0.0.8"


def test_missing_origin_secret_ignores_cloudflare_header(monkeypatch):
    app = _app(monkeypatch, trust_cloudflare=True)
    with app.test_request_context(
        headers={"CF-Connecting-IP": "203.0.113.10"},
        environ_base={"REMOTE_ADDR": "10.0.0.8"},
    ):
        assert trusted_client_ip() == "10.0.0.8"


def test_wrong_origin_secret_ignores_cloudflare_header(monkeypatch):
    app = _app(monkeypatch, trust_cloudflare=True)
    with app.test_request_context(
        headers={
            "CF-Connecting-IP": "203.0.113.10",
            "X-Qinghe-Origin-Secret": "wrong",
        },
        environ_base={"REMOTE_ADDR": "10.0.0.8"},
    ):
        assert trusted_client_ip() == "10.0.0.8"


def test_trusted_cloudflare_requires_config_secret(monkeypatch, tmp_path):
    monkeypatch.setattr("app.config.load_dotenv_file", lambda _path: {})
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-with-at-least-32-chars")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/qinghe_test"
    )
    monkeypatch.setenv("SMS_PROVIDER", "mock")
    monkeypatch.setenv("VERCEL_ENV", "development")
    monkeypatch.setenv("TRUST_CLOUDFLARE_IP_HEADER", "true")
    monkeypatch.delenv("CLOUDFLARE_ORIGIN_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="CLOUDFLARE_ORIGIN_SECRET"):
        Config(project_root=tmp_path).validate()
