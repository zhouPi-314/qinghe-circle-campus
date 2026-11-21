"""页面展示辅助：时区显示与角色标签。

时间统一存 UTC，页面按 Asia/Shanghai 显示（工程标准第 4 节）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from flask import Flask

DISPLAY_TZ = ZoneInfo("Asia/Shanghai")


def to_local(dt: datetime | None) -> datetime | None:
    """把数据库中的 UTC 时间转换为展示时区。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(DISPLAY_TZ)


def fmt_dt(dt: datetime | None) -> str:
    local = to_local(dt)
    if local is None:
        return ""
    return local.strftime("%Y-%m-%d %H:%M")


def fmt_date(dt: datetime | None) -> str:
    local = to_local(dt)
    if local is None:
        return ""
    return local.strftime("%Y-%m-%d")


def register_display_helpers(app: Flask) -> None:
    app.jinja_env.filters["local_dt"] = fmt_dt
    app.jinja_env.filters["local_date"] = fmt_date

    from app.core.auth import ROLE_LABELS

    app.jinja_env.globals["role_labels"] = ROLE_LABELS
    app.jinja_env.globals["csrf_token"] = _csrf_token_for_template


def _csrf_token_for_template() -> str:
    from app.core.auth import get_or_create_csrf_token

    return get_or_create_csrf_token()
