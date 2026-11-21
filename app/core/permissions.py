"""权限辅助：CurrentUser 与路由守卫。

权限在 service 层再次校验（工程标准第 5 节），
本模块只承担路由层的会话守卫和展示信息。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core import auth as session_auth
from app.core.errors import PermissionDeniedError
from app.models.user import User


@dataclass(frozen=True)
class CurrentUser:
    """登录会话中的当前用户快照。"""

    id: int
    role: str
    role_label: str
    nickname: str
    university_id: int | None
    campus_id: int | None
    login_name: str | None
    student_no: str | None

    @property
    def is_student(self) -> bool:
        return self.role == "student"

    @property
    def is_platform_admin(self) -> bool:
        return self.role == "platform_admin"

    @property
    def is_station_manager(self) -> bool:
        return self.role == "station_manager"

    @property
    def is_university_admin(self) -> bool:
        return self.role == "university_admin"


def to_current_user(user: User) -> CurrentUser:
    """把 service 层读到的 User 转为会话用户快照。

    用户读取统一由 auth_service.load_current_user 承担；
    本函数只做展示层包装，不单独查询数据库。
    """
    return CurrentUser(
        id=user.id,
        role=user.role,
        role_label=session_auth.ROLE_LABELS.get(user.role, user.role),
        nickname=user.nickname,
        university_id=user.university_id,
        campus_id=user.campus_id,
        login_name=user.login_name,
        student_no=user.student_no,
    )


def login_required(view):
    """路由装饰器：未登录跳转登录页并保留目标页。"""

    from functools import wraps

    @wraps(view)
    def wrapper(*args, **kwargs):
        session_auth.require_login()
        return view(*args, **kwargs)

    return wrapper


def roles_required(*roles: str):
    """路由装饰器：要求指定角色；越权返回 403。"""

    from functools import wraps

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            session_auth.require_roles(*roles)
            return view(*args, **kwargs)

        return wrapper

    return decorator


def ensure_same_university(actor_university_id: int | None, target_university_id: int) -> None:
    """高校隔离校验：跨学校操作必须拒绝（BR-002）。

    平台管理员（university_id 为 NULL）可跨高校维护基础数据。
    """
    if actor_university_id is None:
        return
    if actor_university_id != target_university_id:
        raise PermissionDeniedError("该内容不属于你所在的学校。")


def is_university_manager(actor: CurrentUser | None) -> bool:
    """平台管理员和校级管理员可进入本校管理范围校验。"""
    return bool(actor and actor.role in ("platform_admin", "university_admin"))


def ensure_actor_university(actor: CurrentUser | None, target_university_id: int) -> int:
    """校验管理员能否操作目标高校，返回目标高校 ID。"""
    if not is_university_manager(actor):
        raise PermissionDeniedError("当前身份无法管理学校数据。")
    if _university_status(target_university_id) != "active":
        raise PermissionDeniedError("所属高校不存在或已停用。")
    if actor.is_university_admin and actor.university_id != target_university_id:
        raise PermissionDeniedError("只能管理你所在的学校。")
    return target_university_id


def _university_status(university_id: int) -> str | None:
    """读取高校状态；未找到返回 None。"""
    from app import db
    from app.models.university import University

    university = db.session.get(University, university_id)
    return university.status if university is not None else None
