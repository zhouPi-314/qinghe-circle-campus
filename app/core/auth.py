"""认证会话与安全辅助：会话键、CSRF、手机号哈希、当前用户加载。

安全规则（工程标准第 5 节）：
- 密码与验证码只存哈希；
- 手机号以 HMAC-SHA-256 哈希匹配，另存后四位；
- 会话 Cookie HttpOnly + SameSite，生产启用 Secure（见 app/config.py）；
- 所有写表单启用 CSRF。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from flask import g, session

from app.core.errors import LoginRequiredError, PermissionDeniedError

SESSION_USER_ID = "auth.user_id"
SESSION_IDENTITY_ROLE = "auth.identity_role"
SESSION_UNIVERSITY_ID = "auth.university_id"
SESSION_CAMPUS_ID = "auth.campus_id"
SESSION_CSRF_TOKEN = "auth.csrf_token"

VALID_IDENTITY_ROLES = ("student", "station_manager", "platform_admin", "university_admin")

ROLE_LABELS = {
    "student": "学生",
    "station_manager": "公益管理员",
    "platform_admin": "平台管理员",
    "university_admin": "校级管理员",
}


def _secret_key_bytes() -> bytes:
    from flask import current_app

    return current_app.config["SECRET_KEY"].encode("utf-8")


# ---------------------------------------------------------------------------
# 手机号哈希（数据库设计第 1 节：HMAC-SHA-256，另存后四位）
# ---------------------------------------------------------------------------


def normalize_phone(phone: str) -> str:
    """规范化手机号：只保留数字；必须是 11 位大陆手机号。"""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    return digits


def is_valid_phone(phone: str) -> bool:
    """11 位大陆手机号：以 1 开头，第二位为 3-9。"""
    digits = normalize_phone(phone)
    return len(digits) == 11 and digits[0] == "1" and digits[1] in "3456789"


# 手机号哈希密钥版本：变更即视为密钥轮换，必须执行迁移（见 D-033）
PHONE_HASH_KEY_VERSION = 1


def phone_hmac_key() -> bytes:
    """从 SECRET_KEY 派生手机号哈希专用密钥（版本化，不新增环境变量）。

    迁移约束（decision-log D-033）：手机号哈希与 SECRET_KEY 绑定，
    轮换 SECRET_KEY 会使既有 phone_hash 失配。轮换前必须执行迁移：
    1) 平台管理员重新导入名单 CSV（按新密钥重建 registry 哈希）；
    2) 迁移作业按 registered_user_id 把 registry.phone_hash 同步回 users；
    3) 学生以学号登录即可恢复手机号登录。上线前（G4）纳入发布检查单。
    """
    label = f"qinghe-phone-hash-v{PHONE_HASH_KEY_VERSION}".encode()
    return hmac.new(_secret_key_bytes(), label, hashlib.sha256).digest()


def phone_hash(phone: str) -> str:
    """计算规范化手机号的 HMAC-SHA-256 十六进制值。"""
    normalized = normalize_phone(phone)
    return hmac.new(phone_hmac_key(), normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def phone_last4(phone: str) -> str:
    return normalize_phone(phone)[-4:]


# ---------------------------------------------------------------------------
# CSRF（无 Flask-WTF 依赖，会话令牌 + 掩码比较）
# ---------------------------------------------------------------------------


def get_or_create_csrf_token() -> str:
    token = session.get(SESSION_CSRF_TOKEN)
    if not token:
        token = secrets.token_hex(32)
        session[SESSION_CSRF_TOKEN] = token
    return token


def validate_csrf_token(submitted: str | None) -> bool:
    expected = session.get(SESSION_CSRF_TOKEN)
    if not expected or not submitted:
        return False
    return hmac.compare_digest(expected, submitted)


# ---------------------------------------------------------------------------
# 登录身份选择与会话
# ---------------------------------------------------------------------------


def set_identity_role(role: str) -> None:
    if role not in VALID_IDENTITY_ROLES:
        raise ValueError("无效的登录身份")
    session[SESSION_IDENTITY_ROLE] = role


def get_identity_role() -> str | None:
    return session.get(SESSION_IDENTITY_ROLE)


def set_student_context(university_id: int, campus_id: int) -> None:
    session[SESSION_UNIVERSITY_ID] = int(university_id)
    session[SESSION_CAMPUS_ID] = int(campus_id)


def login_user(user_id: int) -> None:
    session[SESSION_USER_ID] = int(user_id)
    # 会话固定防护：登录成功后更换会话令牌
    session[SESSION_CSRF_TOKEN] = secrets.token_hex(32)


def logout_user() -> None:
    session.pop(SESSION_USER_ID, None)
    session.pop(SESSION_IDENTITY_ROLE, None)
    session.pop(SESSION_UNIVERSITY_ID, None)
    session.pop(SESSION_CAMPUS_ID, None)
    session.pop(SESSION_CSRF_TOKEN, None)


def current_user_id() -> int | None:
    raw = session.get(SESSION_USER_ID)
    return int(raw) if raw is not None else None


def load_current_user():
    """加载当前登录用户；未登录返回 None。

    会话中只保存 user_id；用户读取统一走身份与准入 service 的
    load_current_user 接口（交接书第 7 节），避免第二套状态策略。
    """
    from app.core.permissions import to_current_user
    from app.services import auth_service

    user_id = current_user_id()
    if user_id is None:
        return None
    user = auth_service.load_current_user(user_id)
    if user is None:
        return None
    return to_current_user(user)


def require_login():
    """未登录抛出 LoginRequiredError（由错误处理器跳转登录页）。"""
    user = g.get("current_user")
    if user is None:
        raise LoginRequiredError("该页面需要登录后访问。")
    return user


def require_roles(*roles: str):
    """要求当前用户具备指定角色之一；越权返回 403。"""
    user = require_login()
    if user.role not in roles:
        label = ROLE_LABELS.get(user.role, user.role)
        raise PermissionDeniedError(f"当前身份（{label}）无法执行该操作。")
    return user


# ---------------------------------------------------------------------------
# 应用级钩子注册
# ---------------------------------------------------------------------------


def register_auth_hooks(app) -> None:
    """注册 CSRF 校验与当前用户加载钩子。"""

    from flask import g, request

    @app.before_request
    def _load_current_user() -> None:
        g.current_user = load_current_user()

    @app.before_request
    def _csrf_protect():
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if not validate_csrf_token(request.form.get("csrf_token")):
                from app.core.errors import AppError

                raise AppError(
                    "页面安全校验失败。请返回上一页刷新后重新提交。",
                    title="安全校验失败",
                )
