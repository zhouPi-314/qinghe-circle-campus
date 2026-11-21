"""管理员路由：平台全局能力与校级管理员本校能力。

路由只解析请求和输出模板；全部查询与写操作在 service 层完成
（route → service → model/database，工程标准第 3 节）。
"""

from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from app.core.errors import InputError
from app.core.permissions import roles_required
from app.services import auth_service, handover_service, item_service, org_service

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.get("/")
@roles_required("platform_admin", "university_admin")
def overview():
    """管理概览：平台全局或校级管理员本校（FR-M01）。

    路由守卫只做第一道校验；service 层在 get_organization_tree(actor)
    内再次校验角色和高校边界（工程标准第 5 节）。
    """
    data = org_service.get_organization_tree(g.current_user)
    return render_template(
        "admin/overview.html",
        counts=data["counts"],
        universities=data["universities"],
    )


# ---------------------------------------------------------------------------
# 组织：高校、校区、站点与授权（FR-U02）
# ---------------------------------------------------------------------------


@bp.get("/organizations")
@roles_required("platform_admin", "university_admin")
def organizations():
    """高校、校区和站点管理（FR-U02）；校级管理员仅维护本校。"""
    universities = org_service.list_all_universities(g.current_user)
    campuses = org_service.list_campuses(g.current_user)
    stations = org_service.list_all_stations(g.current_user)
    managers = org_service.list_station_managers(g.current_user)
    return render_template(
        "admin/organizations.html",
        universities=universities,
        campuses=campuses,
        stations=stations,
        managers=managers,
    )


@bp.post("/organizations/universities")
@roles_required("platform_admin")
def create_university():
    """新增高校（FR-U02）。"""
    try:
        org_service.create_university(
            g.current_user,
            code=request.form.get("code", ""),
            name=request.form.get("name", ""),
            province=request.form.get("province", ""),
            city=request.form.get("city", ""),
            education_level=request.form.get("education_level", "undergraduate"),
            ownership=request.form.get("ownership", "public"),
        )
    except InputError as err:
        _flash_input_error(err)
        return redirect(url_for("admin.organizations"))
    flash("高校已创建。", "success")
    return redirect(url_for("admin.organizations"))


@bp.post("/organizations/universities/<int:university_id>/update")
@roles_required("platform_admin")
def update_university(university_id: int):
    """维护高校名称、城市与状态（FR-U02）。"""
    fields = {}
    for key in ("name", "city", "status"):
        value = request.form.get(key, "").strip()
        if value:
            fields[key] = value
    try:
        org_service.update_university(g.current_user, university_id, fields=fields)
    except InputError as err:
        _flash_input_error(err)
        return redirect(url_for("admin.organizations"))
    flash("高校信息已更新。", "success")
    return redirect(url_for("admin.organizations"))


@bp.post("/organizations/campuses")
@roles_required("platform_admin", "university_admin")
def create_campus():
    try:
        org_service.create_campus(
            g.current_user,
            university_id=request.form.get("university_id", type=int) or 0,
            code=request.form.get("code", ""),
            name=request.form.get("name", ""),
            is_primary=request.form.get("is_primary") == "1",
        )
    except InputError as err:
        _flash_input_error(err)
        return redirect(url_for("admin.organizations"))
    flash("校区已创建。", "success")
    return redirect(url_for("admin.organizations"))


@bp.post("/organizations/stations")
@roles_required("platform_admin", "university_admin")
def create_station():
    try:
        org_service.create_station(
            g.current_user,
            campus_id=request.form.get("campus_id", type=int) or 0,
            name=request.form.get("name", ""),
            station_type=request.form.get("station_type", "mixed"),
            address=request.form.get("address", ""),
        )
    except InputError as err:
        _flash_input_error(err)
        return redirect(url_for("admin.organizations"))
    flash("站点已创建。", "success")
    return redirect(url_for("admin.organizations"))


@bp.post("/organizations/assignments")
@roles_required("platform_admin", "university_admin")
def assign_station_manager():
    from datetime import date

    try:
        org_service.assign_station_manager(
            g.current_user,
            station_id=request.form.get("station_id", type=int) or 0,
            user_id=request.form.get("user_id", type=int) or 0,
            started_on=date.today(),
        )
    except InputError as err:
        _flash_input_error(err)
        return redirect(url_for("admin.organizations"))
    flash("站点授权已建立。", "success")
    return redirect(url_for("admin.organizations"))


# ---------------------------------------------------------------------------
# 账号与名单（BR-007、FR-U03、FR-U04）
# ---------------------------------------------------------------------------


