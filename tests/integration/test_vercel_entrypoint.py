"""Vercel WSGI entrypoint smoke test."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_vercel_entrypoint_exposes_health(app):
    from main import app as vercel_app

    response = vercel_app.test_client().get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
