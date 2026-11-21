"""Registration captcha generation and one-time session verification."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from io import BytesIO

from flask import current_app
from PIL import Image, ImageDraw, ImageFont

CAPTCHA_TTL_SECONDS = 120
CAPTCHA_WIDTH = 240
CAPTCHA_HEIGHT = 80
CAPTCHA_HASH_KEY = "auth.captcha_hash"
CAPTCHA_EXPIRES_KEY = "auth.captcha_expires_at"

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _now_ts() -> float:
    return time.time()


def _random_captcha_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(4))


def _digest(answer: str) -> str:
    key = current_app.secret_key.encode("utf-8")
    return hmac.new(key, answer.upper().encode("utf-8"), hashlib.sha256).hexdigest()


def _render_image(code: str) -> bytes:
    image = Image.new("RGB", (CAPTCHA_WIDTH, CAPTCHA_HEIGHT), "#f4f8ff")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=40)

    for _ in range(7):
        line = tuple(secrets.randbelow(180) + 40 for _ in range(3))
        draw.line(
            (
                secrets.randbelow(CAPTCHA_WIDTH),
                secrets.randbelow(CAPTCHA_HEIGHT),
                secrets.randbelow(CAPTCHA_WIDTH),
                secrets.randbelow(CAPTCHA_HEIGHT),
            ),
            fill=line,
            width=1,
        )
    for _ in range(90):
        draw.point(
            (secrets.randbelow(CAPTCHA_WIDTH), secrets.randbelow(CAPTCHA_HEIGHT)),
            fill=tuple(secrets.randbelow(180) + 40 for _ in range(3)),
        )

    for index, character in enumerate(code):
        color = tuple(secrets.randbelow(90) + 20 for _ in range(3))
        x = 25 + index * 52 + secrets.randbelow(8)
        y = 16 + secrets.randbelow(12)
        draw.text((x, y), character, font=font, fill=color)

    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def issue_captcha(session) -> bytes:
    """Create a PNG challenge and store only its digest and expiry."""
    code = _random_captcha_code()
    session[CAPTCHA_HASH_KEY] = _digest(code)
    session[CAPTCHA_EXPIRES_KEY] = _now_ts() + CAPTCHA_TTL_SECONDS
    return _render_image(code)


def verify_captcha(session, answer: str) -> bool:
    """Verify and consume the current challenge, regardless of success."""
    expected = session.pop(CAPTCHA_HASH_KEY, None)
    expires_at = session.pop(CAPTCHA_EXPIRES_KEY, None)
    if not expected or not expires_at or _now_ts() > float(expires_at):
        return False
    submitted = (answer or "").strip()
    return bool(submitted) and hmac.compare_digest(expected, _digest(submitted))
