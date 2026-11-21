"""Registration captcha behavior."""

from __future__ import annotations

from io import BytesIO

from flask import Flask
from PIL import Image

from app.core import captcha


def _app() -> Flask:
    app = Flask(__name__)
    app.secret_key = "test-secret-key-with-at-least-32-chars"
    return app


def test_issue_captcha_returns_png(monkeypatch):
    monkeypatch.setattr(captcha, "_random_captcha_code", lambda: "A7B9")

    with _app().test_request_context():
        state: dict = {}
        image = captcha.issue_captcha(state)

    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    assert state[captcha.CAPTCHA_HASH_KEY]
    assert state[captcha.CAPTCHA_EXPIRES_KEY] > 0
    with Image.open(BytesIO(image)) as rendered:
        assert rendered.size == (captcha.CAPTCHA_WIDTH, captcha.CAPTCHA_HEIGHT)


def test_correct_captcha_is_consumed_once(monkeypatch):
    monkeypatch.setattr(captcha, "_random_captcha_code", lambda: "A7B9")
    monkeypatch.setattr(captcha, "_now_ts", lambda: 100.0)

    with _app().test_request_context():
        state: dict = {}
        captcha.issue_captcha(state)
        assert captcha.verify_captcha(state, "a7b9") is True
        assert captcha.verify_captcha(state, "a7b9") is False


def test_wrong_captcha_is_rejected(monkeypatch):
    monkeypatch.setattr(captcha, "_random_captcha_code", lambda: "A7B9")

    with _app().test_request_context():
        state: dict = {}
        captcha.issue_captcha(state)
        assert captcha.verify_captcha(state, "ZZZZ") is False


def test_expired_captcha_is_rejected(monkeypatch):
    monkeypatch.setattr(captcha, "_random_captcha_code", lambda: "A7B9")
    monkeypatch.setattr(captcha, "_now_ts", lambda: 100.0)

    with _app().test_request_context():
        state: dict = {}
        captcha.issue_captcha(state)
        monkeypatch.setattr(captcha, "_now_ts", lambda: 100.0 + captcha.CAPTCHA_TTL_SECONDS + 1)
        assert captcha.verify_captcha(state, "A7B9") is False
