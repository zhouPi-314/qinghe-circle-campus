"""认证路由：身份选择、学生学校校区选择、注册、密码登录、退出。

路由只解析请求和输出模板（工程标准第 3 节）；
业务规则在 app/services/auth_service.py。

next 闭环（SRS 异常需求：未登录访问 → 跳转登录并保留目标页）：
next 参数贯穿 身份选择 → 学校校区选择 → 登录 → 登录后落点，
只允许站内相对路径，防止开放重定向。
"""

from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, session, url_for

from app.core import auth as session_auth
from app.core.errors import InputError
from app.services import auth_service

bp = Blueprint("auth", __name__, url_prefix="/auth")

_IDENTITY_ROLES = {
    "student": "在校学生",
    "station_manager": "公益管理员（回收）",
    "platform_admin": "平台管理员",
    "university_admin": "校级管理员（预留）",
}


def _safe_target(raw: str | None) -> str | None:
    """校验 next 目标：仅接受站内相对路径（拒绝外链与协议相对地址）。"""
    if not raw:
        return None
    target = raw.strip()
    if target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return None


def _target_from_request() -> str | None:
    return _safe_target(request.values.get("next"))


def _redirect_with_next(endpoint: str, target: str | None, **kwargs):
    if target:
        return redirect(url_for(endpoint, next=target, **kwargs))
    return redirect(url_for(endpoint, **kwargs))


@bp.route("/identity", methods=["GET", "POST"])
def identity():
    """选择登录身份（BR-044）：学生进入学校校区选择，其余进入各自登录界面。"""
    target = _target_from_request()
    if request.method == "POST":
        role = request.form.get("role", "")
        if role not in _IDENTITY_ROLES:
            raise InputError("请选择有效的登录身份。")
        session_auth.set_identity_role(role)
        if role == "student":
            return _redirect_with_next("auth.student_context", target)
        return _redirect_with_next("auth.login", target)
    return render_template(
        "auth/identity.html",
        roles=_IDENTITY_ROLES,
        selected=session_auth.get_identity_role(),
        next_target=target,
    )


@bp.route("/student-context", methods=["GET", "POST"])
def student_context():
    """学生选择学校与校区（FR-A08）；单校区高校校区显示学校全称。"""
    target = _target_from_request()
    if session_auth.get_identity_role() != "student":
        return _redirect_with_next("auth.identity", target)

    context = auth_service.get_student_context()

    if request.method == "POST":
        try:
            university_id = int(request.form.get("university_id", ""))
            campus_id = int(request.form.get("campus_id", ""))
        except ValueError:
            raise InputError(
                "请选择学校和校区。", field_errors={"campus_id": "请选择学校和校区。"}
            ) from None

        university = next((u for u in context["universities"] if u["id"] == university_id), None)
        if university is None:
            raise InputError("所选学校不存在或已停用，请重新选择。")
        campus = next((c for c in university["campuses"] if c["id"] == campus_id), None)
        if campus is None:
            raise InputError("所选校区不存在或已停用，请重新选择。")

        session_auth.set_student_context(university_id, campus_id)
        return _redirect_with_next("auth.login", target)

    return render_template(
        "auth/student_context.html",
        universities=context["universities"],
        selected_university_id=session.get(session_auth.SESSION_UNIVERSITY_ID),
        selected_campus_id=session.get(session_auth.SESSION_CAMPUS_ID),
        next_target=target,
    )


