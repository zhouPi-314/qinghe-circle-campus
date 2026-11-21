"""个人资料路由：登录用户查看自己的资料与角色（FR-A06/A07 展示部分）。

资料编辑、头像上传随后续增量实现。
"""

from __future__ import annotations

from flask import Blueprint, g, render_template

from app.core.permissions import login_required

bp = Blueprint("me", __name__, url_prefix="/me")


@bp.get("/profile")
@login_required
def profile():
    """个人资料页：昵称、角色标签与登录账号。"""
    user = g.current_user
    account = user.student_no or user.login_name or ""
    return render_template("me/profile.html", user=user, account=account)
