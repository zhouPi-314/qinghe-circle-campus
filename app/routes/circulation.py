"""流转申请路由（G2：共享借还闭环）。

路由只解析请求和输出模板；业务规则在 circulation_service 与 handover_service。
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from app.core.errors import InputError
from app.core.permissions import login_required, roles_required
from app.services import circulation_service, handover_service

bp = Blueprint("circulation", __name__)


@bp.post("/items/<int:item_id>/borrow")
@login_required
def request_borrow(item_id: int):
    """提交借用申请（FR-B01）。"""
    try:
        start = date.fromisoformat(request.form.get("start_date", ""))
        due = date.fromisoformat(request.form.get("due_date", ""))
    except ValueError:
        raise InputError("借期日期格式有误。") from None
    note = request.form.get("request_note", "")

    try:
        requests_req = circulation_service.request_borrow(
            g.current_user, item_id, start_date=start, due_date=due, request_note=note
        )
    except InputError as err:
        for message in err.field_errors.values():
            flash(message, "error")
        return redirect(url_for("items.detail", item_id=item_id))
    flash("借用申请已提交，等待出借人处理。", "success")
    return redirect(url_for("circulation.request_detail", request_id=requests_req.id))


@bp.get("/requests/<int:request_id>")
@login_required
def request_detail(request_id: int):
    """流转详情（FR-B02 ~ FR-B07、FR-H01 ~ FR-H03）：时间线与按状态出现的操作。"""
    actor = g.current_user
    request = circulation_service.get_request_detail(actor, request_id)
    history = circulation_service.request_history(request)
    details = circulation_service.borrow_details_of(request)
    record = handover_service.handover_record_for(request.id)
    dispute = _dispute_for(request.id)

    is_requester = request.requester_user_id == actor.id
    is_owner = request.owner_user_id == actor.id
    overdue = circulation_service.is_overdue(request)

    return render_template(
        "requests/detail.html",
        req=request,
        details=details,
        history=history,
        record=record,
        dispute=dispute,
        dispute_messages=handover_service.dispute_messages_for(dispute.id) if dispute else [],
        is_requester=is_requester,
        is_owner=is_owner,
        is_admin=actor.is_platform_admin,
        overdue=overdue,
    )


def _dispute_for(request_id: int):
    from sqlalchemy import select

    from app import db
    from app.models.governance import Dispute

    return db.session.scalar(
        select(Dispute).where(
            Dispute.circulation_request_id == request_id, Dispute.status.in_(("open", "reviewing"))
        )
    )


@bp.post("/requests/<int:request_id>/decide")
@login_required
def decide(request_id: int):
    """所有者接受或拒绝申请（FR-B02）。"""
    decision = request.form.get("decision", "")
    circulation_service.decide_request(g.current_user, request_id, decision=decision)
    if decision == "accept":
        flash("已接受申请，现在可以生成交接码。", "success")
    else:
        flash("已拒绝申请，物品恢复可申请。", "info")
    return redirect(url_for("circulation.request_detail", request_id=request_id))


@bp.post("/requests/<int:request_id>/cancel")
@login_required
def cancel(request_id: int):
    """交接前取消（FR-H02）。"""
    reason = request.form.get("reason", "")
    handover_service.cancel_request(g.current_user, request_id, reason=reason)
    flash("申请已取消，物品恢复可申请。", "info")
    return redirect(url_for("circulation.request_detail", request_id=request_id))


@bp.post("/requests/<int:request_id>/issue-code")
@login_required
def issue_code(request_id: int):
    """生成交接码（FR-H01）：明文仅本次展示。"""
    _, code = handover_service.issue_handover_code(g.current_user, request_id)
    flash(f"交接码已生成（10 分钟内有效）：{code}。请当面出示给借用人输入。", "success")
    return redirect(url_for("circulation.request_detail", request_id=request_id))


@bp.post("/requests/<int:request_id>/confirm-handover")
@login_required
def confirm_handover(request_id: int):
    """输入交接码完成取件（FR-B04）。"""
    code = request.form.get("code", "")
    try:
        handover_service.confirm_handover(g.current_user, request_id, code=code)
    except InputError as err:
        for message in err.field_errors.values():
            flash(message, "error")
        return redirect(url_for("circulation.request_detail", request_id=request_id))
    flash("交接完成，物品进入借用中。", "success")
    return redirect(url_for("circulation.request_detail", request_id=request_id))


@bp.post("/requests/<int:request_id>/return")
@login_required
def submit_return(request_id: int):
    """借用人提交归还（FR-B06）。"""
    note = request.form.get("return_note", "")
    try:
        circulation_service.submit_return(g.current_user, request_id, return_note=note)
    except InputError as err:
        for message in err.field_errors.values():
            flash(message, "error")
        return redirect(url_for("circulation.request_detail", request_id=request_id))
    flash("归还已提交，等待出借人确认。", "success")
    return redirect(url_for("circulation.request_detail", request_id=request_id))


@bp.post("/requests/<int:request_id>/confirm-return")
@login_required
def confirm_return(request_id: int):
    """出借人确认归还或转争议（FR-B07）。"""
    condition_ok = request.form.get("condition_ok") == "ok"
    note = request.form.get("note", "")
    circulation_service.confirm_return(
        g.current_user, request_id, condition_ok=condition_ok, note=note
    )
    if condition_ok:
        flash("借用已完成。", "success")
    else:
        flash("已转入争议处理，等待平台管理员处理。", "warning")
    return redirect(url_for("circulation.request_detail", request_id=request_id))


@bp.post("/requests/<int:request_id>/dispute")
@login_required
def open_dispute(request_id: int):
    """参与人发起争议（FR-H04）。"""
    reason = request.form.get("reason", "")
    handover_service.open_dispute(g.current_user, request_id, reason=reason)
    flash("争议已提交，等待平台管理员处理。", "warning")
    return redirect(url_for("circulation.request_detail", request_id=request_id))


@bp.get("/me/requests")
@login_required
def my_requests():
    """我的申请与待我处理。"""
    data = circulation_service.list_requests_for(g.current_user)
    return render_template("me/requests.html", mine=data["mine"], incoming=data["incoming"])


@bp.get("/me/notifications")
@login_required
def notifications():
    """站内通知（FR-H06）。"""
    unread_only = request.args.get("filter") == "unread"
    rows = _notification_service_list(unread_only)
    return render_template("me/notifications.html", notifications=rows, unread_only=unread_only)


@bp.post("/me/notifications/<int:notification_id>/read")
@login_required
def mark_notification(notification_id: int):
    from app.services import notification_service

    notification_service.mark_notification_read(g.current_user, notification_id)
    return redirect(url_for("circulation.notifications"))


def _notification_service_list(unread_only: bool):
    from app.services import notification_service

    return notification_service.list_notifications(g.current_user, unread_only=unread_only)


# ---------------------------------------------------------------------------
# 出售 / 赠送 / 回收（G3）
# ---------------------------------------------------------------------------


@bp.post("/items/<int:item_id>/purchase")
@login_required
def request_purchase(item_id: int):
    """提交购买申请（FR-S01）。"""
    from app.services import circulation_service as cs

    try:
        created = cs.request_purchase(
            g.current_user, item_id, request_note=request.form.get("request_note", "")
        )
    except InputError as err:
        for message in err.field_errors.values():
            flash(message, "error")
        return redirect(url_for("items.detail", item_id=item_id))
    flash("购买申请已提交，等待卖家确认。", "success")
    return redirect(url_for("circulation.request_detail", request_id=created.id))


@bp.post("/items/<int:item_id>/giveaway")
@login_required
def request_giveaway(item_id: int):
    """提交领取申请（FR-G01）。"""
    from app.services import circulation_service as cs

    try:
        created = cs.request_giveaway(
            g.current_user, item_id, request_note=request.form.get("request_note", "")
        )
    except InputError as err:
        for message in err.field_errors.values():
            flash(message, "error")
        return redirect(url_for("items.detail", item_id=item_id))
    flash("领取申请已提交，等待发布者确认。", "success")
    return redirect(url_for("circulation.request_detail", request_id=created.id))


@bp.post("/items/<int:item_id>/recycle")
@login_required
def request_recycle(item_id: int):
    """提交回收申请（FR-R01）：选择本校站点与送达时段。"""
    from datetime import datetime

    from app.services import circulation_service as cs

    try:
        start = datetime.fromisoformat(request.form.get("preferred_start", ""))
        end = datetime.fromisoformat(request.form.get("preferred_end", ""))
    except ValueError:
        raise InputError("送达时段格式有误。") from None
    try:
        created = cs.request_recycle(
            g.current_user,
            item_id,
            station_id=request.form.get("station_id", type=int) or 0,
            preferred_start_at=start,
            preferred_end_at=end,
            request_note=request.form.get("request_note", ""),
        )
    except InputError as err:
        for message in err.field_errors.values():
            flash(message, "error")
        return redirect(url_for("items.detail", item_id=item_id))
    flash("回收申请已提交，等待站点处理。", "success")
    return redirect(url_for("circulation.request_detail", request_id=created.id))


@bp.post("/requests/<int:request_id>/pay")
@login_required
def simulate_payment(request_id: int):
    """模拟支付（FR-S02）：成功 / 失败 / 取消。"""
    from app.services import circulation_service as cs

    outcome = request.form.get("outcome", "")
    cs.simulate_payment(g.current_user, request_id, outcome=outcome)
    if outcome == "success":
        flash("模拟支付成功（教学模拟，不产生真实扣款）。", "success")
    else:
        flash("支付未完成，物品已恢复可申请。", "warning")
    return redirect(url_for("circulation.request_detail", request_id=request_id))


@bp.post("/requests/<int:request_id>/inspect")
@login_required
def inspect_recycle(request_id: int):
    """站点验收（FR-R03、BR-031）。"""
    from app.services import circulation_service as cs

    passed = request.form.get("result") == "accept"
    updated = cs.inspect_recycle(
        g.current_user, request_id, passed=passed, note=request.form.get("note", "")
    )
    if passed:
        flash("验收通过，回收完成并计入环保贡献。", "success")
    else:
        flash("已记录验收不通过原因，物品已下架。", "warning")
    return redirect(url_for("circulation.request_detail", request_id=updated.id))


@bp.get("/station")
@roles_required("station_manager")
def station_workbench():
    """站点工作台（FR-M03）：本站点回收待办与公益待核验。"""
    from app.services import charity_service, circulation_service, org_service

    actor = g.current_user
    stations = org_service.manager_scope(actor)
    pending_recycles = circulation_service.station_recycle_queue(actor)
    pending_donations = charity_service.station_donation_queue(actor)
    return render_template(
        "station/workbench.html",
        stations=stations,
        pending_recycles=pending_recycles,
        pending_donations=pending_donations,
    )