@bp.route("/login", methods=["GET", "POST"])
def login():
    """按所选身份进入对应登录界面（BR-044）。

    - 学生：学号或手机号 + 密码，账号必须属于所选学校；
    - 公益管理员 / 平台管理员 / 校级管理员：login_name + 密码，无注册入口；
    - 登录成功后回到 next 指定的站内目标页。
    """
    target = _target_from_request()
    role = session_auth.get_identity_role()
    if role is None:
        return _redirect_with_next("auth.identity", target)
    if role == "student" and session.get(session_auth.SESSION_UNIVERSITY_ID) is None:
        # 学生必须先选择学校与校区（BR-044、FR-A08）
        return _redirect_with_next("auth.student_context", target)

    field_errors: dict[str, str] = {}
    identifier_value = ""

    if request.method == "POST":
        identifier_value = request.form.get("identifier", "")
        password = request.form.get("password", "")
        student_university_id = (
            session.get(session_auth.SESSION_UNIVERSITY_ID) if role == "student" else None
        )
        try:
            user = auth_service.authenticate_password(
                role=role,
                identifier=identifier_value,
                password=password,
                student_university_id=student_university_id,
            )
            session_auth.login_user(user.id)
            return redirect(target or url_for("main.index"))
        except InputError as err:
            field_errors = err.field_errors
            if not field_errors:
                # 非字段级错误在页面顶部提示
                from flask import flash

                flash(err.message, "error")

    campus_display = _student_context_display()
    return render_template(
        "auth/login.html",
        role=role,
        role_display=_IDENTITY_ROLES[role],
        field_errors=field_errors,
        identifier_value=identifier_value,
        campus_display=campus_display,
        next_target=target,
    )


@bp.route("/register", methods=["GET", "POST"])
def register():
    """在校学生名单核验注册（BR-005、FR-A01 ~ FR-A03）。

    姓名、学院、专业、年级、班级和校区由名单带入，页面不提供编辑；
    注册成功后前往登录页（保留 next 目标）。
    """
    target = _target_from_request()
    if session_auth.get_identity_role() != "student":
        return _redirect_with_next("auth.identity", target)

    from flask import session

    university_id = session.get(session_auth.SESSION_UNIVERSITY_ID)
    campus_id = session.get(session_auth.SESSION_CAMPUS_ID)
    if university_id is None or campus_id is None:
        return _redirect_with_next("auth.student_context", target)

    context = auth_service.get_student_context()
    university = next((u for u in context["universities"] if u["id"] == university_id), None)
    if university is None:
        return _redirect_with_next("auth.student_context", target)

    field_errors: dict[str, str] = {}

    if request.method == "POST":
        form = {
            "student_no": request.form.get("student_no", ""),
            "phone": request.form.get("phone", ""),
            "password": request.form.get("password", ""),
            "password_confirm": request.form.get("password_confirm", ""),
        }
        try:
            if form["password"] != form["password_confirm"]:
                raise InputError(
                    "两次输入的密码不一致。",
                    field_errors={"password_confirm": "两次输入的密码不一致。"},
                )
            user = auth_service.register_student(
                university_id=university_id,
                campus_id=campus_id,
                student_no=form["student_no"],
                phone=form["phone"],
                password=form["password"],
            )
            session_auth.set_student_context(university_id, user.campus_id)
            from flask import flash

            flash("注册成功，请使用学号或手机号登录。", "success")
            return _redirect_with_next("auth.login", target)
        except InputError as err:
            field_errors = err.field_errors
            if not field_errors:
                from flask import flash

                flash(err.message, "error")

    return render_template(
        "auth/register.html",
        university=university,
        field_errors=field_errors,
        form=request.form if request.method == "POST" else {},
        next_target=target,
    )


@bp.post("/logout")
def logout():
    session_auth.logout_user()
    return redirect(url_for("auth.identity"))


def _student_context_display() -> str | None:
    """学生登录页展示已选学校和校区文案。"""
    if session_auth.get_identity_role() != "student":
        return None
    university_id = session.get(session_auth.SESSION_UNIVERSITY_ID)
    if university_id is None:
        return None
    context = auth_service.get_student_context()
    university = next((u for u in context["universities"] if u["id"] == university_id), None)
    if university is None:
        return None
    campus_id = session.get(session_auth.SESSION_CAMPUS_ID)
    campus = next((c for c in university["campuses"] if c["id"] == campus_id), None)
    if campus and not university["single_campus"]:
        return f"{university['name']} · {campus['name']}"
    return university["name"]
