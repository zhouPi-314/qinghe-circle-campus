"""公益与站点路由（FR-C01 ~ FR-C07、FR-R02/R03）。

路由只解析请求和输出模板；全部查询与业务规则在 charity_service /
circulation_service / org_service（route → service → model/database）。
"""

from __future__ import annotations

from datetime import UTC, datetime

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for

from app.core.errors import InputError
from app.core.permissions import login_required, roles_required
from app.services import charity_service, circulation_service, org_service

bp = Blueprint("charity", __name__)


@bp.get("/charity")
@login_required
def project_list():
    """公益项目列表（BR-033）。"""
    projects = charity_service.list_projects(g.current_user)
    return render_template(
        "charity/list.html",
        projects=projects,
        progress={p.id: charity_service.project_progress(p) for p in projects},
    )


@bp.get("/charity/<int:project_id>")
@login_required
def project_detail(project_id: int):
    """项目目标与募集进度（FR-C04）。"""
    project = charity_service.get_project(g.current_user, project_id)
    needs = charity_service.project_progress(project)
    receipts = [
        r
        for r in charity_service.list_published_receipts(g.current_user)
        if r.project_id == project.id
    ]
    stations = charity_service.list_university_charity_stations(g.current_user)
    return render_template(
        "charity/detail.html",
        project=project,
        needs=needs,
        receipts=receipts,
        stations=stations,
        is_student=g.current_user.is_student,
        expired=project.deadline <= datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# 项目创建与需求维护（FR-C01）：公益管理员（回收）/平台管理员
# ---------------------------------------------------------------------------


@bp.route("/charity/projects/new", methods=["GET", "POST"])
@roles_required("station_manager")
def new_project():
    """创建公益项目（FR-C01）：公益管理员需持有站点授权。"""
    from app.services import item_service

    if request.method == "POST":
        form = request.form
        needs = []
        index = 0
        while form.get(f"need_name_{index}"):
            needs.append(
                {
                    "item_category_id": form.get(f"need_category_{index}", type=int) or 0,
                    "item_name": form.get(f"need_name_{index}", ""),
                    "target_quantity": form.get(f"need_target_{index}", type=int) or 0,
                    "unit": form.get(f"need_unit_{index}", "件"),
                }
            )
            index += 1
        try:
            deadline = datetime.fromisoformat(form.get("deadline", ""))
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            project = charity_service.create_project(
                g.current_user,
                title=form.get("title", ""),
                description=form.get("description", ""),
                recipient_org=form.get("recipient_org", ""),
                public_summary=form.get("public_summary", ""),
                deadline=deadline,
                needs=needs,
            )
        except (InputError, ValueError) as err:
            message = err.field_errors and next(iter(err.field_errors.values()))
            flash(message or str(err), "error")
            # G4 加固：表单错误返回 400（原位提示保持可读）
            return render_template(
                "charity/new_project.html", categories=item_service.list_categories()
            ), 400
        else:
            flash("公益项目已创建，本校学生现在可以提交捐赠。", "success")
            return redirect(url_for("charity.project_detail", project_id=project.id))

    return render_template("charity/new_project.html", categories=item_service.list_categories())


@bp.post("/charity/<int:project_id>/needs")
@roles_required("station_manager")
def add_need(project_id: int):
    """向募集中项目追加物资需求（FR-C01）。"""
    try:
        charity_service.update_project_need(
            g.current_user,
            project_id,
            item_category_id=request.form.get("item_category_id", type=int) or 0,
            item_name=request.form.get("item_name", ""),
            target_quantity=request.form.get("target_quantity", type=int) or 0,
            unit=request.form.get("unit", "件"),
        )
    except (InputError, ValueError) as err:
        message = err.field_errors and next(iter(err.field_errors.values()))
        flash(message or str(err), "error")
    else:
        flash("物资需求已添加。", "success")
    return redirect(url_for("charity.project_detail", project_id=project_id))


# ---------------------------------------------------------------------------
# 捐赠（FR-C02、FR-C03）
# ---------------------------------------------------------------------------


@bp.route("/charity/<int:project_id>/donate", methods=["GET", "POST"])
@roles_required("student")
def donate(project_id: int):
    """提交实物捐赠表单（FR-C02）：物资明细可附图片，送入公益站点。"""
    project = charity_service.get_project(g.current_user, project_id)
    needs = charity_service.project_progress(project)

    if request.method == "POST":
        form = request.form
        station_id = form.get("station_id", type=int) or 0
        items = []
        for need in needs:
            quantity = form.get(f"quantity_{need.id}", type=int)
            if quantity:
                image_key = _upload_donation_image(need.id)
                items.append(
                    {
                        "need_id": need.id,
                        "quantity": quantity,
                        "condition": form.get(f"condition_{need.id}", "good"),
                        "note": form.get(f"note_{need.id}", ""),
                        "image_object_key": image_key,
                    }
                )
        try:
            charity_service.submit_donation(
                g.current_user,
                project_id,
                station_id=station_id,
                items=items,
                donor_note=form.get("donor_note", ""),
            )
        except InputError as err:
            for message in err.field_errors.values():
                flash(message, "error")
        else:
            flash("捐赠已提交，等待站点核验；核验接收后计入募集进度。", "success")
            return redirect(url_for("charity.project_detail", project_id=project.id))

    stations = charity_service.list_university_charity_stations(g.current_user)
    return render_template("charity/donate.html", project=project, needs=needs, stations=stations)


def _upload_donation_image(need_id: int) -> str | None:
    """捐赠物资图片上传（FR-C02）：可选，校验失败返回 None 不阻断捐赠。"""
    upload = request.files.get(f"image_{need_id}")
    if upload is None or not upload.filename:
        return None
    from app.core.storage import StorageError, storage_from_config

    try:
        config = current_app.config["APP_CONFIG"]
        storage = storage_from_config(config)
        return storage.put_image(upload.read(), upload.mimetype or "image/jpeg")
    except StorageError as err:
        flash(f"物资图片上传失败：{err}（捐赠本体不受影响）", "warning")
        return None
    except KeyError:
        flash("对象存储未配置，图片未上传（捐赠本体不受影响）。", "warning")
        return None


@bp.get("/charity/receipts/<int:receipt_id>")
@login_required
def receipt_detail(receipt_id: int):
    """已公示回执（FR-C07）：不含可识别个人信息（BR-039）。"""
    receipt = charity_service.get_published_receipt(g.current_user, receipt_id)
    return render_template("charity/receipt.html", receipt=receipt, items=receipt.items)


# ---------------------------------------------------------------------------
# 站点工作台（FR-M03）
# ---------------------------------------------------------------------------


@bp.get("/station/recycling")
@roles_required("station_manager")
def station_recycling():
    """回收验收（FR-R02、FR-R03）。"""
    requests_req = circulation_service.station_recycle_queue(g.current_user)
    return render_template("station/recycling.html", requests=requests_req)


@bp.get("/station/donations")
@roles_required("station_manager")
def station_donations():
    """公益捐赠核验（FR-C03）。"""
    donations = charity_service.station_donation_queue(g.current_user)
    return render_template("station/donations.html", donations=donations)


@bp.post("/station/donations/<int:donation_id>/review")
@roles_required("station_manager")
def review_donation(donation_id: int):
    """核验捐赠：接收（含分项确认数量）或拒绝。"""
    accept = request.form.get("decision") == "accept"
    accepted_quantities: dict[int, int] = {}
    try:
        for key, value in request.form.items():
            if key.startswith("accepted_"):
                if not value:
                    continue
                try:
                    item_id = int(key.removeprefix("accepted_"))
                    accepted_quantities[item_id] = int(value)
                except ValueError:
                    raise InputError(
                        "确认数量必须是整数。",
                        field_errors={"accepted_quantity": "确认数量必须是整数。"},
                    ) from None
    except InputError:
        flash("确认数量必须是整数，请检查后重新提交。", "error")
        return redirect(url_for("charity.station_donations"))
    try:
        charity_service.review_donation(
            g.current_user,
            donation_id,
            accept=accept,
            accepted_quantities=accepted_quantities or None,
            reject_reason=request.form.get("reject_reason", ""),
        )
    except InputError as err:
        for message in err.field_errors.values():
            flash(message, "error")
        return redirect(url_for("charity.station_donations"))
    if accept:
        flash("捐赠已核验接收，进度已更新。", "success")
    else:
        flash("已记录拒绝原因。", "warning")
    return redirect(url_for("charity.station_donations"))


@bp.route("/station/receipts/new", methods=["GET", "POST"])
@roles_required("station_manager")
def new_receipt():
    """公益回执登记（FR-C06）：物资可追溯授权站点已接收明细（BR-038）。"""
    selected_project_id = request.values.get("project_id", type=int)
    data = charity_service.receipt_form_data(g.current_user, selected_project_id)
    projects = data["projects"]
    donation_items = data["donation_items"]

    if request.method == "POST":
        items = []
        for donation_item in donation_items:
            quantity = request.form.get(f"receipt_{donation_item.id}", type=int)
            if quantity:
                items.append(
                    {
                        "donation_item_id": donation_item.id,
                        "item_name": donation_item.item_name,
                        "quantity": quantity,
                    }
                )
        try:
            received_at = datetime.fromisoformat(request.form.get("received_at", ""))
            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=UTC)
            receipt = charity_service.publish_receipt(
                g.current_user,
                selected_project_id,
                station_id=request.form.get("station_id", type=int) or 0,
                title=request.form.get("title", ""),
                recipient_org=request.form.get("recipient_org", ""),
                received_at=received_at,
                public_note=request.form.get("public_note", ""),
                items=items,
            )
        except (InputError, ValueError) as err:
            message = err.field_errors and next(iter(err.field_errors.values()))
            flash(message or str(err), "error")
            # G4 加固：表单错误返回 400（原位提示保持可读）
            return render_template(
                "station/new_receipt.html",
                projects=projects,
                selected_project_id=selected_project_id,
                donation_items=donation_items,
                stations=org_service.manager_scope(g.current_user),
            ), 400
        else:
            flash("回执已公示，本校用户可以查看。", "success")
            return redirect(url_for("charity.receipt_detail", receipt_id=receipt.id))

    stations = org_service.manager_scope(g.current_user)
    return render_template(
        "station/new_receipt.html",
        projects=projects,
        selected_project_id=selected_project_id,
        donation_items=donation_items,
        stations=stations,
    )
