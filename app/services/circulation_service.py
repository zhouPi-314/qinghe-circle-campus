"""流转申请 Service（G2：共享借还）。

公开接口（交接书第 7 节，G2 实现借用链）：
- request_borrow(actor, item_id, ...)      提交借用申请
- decide_request(actor, request_id, ...)   所有者接受 / 拒绝
- submit_return(actor, request_id, ...)    借用人提交归还
- confirm_return(actor, request_id, ...)   出借人确认归还（或转争议）
- list_requests_for(actor)                 我的申请 / 待我处理

交接与异常接口在 handover_service（issue_handover_code、confirm_handover、
cancel_request、open_dispute、resolve_dispute）。
出售、赠送、回收模式按同一共享模式在 G3 复制实现。

核心规则（SRS BR-011 ~ BR-024）：
- 申请模式必须与物品模式一致；不允许自我申请；跨校拒绝；
- 同一物品同一时间最多一条活动申请（数据库唯一索引 + service 防护）；
- 借用必须有起止日期，归还日期不得早于开始日期（BR-021）；
- 批准时校验相同物品借期不重叠（BR-022）；
- 超过预计归还日期显示逾期，页面动态计算（BR-024）；
- 状态变更、状态历史、通知在同一事务完成。
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select

from app import db
from app.core.display import DISPLAY_TZ
from app.core.errors import ConflictError, InputError, NotFoundError, PermissionDeniedError
from app.core.states import (
    ITEM_ACTIVE,
    ITEM_RESERVED,
    REQ_ACCEPTED,
    REQ_CANCELLED,
    REQ_COMPLETED,
    REQ_HANDOVER_PENDING,
    REQ_IN_PROGRESS,
    REQ_PAYMENT_PENDING,
    REQ_PENDING,
    REQ_REJECTED,
    REQ_RETURN_PENDING,
    REQUEST_STATUS_LABELS,
    validate_request_transition,
)
from app.models.circulation import (
    BorrowDetails,
    CirculationRequest,
    RecycleDetails,
    SaleDetails,
)
from app.models.governance import StatusHistory
from app.models.item import Item
from app.models.user import User
from app.services.item_service import get_visible_item
from app.services.notification_service import notify_users

# 已批准借期占用中的状态（用于借期冲突校验）
_OCCUPYING_STATUSES = (
    REQ_ACCEPTED,
    REQ_HANDOVER_PENDING,
    REQ_IN_PROGRESS,
    REQ_RETURN_PENDING,
)


# ---------------------------------------------------------------------------
# 提交借用申请
# ---------------------------------------------------------------------------


def request_borrow(
    actor, item_id: int, *, start_date: date, due_date: date, request_note: str | None = None
) -> CirculationRequest:
    """提交借用申请（FR-B01）。

    - 只允许在校学生申请；不允许申请自己的物品；
    - 物品必须处于可申请状态（BR-012/BR-014）；
    - 归还日期不得早于开始日期（BR-021）；
    - 创建活动申请后物品进入"已被申请"。
    """
    if not actor.is_student:
        raise PermissionDeniedError("只有在校学生可以申请借用。")
    if due_date < start_date:
        raise InputError(
            "预计归还日期不能早于开始日期。",
            field_errors={"due_date": "归还日期不能早于开始日期。"},
        )

    item = get_visible_item(actor, item_id)
    # G4 加固：申请前锁定物品行并重检（BR-012 活动申请互斥）
    item = _lock_item(item.id, mode="borrow", owner_must_differ_from=actor.id)

    now = datetime.now(UTC)
    request = CirculationRequest(
        university_id=actor.university_id,
        item_id=item.id,
        requester_user_id=actor.id,
        owner_user_id=item.owner_user_id,
        mode="borrow",
        status=REQ_PENDING,
        request_note=(request_note or "").strip() or None,
        created_at=now,
        updated_at=now,
    )
    db.session.add(request)
    db.session.flush()

    details = BorrowDetails(request_id=request.id, start_date=start_date, due_date=due_date)
    db.session.add(details)
    db.session.flush()

    _write_request_history(
        request,
        from_status=None,
        to_status=REQ_PENDING,
        actor_user_id=actor.id,
        reason="提交借用申请",
    )
    _set_item_status(item, ITEM_RESERVED, actor_user_id=actor.id, reason="存在待处理的借用申请")
    notify_users(
        university_id=actor.university_id,
        recipient_ids={item.owner_user_id},
        category="request",
        title="收到新的借用申请",
        body=f"你的物品「{item.title}」收到新的借用申请（{start_date} 至 {due_date}）。",
        related_entity_type="circulation_request",
        related_entity_id=request.id,
    )
    db.session.commit()
    return request


# ---------------------------------------------------------------------------
# 接受 / 拒绝
# ---------------------------------------------------------------------------


def decide_request(actor, request_id: int, *, decision: str) -> CirculationRequest:
    """所有者接受或拒绝借用申请（FR-B02）。

    - 接受：校验借期不重叠（BR-022），进入待交接；
    - 拒绝：物品恢复可申请（BR-014）。
    """
    request = _get_request(actor, request_id, require_participant="owner", for_update=True)
    if decision not in ("accept", "reject"):
        raise InputError("无效的处理决定。")

    if request.status != REQ_PENDING:
        current = REQUEST_STATUS_LABELS.get(request.status, request.status)
        raise ConflictError(f"申请当前状态（{current}）不是待处理。")

    now = datetime.now(UTC)
    if decision == "accept":
        if request.mode == "recycle":
            _ensure_station_authorization(actor, request)
        if request.mode == "borrow":
            details = _borrow_details(request)
            _ensure_no_date_conflict(request, details.start_date, details.due_date)
        validate_request_transition(request.status, REQ_ACCEPTED)
        if request.mode == "sale":
            # 出售：接受后进入待模拟支付（6.2 状态机 pending→accepted→payment_pending）
            validate_request_transition(REQ_ACCEPTED, REQ_PAYMENT_PENDING)
            request.status = REQ_PAYMENT_PENDING
            accept_reason = "卖家接受申请，等待买家完成模拟支付"
            notify_title = "购买申请已被接受"
            notify_body = "卖家已接受你的购买申请，请到申请详情页完成模拟支付。"
        else:
            # 借用/赠送/回收：接受后服务端准备交接 accepted -> handover_pending
            validate_request_transition(REQ_ACCEPTED, REQ_HANDOVER_PENDING)
            request.status = REQ_HANDOVER_PENDING
            accept_reason = "所有者接受申请，进入待交接"
            notify_title = "申请已被接受"
            notify_body = "对方已接受你的申请，等待对方生成交接码后完成取件。"
        request.responded_at = now
        request.updated_at = now
        _write_request_history(
            request,
            from_status=REQ_PENDING,
            to_status=request.status,
            actor_user_id=actor.id,
            reason=accept_reason,
        )
        notify_users(
            university_id=request.university_id,
            recipient_ids={request.requester_user_id},
            category="request",
            title=notify_title,
            body=f"「{request.item.title}」：{notify_body}",
            related_entity_type="circulation_request",
            related_entity_id=request.id,
        )
    else:
        validate_request_transition(request.status, REQ_REJECTED)
        request.status = REQ_REJECTED
        request.responded_at = now
        request.updated_at = now
        _write_request_history(
            request,
            from_status=REQ_PENDING,
            to_status=REQ_REJECTED,
            actor_user_id=actor.id,
            reason="站点拒绝回收申请" if request.mode == "recycle" else "所有者拒绝申请",
        )
        if request.mode == "recycle":
            # D-036：回收拒绝后物品不自动回到可申请，所有者可重新上架
            _set_item_status(
                _lock_item_row(request.item_id),
                "off_shelf",
                actor_user_id=actor.id,
                reason="回收申请被站点拒绝，物品由所有者决定重新上架（D-036）",
            )
        else:
            _set_item_status(
                _lock_item_row(request.item_id),
                ITEM_ACTIVE,
                actor_user_id=actor.id,
                reason="申请被拒绝，物品恢复可申请",
            )
        notify_users(
            university_id=request.university_id,
            recipient_ids={request.requester_user_id},
            category="request",
            title="申请被拒绝",
            body=f"你关于「{request.item.title}」的申请被拒绝，物品已恢复可申请。",
            related_entity_type="circulation_request",
            related_entity_id=request.id,
        )
    db.session.commit()
    return request


# ---------------------------------------------------------------------------
# 归还
# ---------------------------------------------------------------------------


def submit_return(actor, request_id: int, *, return_note: str) -> CirculationRequest:
    """借用人提交归还（FR-B06）。借用中 -> 待归还确认。"""
    request = _get_request(actor, request_id, require_participant="requester", for_update=True)
    if request.status != REQ_IN_PROGRESS:
        raise ConflictError("只有借用中的申请可以提交归还。")
    if not (return_note or "").strip():
        raise InputError("请填写归还说明。", field_errors={"return_note": "请填写归还说明。"})

    now = datetime.now(UTC)
    details = _borrow_details(request)
    details.return_note = return_note.strip()
    details.return_submitted_at = now
    details.returned_at = now

    validate_request_transition(request.status, REQ_RETURN_PENDING)
    request.status = REQ_RETURN_PENDING
    request.updated_at = now
    _write_request_history(
        request,
        from_status=REQ_IN_PROGRESS,
        to_status=REQ_RETURN_PENDING,
        actor_user_id=actor.id,
        reason="借用人提交归还",
    )
    notify_users(
        university_id=request.university_id,
        recipient_ids={request.owner_user_id},
        category="request",
        title="借用人已提交归还",
        body=f"「{request.item.title}」的借用人已提交归还，请确认物品状态。",
        related_entity_type="circulation_request",
        related_entity_id=request.id,
    )
    db.session.commit()
    return request


def confirm_return(
    actor, request_id: int, *, condition_ok: bool, note: str | None = None
) -> CirculationRequest:
    """出借人确认归还或转争议（FR-B07）。

    - condition_ok = True：借用完成，物品进入已完成；
    - condition_ok = False：转入争议处理（BR-023）。
    """
    request = _get_request(actor, request_id, require_participant="owner", for_update=True)
    if request.status != REQ_RETURN_PENDING:
        raise ConflictError("只有待归还确认的申请可以确认归还。")

    now = datetime.now(UTC)
    details = _borrow_details(request)
    details.condition_ok = condition_ok
    details.return_confirmed_at = now

    if condition_ok:
        validate_request_transition(request.status, REQ_COMPLETED)
        request.status = REQ_COMPLETED
        request.completed_at = now
        request.updated_at = now
        _write_request_history(
            request,
            from_status=REQ_RETURN_PENDING,
            to_status=REQ_COMPLETED,
            actor_user_id=actor.id,
            reason="出借人确认归还，借用完成",
        )
        _set_item_status(
            _lock_item_row(request.item_id),
            "completed",
            actor_user_id=actor.id,
            reason="借用完成",
        )
        notify_users(
            university_id=request.university_id,
            recipient_ids={request.requester_user_id},
            category="request",
            title="借用已完成",
            body=f"「{request.item.title}」的借用已完成。所有者可选择重新上架该物品。",
            related_entity_type="circulation_request",
            related_entity_id=request.id,
        )
    else:
        # 归还异常转争议：由 handover_service 统一处理状态与争议记录（BR-023）
        from app.services.handover_service import open_dispute_for_request

        open_dispute_for_request(
            request,
            opened_by_user_id=actor.id,
            reason=(note or "").strip() or "出借人确认归还时发现物品损坏或描述不符。",
        )
    db.session.commit()
    return request


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


def get_request_detail(actor, request_id: int) -> CirculationRequest:
    """读取流转申请详情；仅参与双方与管理员可见（BR-002）。"""
    request = db.session.get(CirculationRequest, request_id)
    if request is None or request.university_id != actor.university_id:
        raise NotFoundError("没有找到该流转申请。")
    if not (
        request.requester_user_id == actor.id
        or request.owner_user_id == actor.id
        or actor.is_platform_admin
    ):
        raise NotFoundError("没有找到该流转申请。")
    return request


def list_requests_for(actor) -> dict[str, list[CirculationRequest]]:
    """我的申请与待我处理（FR-B02 列表入口）。"""
    mine = db.session.scalars(
        select(CirculationRequest)
        .where(CirculationRequest.requester_user_id == actor.id)
        .order_by(CirculationRequest.created_at.desc())
    ).all()
    incoming = db.session.scalars(
        select(CirculationRequest)
        .where(CirculationRequest.owner_user_id == actor.id)
        .order_by(CirculationRequest.created_at.desc())
    ).all()
    return {"mine": list(mine), "incoming": list(incoming)}


def borrow_details_of(request: CirculationRequest) -> BorrowDetails | None:
    """借用明细（详情页展示；非借用模式返回 None）。"""
    if request.mode != "borrow":
        return None
    return db.session.get(BorrowDetails, request.id)


def is_overdue(request: CirculationRequest, today: date | None = None) -> bool:
    """借用是否逾期：超过预计归还日期仍未归还（BR-024，页面动态计算）。"""
    if request.mode != "borrow" or request.status != REQ_IN_PROGRESS:
        return False
    details = _borrow_details(request)
    check_date = today or datetime.now(DISPLAY_TZ).date()
    return check_date > details.due_date


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _get_request(
    actor,
    request_id: int,
    *,
    require_participant: str,
    for_update: bool = False,
) -> CirculationRequest:
    """读取申请并校验高校与参与人（require_participant: owner/requester/any）。

    for_update=True 时以 SELECT ... FOR UPDATE 行锁读取（G4 并发加固）：
    状态检查在锁内进行，防止并发状态操作基于过期状态推进。
    锁顺序约定：申请行 → 物品行（confirm_handover 中交接记录行随申请行之后）。
    """
    stmt = select(CirculationRequest).where(CirculationRequest.id == request_id)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    request = db.session.scalars(stmt).first()
    if request is None or request.university_id != actor.university_id:
        raise NotFoundError("没有找到该流转申请。")
    if require_participant == "owner" and request.owner_user_id != actor.id:
        raise PermissionDeniedError("只有物品所有者可以执行该操作。")
    if require_participant == "requester" and request.requester_user_id != actor.id:
        raise PermissionDeniedError("只有申请人可以执行该操作。")
    return request


def _lock_item_row(item_id: int) -> Item:
    """按主键行锁读取物品（G4 并发加固；锁序约定：申请行 → 物品行）。"""
    return db.session.scalars(
        select(Item).where(Item.id == item_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()


def _lock_item(item_id: int, *, mode: str, owner_must_differ_from: int | None) -> Item:
    """申请创建前锁定物品行并重检（G4 并发加固，BR-012）。

    两个并发申请在同一物品行上排队：后到者在锁内重读 status，
    若物品已被占用则得到 ConflictError，而不是 IntegrityError 500。
    锁顺序：物品行先于申请行 INSERT，与状态操作的 申请行→物品行 不构成交叉死锁
    （申请创建时申请行尚不存在，状态操作先锁已存在的申请行）。
    """
    item = db.session.scalars(
        select(Item).where(Item.id == item_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if item.university_id is None or item.mode != mode:
        raise PermissionDeniedError("该物品不是对应的流转方式。")
    if owner_must_differ_from is not None and item.owner_user_id == owner_must_differ_from:
        raise PermissionDeniedError("不能申请自己的物品。")
    if item.status != ITEM_ACTIVE:
        raise ConflictError("该物品已被其他人申请，暂时不能接受新的申请（BR-012）。")
    return item


def _borrow_details(request: CirculationRequest) -> BorrowDetails:
    details = db.session.get(BorrowDetails, request.id)
    if details is None:
        raise NotFoundError("借用明细不存在。")
    return details


def _ensure_no_date_conflict(request: CirculationRequest, start: date, due: date) -> None:
    """BR-022：相同物品已批准借期不得重叠。"""
    conditions = (
        CirculationRequest.item_id == request.item_id,
        CirculationRequest.mode == "borrow",
        CirculationRequest.id != request.id,
        CirculationRequest.status.in_(_OCCUPYING_STATUSES),
    )
    existing = db.session.scalars(select(CirculationRequest).where(*conditions)).all()
    for other in existing:
        other_details = db.session.get(BorrowDetails, other.id)
        if other_details is None:
            continue
        if start <= other_details.due_date and other_details.start_date <= due:
            raise ConflictError(
                f"该物品在 {other_details.start_date} 至 {other_details.due_date} 已有借用安排，"
                "所选借期与之重叠（BR-022）。请调整借期。"
            )


def _set_item_status(item: Item, to_status: str, *, actor_user_id: int, reason: str) -> None:
    """物品状态变更（校验 + 历史），不单独 commit。"""
    from app.core.states import validate_item_transition

    from_status = item.status
    validate_item_transition(from_status, to_status)
    item.status = to_status
    item.updated_at = datetime.now(UTC)
    _write_item_history(
        item,
        from_status=from_status,
        to_status=to_status,
        actor_user_id=actor_user_id,
        reason=reason,
    )


def _write_item_history(
    item: Item, *, from_status: str | None, to_status: str, actor_user_id: int, reason: str
) -> None:
    db.session.add(
        StatusHistory(
            university_id=item.university_id,
            entity_type="item",
            entity_id=item.id,
            from_status=from_status if from_status is not None else item.status,
            to_status=to_status,
            actor_user_id=actor_user_id,
            reason=reason,
            created_at=datetime.now(UTC),
        )
    )


def _write_request_history(
    request: CirculationRequest,
    *,
    from_status: str | None,
    to_status: str,
    actor_user_id: int,
    reason: str,
) -> None:
    db.session.add(
        StatusHistory(
            university_id=request.university_id,
            entity_type="circulation_request",
            entity_id=request.id,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_user_id,
            reason=reason,
            created_at=datetime.now(UTC),
        )
    )


def request_history(request: CirculationRequest) -> list[StatusHistory]:
    stmt = (
        select(StatusHistory)
        .where(
            StatusHistory.entity_type == "circulation_request",
            StatusHistory.entity_id == request.id,
            StatusHistory.university_id == request.university_id,
        )
        .order_by(StatusHistory.created_at.desc())
    )
    return list(db.session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# 出售 / 赠送 / 回收（G3）
# ---------------------------------------------------------------------------


def request_purchase(actor, item_id: int, *, request_note: str | None = None) -> CirculationRequest:
    """提交购买申请（FR-S01）：买家显示标价，等待卖家确认。"""
    if not actor.is_student:
        raise PermissionDeniedError("只有在校学生可以申请购买。")
    item = _item_for_request(actor, item_id, mode="sale")
    now = datetime.now(UTC)
    request = CirculationRequest(
        university_id=actor.university_id,
        item_id=item.id,
        requester_user_id=actor.id,
        owner_user_id=item.owner_user_id,
        mode="sale",
        status=REQ_PENDING,
        request_note=(request_note or "").strip() or None,
        created_at=now,
        updated_at=now,
    )
    db.session.add(request)
    db.session.flush()
    db.session.add(SaleDetails(request_id=request.id, agreed_price_cents=item.sale_price_cents))
    db.session.flush()
    _write_request_history(
        request,
        from_status=None,
        to_status=REQ_PENDING,
        actor_user_id=actor.id,
        reason="提交购买申请",
    )
    _set_item_status(item, ITEM_RESERVED, actor_user_id=actor.id, reason="存在待处理的购买申请")
    notify_users(
        university_id=actor.university_id,
        recipient_ids={item.owner_user_id},
        category="request",
        title="收到新的购买申请",
        body=(
            f"你的物品「{item.title}」收到新的购买申请"
            f"（标价 ¥{item.sale_price_cents / 100:.2f}，教学模拟）。"
        ),
        related_entity_type="circulation_request",
        related_entity_id=request.id,
    )
    db.session.commit()
    return request


def request_giveaway(actor, item_id: int, *, request_note: str | None = None) -> CirculationRequest:
    """提交领取申请（FR-G01）：同一时间只保留一个有效申请。"""
    if not actor.is_student:
        raise PermissionDeniedError("只有在校学生可以申请领取。")
    item = _item_for_request(actor, item_id, mode="give")
    now = datetime.now(UTC)
    request = CirculationRequest(
        university_id=actor.university_id,
        item_id=item.id,
        requester_user_id=actor.id,
        owner_user_id=item.owner_user_id,
        mode="give",
        status=REQ_PENDING,
        request_note=(request_note or "").strip() or None,
        created_at=now,
        updated_at=now,
    )
    db.session.add(request)
    db.session.flush()
    _write_request_history(
        request,
        from_status=None,
        to_status=REQ_PENDING,
        actor_user_id=actor.id,
        reason="提交领取申请",
    )
    _set_item_status(item, ITEM_RESERVED, actor_user_id=actor.id, reason="存在待处理的领取申请")
    notify_users(
        university_id=actor.university_id,
        recipient_ids={item.owner_user_id},
        category="request",
        title="收到新的领取申请",
        body=f"你赠送的物品「{item.title}」收到新的领取申请。",
        related_entity_type="circulation_request",
        related_entity_id=request.id,
    )
    db.session.commit()
    return request


def request_recycle(
    actor,
    item_id: int,
    *,
    station_id: int,
    preferred_start_at: datetime,
    preferred_end_at: datetime,
    request_note: str | None = None,
) -> CirculationRequest:
    """提交回收申请（FR-R01）：选择本校站点与期望送达时段（BR-029）。

    回收是用户对自己物品发起的申请（BR-011/BR-029）：
    - requester_user_id = 物品所有者；
    - owner_user_id = 申请时该站点的在职公益管理员（数据库约束要求双方不同用户）；
    - 站点必须属于本校且处于启用状态，且必须有在职公益管理员接单。
    """
    if not actor.is_student:
        raise PermissionDeniedError("只有在校学生可以提交回收申请。")
    if preferred_end_at <= preferred_start_at:
        raise InputError("送达时段结束时间必须晚于开始时间。")

    from app.models.university import Station, StationManagerAssignment

    item = db.session.get(Item, item_id)
    if item is None or item.university_id != actor.university_id:
        raise NotFoundError("没有找到该物品。")
    if item.owner_user_id != actor.id:
        raise PermissionDeniedError("只能提交自己物品的回收申请。")
    # G4 加固：申请前锁定物品行并重检（BR-012 活动申请互斥）
    item = _lock_item(item.id, mode="recycle", owner_must_differ_from=None)

    station = db.session.get(Station, station_id)
    if (
        station is None
        or station.university_id != actor.university_id
        or station.status != "active"
        # BR-029：回收物资只能进入回收站点（recycle/mixed），不能进纯公益站点
        or station.station_type not in ("recycle", "mixed")
    ):
        raise InputError(
            "所选回收站点不存在、不在本校或不是回收站点。",
            field_errors={"station_id": "站点无效。"},
        )

    manager = db.session.scalars(
        select(User)
        .join(StationManagerAssignment, StationManagerAssignment.user_id == User.id)
        .where(
            StationManagerAssignment.station_id == station_id,
            StationManagerAssignment.status == "active",
            User.status == "active",
        )
    ).first()
    if manager is None:
        raise ConflictError("该站点当前没有在职公益管理员，暂时不能接单。")

    now = datetime.now(UTC)
    request = CirculationRequest(
        university_id=actor.university_id,
        item_id=item.id,
        requester_user_id=actor.id,
        owner_user_id=manager.id,
        mode="recycle",
        status=REQ_PENDING,
        request_note=(request_note or "").strip() or None,
        created_at=now,
        updated_at=now,
    )
    db.session.add(request)
    db.session.flush()
    db.session.add(
        RecycleDetails(
            request_id=request.id,
            station_id=station_id,
            preferred_start_at=preferred_start_at,
            preferred_end_at=preferred_end_at,
        )
    )
    db.session.flush()
    _write_request_history(
        request,
        from_status=None,
        to_status=REQ_PENDING,
        actor_user_id=actor.id,
        reason="提交回收申请",
    )
    _set_item_status(item, ITEM_RESERVED, actor_user_id=actor.id, reason="存在待处理的回收申请")
    notify_users(
        university_id=actor.university_id,
        recipient_ids={manager.id},
        category="request",
        title="站点收到新的回收申请",
        body=f"站点「{station.name}」收到新的回收申请（{request.item.title}）。",
        related_entity_type="circulation_request",
        related_entity_id=request.id,
    )
    db.session.commit()
    return request


def simulate_payment(actor, request_id: int, *, outcome: str) -> CirculationRequest:
    """模拟支付（FR-S02）：成功 / 失败 / 取消；教学模拟不产生真实扣款（BR-025/BR-026）。

    - success：进入待交接，物品保持被申请；
    - fail / cancel：申请取消，物品恢复可申请（解除占用）。
    """
    if outcome not in ("success", "fail", "cancel"):
        raise InputError("无效的支付结果。")
    request = _get_request(actor, request_id, require_participant="requester", for_update=True)
    if request.mode != "sale":
        raise ConflictError("只有出售申请存在模拟支付。")
    if request.status != "payment_pending":
        raise ConflictError("申请当前不是待模拟支付状态。")

    details = db.session.get(SaleDetails, request.id)
    now = datetime.now(UTC)
    if outcome == "success":
        details.payment_status = "paid"
        details.paid_at = now
        details.payment_reference = f"SIM-{uuid.uuid4().hex[:10].upper()}"
        validate_request_transition(request.status, "handover_pending")
        request.status = "handover_pending"
        request.updated_at = now
        _write_request_history(
            request,
            from_status="payment_pending",
            to_status="handover_pending",
            actor_user_id=actor.id,
            reason="模拟支付成功（教学模拟，不产生真实扣款）",
        )
        notify_users(
            university_id=request.university_id,
            recipient_ids={request.owner_user_id},
            category="payment",
            title="买家已完成模拟支付",
            body=f"「{request.item.title}」的买家已完成模拟支付，请生成交接码完成交易。",
            related_entity_type="circulation_request",
            related_entity_id=request.id,
        )
    else:
        reason = "模拟支付失败" if outcome == "fail" else "买家取消支付"
        details.payment_status = "failed" if outcome == "fail" else "cancelled"
        validate_request_transition(request.status, REQ_CANCELLED)
        request.status = REQ_CANCELLED
        request.updated_at = now
        _write_request_history(
            request,
            from_status="payment_pending",
            to_status=REQ_CANCELLED,
            actor_user_id=actor.id,
            reason=reason,
        )
        _set_item_status(
            _lock_item_row(request.item_id),
            ITEM_ACTIVE,
            actor_user_id=actor.id,
            reason="模拟支付未完成，物品恢复可申请（BR-026）",
        )
        notify_users(
            university_id=request.university_id,
            recipient_ids={request.owner_user_id},
            category="payment",
            title="模拟支付未完成",
            body=f"「{request.item.title}」的{reason}，物品已恢复可申请。",
            related_entity_type="circulation_request",
            related_entity_id=request.id,
        )
    db.session.commit()
    return request


def inspect_recycle(
    actor, request_id: int, *, passed: bool, note: str | None = None
) -> CirculationRequest:
    """站点验收回收物品（FR-R03、BR-031）。

    - 通过：申请完成、物品完成（计入环保贡献，按完成申请聚合）；
    - 不符合：记录原因，申请 rejected，物品 off_shelf（D-036：所有者可重新上架）。
    """
    request = _get_request(actor, request_id, require_participant="owner", for_update=True)
    if request.mode != "recycle":
        raise ConflictError("只有回收申请可以进行站点验收。")
    if request.status != "inspection_pending":
        raise ConflictError("申请当前不是待回收验收状态。")
    _ensure_station_authorization(actor, request)

    details = db.session.get(RecycleDetails, request.id)
    now = datetime.now(UTC)
    # 先完整写入明细字段（CHECK 约束要求 status 与检查人同时落库），
    # 再访问关联对象，避免 autoflush 把中间态刷进数据库
    if passed:
        details.inspection_status = "accepted"
        details.inspection_note = (note or "").strip() or None
        details.inspected_by_user_id = actor.id
        details.inspected_at = now
    else:
        if not (note or "").strip():
            raise InputError(
                "验收不通过必须记录原因（BR-031）。",
                field_errors={"note": "请填写验收不通过原因。"},
            )
        details.inspection_status = "rejected"
        details.inspection_note = note.strip()
        details.inspected_by_user_id = actor.id
        details.inspected_at = now

    item = _lock_item_row(request.item_id)
    if passed:
        validate_request_transition(request.status, REQ_COMPLETED)
        request.status = REQ_COMPLETED
        request.completed_at = now
        request.updated_at = now
        _write_request_history(
            request,
            from_status="inspection_pending",
            to_status=REQ_COMPLETED,
            actor_user_id=actor.id,
            reason="站点验收通过，回收完成",
        )
        _set_item_status(item, "completed", actor_user_id=actor.id, reason="回收验收通过")
        notify_users(
            university_id=request.university_id,
            recipient_ids={request.requester_user_id},
            category="recycle",
            title="回收验收通过",
            body=f"「{request.item.title}」已通过站点验收，计入你的校园环保贡献。",
            related_entity_type="circulation_request",
            related_entity_id=request.id,
        )
    else:
        validate_request_transition(request.status, REQ_REJECTED)
        request.status = REQ_REJECTED
        request.updated_at = now
        _write_request_history(
            request,
            from_status="inspection_pending",
            to_status=REQ_REJECTED,
            actor_user_id=actor.id,
            reason=f"验收不符合：{note.strip()}",
        )
        _set_item_status(
            item,
            "off_shelf",
            actor_user_id=actor.id,
            reason="回收验收不符合，物品由所有者决定重新上架（D-036）",
        )
        notify_users(
            university_id=request.university_id,
            recipient_ids={request.requester_user_id},
            category="recycle",
            title="回收验收未通过",
            body=f"「{request.item.title}」未通过站点验收：{note.strip()}。物品已下架，你可以修改后重新上架。",
            related_entity_type="circulation_request",
            related_entity_id=request.id,
        )
    db.session.commit()
    return request


def count_completed_recycles(user_id: int) -> int:
    """校园环保贡献：按已完成回收申请聚合（6.2 第 9 节，不保存冗余计数）。"""
    stmt = (
        select(func.count())
        .select_from(CirculationRequest)
        .where(
            CirculationRequest.requester_user_id == user_id,
            CirculationRequest.mode == "recycle",
            CirculationRequest.status == REQ_COMPLETED,
        )
    )
    return db.session.scalar(stmt) or 0


def _item_for_request(actor, item_id: int, *, mode: str) -> Item:
    """购买/领取申请的公共校验：本校可见 + 模式一致 + 非本人 + 可申请。

    G4 加固：锁定物品行并重检，并发申请只有一个能成功（BR-012）。
    """
    item = get_visible_item(actor, item_id)
    return _lock_item(item.id, mode=mode, owner_must_differ_from=actor.id)


def station_recycle_queue(actor) -> list[CirculationRequest]:
    """站点工作台：授权站点待处理的回收申请与待验收物品（FR-M03）。"""
    stmt = (
        select(CirculationRequest)
        .where(
            CirculationRequest.owner_user_id == actor.id,
            CirculationRequest.mode == "recycle",
            CirculationRequest.status.in_(("pending", "inspection_pending")),
        )
        .order_by(CirculationRequest.created_at)
    )
    return list(db.session.scalars(stmt).all())


def _ensure_station_authorization(actor, request: CirculationRequest) -> None:
    """FR-M03：公益管理员（回收）只能处理授权站点的申请。"""
    from app.models.university import StationManagerAssignment

    details = db.session.get(RecycleDetails, request.id)
    assignment = db.session.scalar(
        select(StationManagerAssignment).where(
            StationManagerAssignment.station_id == details.station_id,
            StationManagerAssignment.user_id == actor.id,
            StationManagerAssignment.status == "active",
        )
    )
    if assignment is None:
        raise PermissionDeniedError("只能处理被授权站点的回收申请。")
