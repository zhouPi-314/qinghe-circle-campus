"""集成测试：公开仓库不预置管理员密码，管理员由交互工具创建。"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app import db
from app.models.user import User
from app.services.auth_service import check_password
from tools.create_platform_admin import create_platform_admin

pytestmark = pytest.mark.integration


def test_create_first_platform_admin(app):
    with app.app_context():
        create_platform_admin(
            login_name="bootstrap_admin",
            password="Bootstrap123",
            nickname="初始管理员",
        )

        saved = db.session.scalar(select(User).where(User.login_name == "bootstrap_admin"))
        assert saved is not None
        assert saved.role == "platform_admin"
        assert saved.status == "active"
        assert saved.password_must_change is False
        assert check_password(saved.password_hash, "Bootstrap123")
