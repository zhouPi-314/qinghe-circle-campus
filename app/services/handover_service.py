"""交接与异常 Service（G2：借用链的交接码、取消、争议）。

公开接口（交接书第 7 节，G2 实现借用所需部分）：
- issue_handover_code(actor, request_id)        交付方生成交接码
- confirm_handover(actor, request_id, code)     接收方输入交接码确认
- cancel_request(actor, request_id, reason)     交接前取消
- open_dispute(actor, request_id, reason)       发起争议
- resolve_dispute(actor, dispute_id, ...)       管理员处理争议

核心规则（SRS BR-016 ~ BR-020、BR-041、BR-042、FR-H01 ~ FR-H05）：
- 申请经有权一方确认后才可生成交接码；
- 交接码 6 位、10 分钟有效、一次性；重新生成后旧码失效；
- 只保存哈希（请求级盐 + 应用 pepper），不保存明文；
- 交接双方必须属于同一高校；服务端校验当前状态；
- 状态变更、状态历史、争议记录、通知在同一事务完成。
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from flask import current_app
from sqlalchemy import select

from app import db
from app.core.errors import ConflictError, InputError, NotFoundError, PermissionDeniedError
from app.core.permissions import ensure_actor_university, is_university_manager
from app.core.states import (
    DISPUTABLE_REQUEST_STATUSES,
    ITEM_IN_PROGRESS,
    ITEM_ON_HOLD,
    REQ_CANCELLED,
    REQ_COMPLETED,
    REQ_DISPUTED,
    REQ_HANDOVER_PENDING,
    REQ_IN_PROGRESS,
    REQ_PENDING,
    REQUEST_STATUS_LABELS,
    validate_request_transition,
)
from app.models.circulation import CirculationRequest, HandoverRecord
from app.models.governance import Dispute, DisputeMessage
from app.models.item import Item
from app.services.circulation_service import _get_request
from app.services.notification_service import notify_users, record_audit

CODE_TTL_SECONDS = 10 * 60


# ---------------------------------------------------------------------------
# 交接码
# ---------------------------------------------------------------------------


DELIVER_BY_OWNER_MODES = ("borrow", "sale", "give")


def _delivery_party(request: CirculationRequest) -> int:
    """BR-018：交付方生成交接码。

    借用/出售/赠送：交付方 = 物品所有者；回收：交付方 = 交出物品的用户。
    """
    if request.mode in DELIVER_BY_OWNER_MODES:
        return request.owner_user_id
    return request.requester_user_id


def issue_handover_code(actor, request_id: int) -> tuple[CirculationRequest, str]:
    """交付方生成交接码（FR-H01、BR-017）。

    - 仅交接前（待交接）可以生成；
    - 6 位数字、10 分钟有效；重新生成时 code_version +1，旧码立即失效；
    - 返回 (申请, 明文码)；明文只在本次响应展示，不入库。

    G4 加固：先锁申请行再锁交接记录行；重生成与确认并发时串行化，
    旧码不得在新码生成后成功消费。
    """
    request = _get_request(actor, request_id, require_participant="any", for_update=True)
    if request.status != REQ_HANDOVER_PENDING:
        raise ConflictError(
            f"申请当前状态（{REQUEST_STATUS_LABELS.get(request.status, request.status)}）"
            "不是待交接，不能生成交接码（BR-016）。"
        )
    if _delivery_party(request) != actor.id:
        raise PermissionDeniedError("只有交付方可以生成交接码（BR-018）。")

    now = datetime.now(UTC)
    code = f"{secrets.randbelow(1_000_000):06d}"
    # G4 加固：交接记录行锁，重生成与确认互斥（锁序：申请行 → 交接记录行）
    record = db.session.scalar(
        select(HandoverRecord)
        .where(HandoverRecord.request_id == request.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if record is None:
        record = HandoverRecord(
            request_id=request.id,
            generated_by_user_id=actor.id,
            generated_at=now,
        )
        db.session.add(record)
        version = 1
    else:
        version = record.code_version + 1
        record.generated_by_user_id = actor.id
        record.generated_at = now
        record.status = "active"
        record.consumed_by_user_id = None
        record.consumed_at = None

    record.code_hash = _handover_hash(request.id, version, code)
    record.code_version = version
    record.expires_at = now + timedelta(seconds=CODE_TTL_SECONDS)
    db.session.flush()

    notify_users(
        university_id=request.university_id,
        recipient_ids={_receiving_party(request)},
        category="handover",
        title="交接码已生成",
        body=f"「{request.item.title}」的交接码已生成，请在 10 分钟内与对方完成取件交接。",
        related_entity_type="circulation_request",
        related_entity_id=request.id,
    )
    db.session.commit()
    return request, code


def _receiving_party(request: CirculationRequest) -> int:
    """BR-018：接收方输入交接码。

    借用/出售/赠送：接收方 = 申请人；回收：接收方 = 站点（公益管理员）。
    """
    if request.mode in DELIVER_BY_OWNER_MODES:
        return request.requester_user_id
    return request.owner_user_id


def confirm_handover(actor, request_id: int, *, code: str) -> CirculationRequest:
    """接收方输入交接码完成交接（FR-B04、FR-R02、BR-018/BR-019）。

    借用：交接成功后进入借用中；出售/赠送：交接完成即业务完成；
    回收：送达交接后进入待站点验收。
    错误、过期或已用码不推进状态（异常需求）。

    G4 加固：先锁申请行再锁交接记录行；两个并发确认只有一个成功，
    另一个得到状态冲突（申请已不在待交接）或"交接码已使用"。
    """
    request = _get_request(actor, request_id, require_participant="any", for_update=True)
    if _receiving_party(request) != actor.id:
        raise PermissionDeniedError("只有接收方可以输入交接码完成交接。")
    if request.status != REQ_HANDOVER_PENDING:
        raise ConflictError("申请当前不是待交接状态，无法确认交接（交接码已使用或已失效）。")

    # G4 加固：交接记录行锁（锁序：申请行 → 交接记录行）
    record = db.session.scalar(
        select(HandoverRecord)
        .where(HandoverRecord.request_id == request.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if record is None or record.status != "active":
        raise InputError("交接码尚未生成或已使用，请联系对方重新生成。")
    if datetime.now(UTC) > record.expires_at:
        raise InputError("交接码已过期（10 分钟有效），请联系对方重新生成。")

    submitted = (code or "").strip()
    if not submitted:
        raise InputError("请输入交接码。", field_errors={"code": "请输入 6 位交接码。"})
    computed = _handover_hash(request.id, record.code_version, submitted)
    if not secrets.compare_digest(computed, record.code_hash):
        raise InputError("交接码不正确。请核对后重试；连续失败请联系对方重新生成。")

    # 一次性使用
    record.status = "used"
    record.consumed_by_user_id = actor.id
    record.consumed_at = datetime.now(UTC)

    now = datetime.now(UTC)
    from app.core.states import validate_item_transition

    if request.mode == "borrow":
        next_request_status, next_item_status = REQ_IN_PROGRESS, ITEM_IN_PROGRESS
        done_reason = "交接码验证成功，进入借用中"
        item_reason = "借用取件交接完成"
    elif request.mode in ("sale", "give"):
        next_request_status, next_item_status = REQ_COMPLETED, "completed"
        done_reason = (
            "交接码验证成功，交易完成" if request.mode == "sale" else "交接码验证成功，赠送完成"
        )
        item_reason = "交接完成，物品由新所有者接收"
    else:  # recycle
        next_request_status, next_item_status = "inspection_pending", ITEM_IN_PROGRESS
        done_reason = "送达交接成功，等待站点验收"
        item_reason = "回收物品送达站点，等待验收"

    validate_request_transition(request.status, next_request_status)
    request.status = next_request_status
    if next_request_status == REQ_COMPLETED:
        request.completed_at = now
    request.updated_at = now
    _write_request_history(
        request,
        from_status=REQ_HANDOVER_PENDING,
        to_status=next_request_status,
        actor_user_id=actor.id,
        reason=done_reason,
    )

    # G4 加固：锁序 申请行 → 交接记录行 → 物品行
    item = db.session.scalars(
        select(Item).where(Item.id == request.item_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    from_status = item.status
    validate_item_transition(from_status, next_item_status)
    item.status = next_item_status
    if request.mode in ("sale", "give"):
        # BR-015：出售/赠送交接完成即转移所有权，新所有者（接收方）可后续重新上架
        item.owner_user_id = request.requester_user_id
    item.updated_at = now
    _write_item_history(
        item,
        from_status=from_status,
        to_status=next_item_status,
        actor_user_id=actor.id,
        reason=item_reason,
    )

    counterpart = (
        request.owner_user_id
        if actor.id == request.requester_user_id
        else request.requester_user_id
    )
    notify_users(
        university_id=request.university_id,
        recipient_ids={counterpart},
        category="handover",
        title="物品已交接",
        body=f"「{request.item.title}」交接完成：{done_reason}。",
        related_entity_type="circulation_request",
        related_entity_id=request.id,
    )
    db.session.commit()
    return request


def handover_record_for(request_id: int) -> HandoverRecord | None:
    """读取当前交接记录（模板展示剩余有效期用）。"""
    return db.session.scalar(select(HandoverRecord).where(HandoverRecord.request_id == request_id))


# ---------------------------------------------------------------------------
# 取消
# ---------------------------------------------------------------------------


def cancel_request(actor, request_id: int, *, reason: str) -> CirculationRequest:
    """交接前取消（FR-H02、BR-014）。

    - pending：仅申请人可取消；
    - accepted / handover_pending：约定双方可取消；
    - 取消后物品恢复可申请。

    G4 加固：申请行锁内重检状态（锁序：申请行 → 物品行）。
    """
    request = _get_request(actor, request_id, require_participant="any", for_update=True)
    if not (request.requester_user_id == actor.id or request.owner_user_id == actor.id):
        raise NotFoundError("没有找到该流转申请。")
    if not (reason or "").strip():
        raise InputError("取消必须填写原因。", field_errors={"reason": "请填写取消原因。"})

    if request.status == REQ_PENDING:
        if request.requester_user_id != actor.id:
            raise PermissionDeniedError("待处理申请只能由申请人取消。")
    elif request.status in ("accepted", "payment_pending", "handover_pending"):
        pass  # 约定双方均可取消
    else:
        raise ConflictError("当前状态不能取消。交接后如需处理请发起争议（BR-028）。")

    now = datetime.now(UTC)
    from_status = request.status
    validate_request_transition(from_status, REQ_CANCELLED)
    request.status = REQ_CANCELLED
    request.updated_at = now

    _write_request_history(
        request,
        from_status=from_status,
        to_status=REQ_CANCELLED,
        actor_user_id=actor.id,
        reason=f"取消：{reason.strip()}",
    )
    _set_item_active(
        db.session.scalars(
            select(Item).where(Item.id == request.item_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one(),
        actor_user_id=actor.id,
        reason="申请取消，物品恢复可申请",
    )
    notify_users(
        university_id=request.university_id,
        recipient_ids={request.requester_user_id, request.owner_user_id} - {actor.id},
        category="request",
        title="流转申请已取消",
        body=f"「{request.item.title}」的流转申请已取消。物品已恢复可申请。",
        related_entity_type="circulation_request",
        related_entity_id=request.id,
    )
    db.session.commit()
    return request


# ---------------------------------------------------------------------------
# 争议
# ---------------------------------------------------------------------------


def open_dispute(actor, request_id: int, *, reason: str) -> Dispute:
    """参与人发起争议（FR-H04、BR-041）。G4 加固：申请行锁内重检状态。"""
    request = _get_request(actor, request_id, require_participant="any", for_update=True)
    return open_dispute_for_request(request, opened_by_user_id=actor.id, reason=reason)


def open_dispute_for_request(
    request: CirculationRequest, *, opened_by_user_id: int, reason: str
) -> Dispute:
    """在已校验归属的申请上开启争议（confirm_return 转争议时复用）。"""
    if request.status not in DISPUTABLE_REQUEST_STATUSES:
        raise ConflictError("当前状态不能发起争议。")
    if not (reason or "").strip():
        raise InputError("发起争议必须填写原因。", field_errors={"reason": "请填写争议原因。"})

    now = datetime.now(UTC)
    from_status = request.status
    validate_request_transition(from_status, REQ_DISPUTED)
    request.status = REQ_DISPUTED
    request.updated_at = now
    _write_request_history(
        request,
        from_status=from_status,
        to_status=REQ_DISPUTED,
        actor_user_id=opened_by_user_id,
        reason=f"发起争议：{reason.strip()}",
    )

    item = db.session.scalars(
        select(Item).where(Item.id == request.item_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    from app.core.states import validate_item_transition
    from app.services.circulation_service import _write_item_history

    item_from = item.status
    validate_item_transition(item_from, ITEM_ON_HOLD)
    item.status = ITEM_ON_HOLD
    item.updated_at = now
    _write_item_history(
        item,
        from_status=item_from,
        to_status=ITEM_ON_HOLD,
        actor_user_id=opened_by_user_id,
        reason="争议处理中，物品异常冻结",
    )

    dispute = Dispute(
        university_id=request.university_id,
        circulation_request_id=request.id,
        opened_by_user_id=opened_by_user_id,
        reason=reason.strip(),
        status="open",
        created_at=now,
        updated_at=now,
    )
    db.session.add(dispute)
    db.session.flush()
    db.session.add(
        DisputeMessage(
            dispute_id=dispute.id,
            author_user_id=opened_by_user_id,
            body=reason.strip(),
            created_at=now,
        )
    )
    notify_users(
        university_id=request.university_id,
        recipient_ids={request.requester_user_id, request.owner_user_id} - {opened_by_user_id},
        category="dispute",
        title="流转争议已发起",
        body=f"「{request.item.title}」存在争议，等待管理员处理。",
        related_entity_type="circulation_request",
        related_entity_id=request.id,
    )
    return dispute


def resolve_dispute(actor, dispute_id: int, *, resolution: str) -> Dispute:
    """管理员处理争议（FR-H05、BR-042）：记录结论并关闭业务。

    G4 加固：锁序固定 争议行 → 申请行 → 物品行，与并发处理串行化。
    """
    if not is_university_manager(actor):
        raise PermissionDeniedError("当前身份无法处理争议。")
    dispute = db.session.scalars(
        select(Dispute).where(Dispute.id == dispute_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if dispute is None:
        raise NotFoundError("没有找到该争议记录。")
    if actor.is_university_admin and dispute.university_id != actor.university_id:
        raise NotFoundError("没有找到该争议记录。")
    ensure_actor_university(actor, dispute.university_id)
    if dispute.status not in ("open", "reviewing"):
        raise ConflictError("该争议已处理完毕，不能重复处理（BR-042）。")
    if not (resolution or "").strip():
        raise InputError("处理结论必须填写。", field_errors={"resolution": "请填写处理结论。"})

    now = datetime.now(UTC)
    # 锁序：争议行（已锁）→ 申请行 → 物品行
    request = db.session.scalars(
        select(CirculationRequest)
        .where(CirculationRequest.id == dispute.circulation_request_id)
        .with_for_update().execution_options(populate_existing=True)
    ).first()
    dispute.status = "resolved"
    dispute.resolution = resolution.strip()
    dispute.resolved_by_user_id = actor.id
    dispute.resolved_at = now
    dispute.updated_at = now

    if request is not None and request.status == REQ_DISPUTED:
        validate_request_transition(REQ_DISPUTED, REQ_COMPLETED)
        request.status = REQ_COMPLETED
        request.completed_at = now
        request.updated_at = now
        _write_request_history(
            request,
            from_status=REQ_DISPUTED,
            to_status=REQ_COMPLETED,
            actor_user_id=actor.id,
            reason=f"争议处理完毕：{resolution.strip()}",
        )
        item = db.session.scalars(
            select(Item).where(Item.id == request.item_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one()
        from app.core.states import validate_item_transition
        from app.services.circulation_service import _write_item_history

        item_from = item.status
        validate_item_transition(item_from, "completed")
        item.status = "completed"
        item.updated_at = now
        _write_item_history(
            item,
            from_status=item_from,
            to_status="completed",
            actor_user_id=actor.id,
            reason="争议关闭，业务完成",
        )

    record_audit(
        actor_user_id=actor.id,
        university_id=dispute.university_id,
        action="dispute.resolve",
        entity_type="dispute",
        entity_id=dispute.id,
        detail={"resolution": resolution.strip()},
    )
    notify_users(
        university_id=dispute.university_id,
        recipient_ids={request.requester_user_id, request.owner_user_id} if request else set(),
        category="dispute",
        title="争议已处理",
        body=f"「{request.item.title if request else '相关物品'}」的争议已由管理员处理完毕。",
        related_entity_type="circulation_request",
        related_entity_id=request.id if request else None,
    )
    db.session.commit()
    return dispute


def dispute_messages_for(dispute_id: int) -> list[DisputeMessage]:
    """争议说明列表（参与双方与管理员可查看）。"""
    stmt = (
        select(DisputeMessage)
        .where(DisputeMessage.dispute_id == dispute_id)
        .order_by(DisputeMessage.created_at)
    )
    return list(db.session.scalars(stmt).all())


def list_open_disputes(actor) -> list[Dispute]:
    """管理员查看待处理争议；校级管理员仅本校（FR-H05）。"""
    if not is_university_manager(actor):
        raise PermissionDeniedError("当前身份无法查看争议列表。")
    stmt = (
        select(Dispute)
        .where(Dispute.status.in_(("open", "reviewing")))
        .order_by(Dispute.created_at)
    )
    if actor.is_university_admin:
        ensure_actor_university(actor, actor.university_id)
        stmt = stmt.where(Dispute.university_id == actor.university_id)
    return list(db.session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _handover_hash(request_id: int, code_version: int, code: str) -> str:
    """交接码哈希：请求级盐 + 应用 pepper，保证唯一且不可逆。"""
    pepper = current_app.config["SECRET_KEY"].encode("utf-8")
    raw = f"qinghe-handover-v1:{request_id}:{code_version}:{code.strip()}".encode()
    return hashlib.sha256(hashlib.sha256(raw).digest() + pepper).hexdigest()


def _write_request_history(request, *, from_status, to_status, actor_user_id, reason) -> None:
    from app.services.circulation_service import _write_request_history as _impl

    _impl(
        request,
        from_status=from_status,
        to_status=to_status,
        actor_user_id=actor_user_id,
        reason=reason,
    )


def _write_item_history(item, *, from_status, to_status, actor_user_id, reason) -> None:
    from app.services.circulation_service import _write_item_history as _impl

    _impl(
        item,
        from_status=from_status,
        to_status=to_status,
        actor_user_id=actor_user_id,
        reason=reason,
    )


def _set_item_active(item, *, actor_user_id: int, reason: str) -> None:
    from app.services.circulation_service import _set_item_status as _impl

    _impl(item, "active", actor_user_id=actor_user_id, reason=reason)
