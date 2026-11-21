"""主路由：首页与健康检查。"""

from __future__ import annotations

from flask import Blueprint, g, jsonify, render_template
from sqlalchemy import text

from app import db
from app.core.permissions import login_required

bp = Blueprint("main", __name__)


@bp.get("/")
@login_required
def index():
    """首页：已登录进入工作区首页；未登录跳转登录页并保留目标。"""
    return render_template("home.html", user=g.current_user)


@bp.get("/health")
def health():
    """健康检查：验证应用与数据库连接。不输出任何敏感信息。"""
    checks = {"app": "ok"}
    db_status = "ok"
    status_code = 200
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        db.session.rollback()
        db_status = "unavailable"
        status_code = 503
    checks["database"] = db_status
    overall = "ok" if db_status == "ok" else "degraded"
    return jsonify({"status": overall, "checks": checks}), status_code