@bp.get("/users")
@roles_required("platform_admin", "university_admin")
def users():
    """账号与角色管理（BR-007）。"""
    rows = auth_service.list_all_users(g.current_user)
    universities = auth_service.list_universities(g.current_user)
    return render_template("admin/users.html", users=rows, universities=universities)


@bp.post("/users/import")
@roles_required("platform_admin", "university_admin")
def import_managed_account():
    try:
        auth_service.import_managed_accounts(
            g.current_user,
            university_id=request.form.get("university_id", type=int),
            login_name=request.form.get("login_name", ""),
            role=request.form.get("role", ""),
            password=request.form.get("password", ""),
            nickname=request.form.get("nickname", ""),
        )
    except InputError as err:
        _flash_input_error(err)
        return redirect(url_for("admin.users"))
    flash("管理员账号已创建，请通知本人首次登录后修改密码。", "success")
    return redirect(url_for("admin.users"))


@bp.post("/users/<int:user_id>/status")
@roles_required("platform_admin", "university_admin")
def update_user_status(user_id: int):
    try:
        auth_service.set_user_status(
            g.current_user, user_id, status=request.form.get("status", "")
        )
    except InputError as err:
        _flash_input_error(err)
        return redirect(url_for("admin.users"))
    flash("账号状态已更新。", "success")
    return redirect(url_for("admin.users"))


@bp.get("/student-imports")
@roles_required("platform_admin", "university_admin")
def student_imports():
    """学生名单导入（FR-U03、FR-U04）。"""
    batches = auth_service.list_import_batches(g.current_user)
    universities = auth_service.list_universities(g.current_user)
    return render_template("admin/student_imports.html", batches=batches, universities=universities)


@bp.post("/student-imports")
@roles_required("platform_admin", "university_admin")
def upload_roster():
    """上传 UTF-8 CSV 学生名单（中文或英文表头均可）。"""
    upload = request.files.get("roster")
    if upload is None or not upload.filename:
        flash("请选择 CSV 文件。", "error")
        return redirect(url_for("admin.student_imports"))
    try:
        batch = auth_service.import_students(
            g.current_user,
            university_id=request.form.get("university_id", type=int) or 0,
            csv_bytes=upload.read(),
        )
    except InputError as err:
        _flash_input_error(err)
        return redirect(url_for("admin.student_imports"))
    flash(
        f"导入完成：成功 {batch.success_rows} 行，失败 {batch.failed_rows} 行。",
        "success" if batch.failed_rows == 0 else "warning",
    )
    return redirect(url_for("admin.student_imports"))


# ---------------------------------------------------------------------------
# 审核、争议与审计（FR-M02 ~ FR-M04）
# ---------------------------------------------------------------------------


@bp.get("/moderation")
@roles_required("platform_admin", "university_admin")
def moderation():
    """内容审核（FR-M02）：下架违规物品并记录原因。"""
    rows = item_service.list_recent_items(g.current_user)
    return render_template("admin/moderation.html", items=rows)


@bp.post("/moderation/<int:item_id>/off-shelf")
@roles_required("platform_admin", "university_admin")
def force_off_shelf(item_id: int):
    try:
        item_service.change_item_shelf_state(
            g.current_user, item_id, action="force_off_shelf", reason=request.form.get("reason", "")
        )
    except InputError as err:
        _flash_input_error(err)
        return redirect(url_for("admin.moderation"))
    flash("物品已按 BR-043 处理并记录审计。", "warning")
    return redirect(url_for("admin.moderation"))


@bp.get("/disputes")
@roles_required("platform_admin", "university_admin")
def disputes():
    """争议处理（FR-H05、BR-042）。"""
    rows = handover_service.list_open_disputes(g.current_user)
    return render_template("admin/disputes.html", disputes=rows)


@bp.post("/disputes/<int:dispute_id>/resolve")
@roles_required("platform_admin", "university_admin")
def resolve_dispute(dispute_id: int):
    try:
        handover_service.resolve_dispute(
            g.current_user, dispute_id, resolution=request.form.get("resolution", "")
        )
    except InputError as err:
        _flash_input_error(err)
        return redirect(url_for("admin.disputes"))
    flash("争议已处理并关闭。", "success")
    return redirect(url_for("admin.disputes"))


@bp.get("/audit")
@roles_required("platform_admin", "university_admin")
def audit():
    """审计日志查询（FR-M04）。"""
    from app.services import notification_service

    rows = notification_service.list_audit_logs(g.current_user, limit=100)
    return render_template("admin/audit.html", logs=rows)


def _flash_input_error(err: InputError) -> None:
    """表单校验错误统一提示；无字段明细时展示主信息。"""
    if err.field_errors:
        for message in err.field_errors.values():
            flash(message, "error")
    else:
        flash(err.message, "error")
