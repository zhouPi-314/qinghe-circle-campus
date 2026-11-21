"""交互式创建首个平台管理员。

用法：
    .venv/Scripts/python tools/create_platform_admin.py

密码从终端读取，不进入命令历史、源码或日志。
"""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app, db  # noqa: E402
from app.core.errors import InputError  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.auth_service import hash_password, validate_password_strength  # noqa: E402


def create_platform_admin(*, login_name: str, password: str, nickname: str) -> User:
    """在当前应用上下文中创建平台管理员。"""
    login_name = (login_name or "").strip()
    nickname = (nickname or "").strip() or "平台管理员"
    if not login_name:
        raise InputError("登录账号不能为空。")
    validate_password_strength(password)
    if db.session.scalar(select(User).where(User.login_name == login_name)) is not None:
        raise InputError("登录账号已存在。")

    now = datetime.now(UTC)
    user = User(
        login_name=login_name,
        password_hash=hash_password(password),
        password_must_change=False,
        nickname=nickname,
        role="platform_admin",
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.session.add(user)
    db.session.commit()
    return user


def main() -> int:
    parser = argparse.ArgumentParser(description="创建青禾流转首个平台管理员")
    parser.add_argument("--login-name", default="platform_admin")
    parser.add_argument("--nickname", default="平台管理员")
    args = parser.parse_args()

    password = getpass.getpass("管理员密码（至少 8 位，含字母和数字）：")
    if password != getpass.getpass("再次输入密码："):
        print("两次输入的密码不一致。", file=sys.stderr)
        return 1

    app = create_app()
    with app.app_context():
        try:
            user = create_platform_admin(
                login_name=args.login_name,
                password=password,
                nickname=args.nickname,
            )
        except InputError as err:
            print(err.message, file=sys.stderr)
            return 1
        print(f"平台管理员已创建：{user.login_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
