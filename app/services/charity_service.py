"""公益首版 Service（G3：FR-C01 ~ FR-C07、BR-033 ~ BR-040）。

公开接口（交接书第 7 节）：
- create_project() / update_project_need()   项目与物资目标
- submit_donation()                          学生提交本校实物捐赠
- review_donation()                          公益管理员（回收）核验（行锁防超募）
- publish_receipt()                          创建并公示脱敏回执

辅助接口：list_projects / get_project / project_progress / station_donation_queue /
list_published_receipts / get_receipt。

核心规则：
- 公益项目属于一个高校；用户只能捐赠本校项目（BR-034）；
- 只有核验接收后数量才计入进度（BR-035）；确认数量不得超目标（BR-036），
  核验时锁定需求行避免并发超募；
- 达到目标或截止时间后停止接受新捐赠（BR-037）；
- 回执可追溯到已接收捐赠明细；公开回执不得包含可识别个人信息（BR-038/BR-039）；
- 不接收真实资金，不展示募捐账户（BR-040）。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app import db
from app.core.errors import ConflictError, InputError, NotFoundError, PermissionDeniedError
from app.core.states import CHARITY_PROJECT_COMPLETED
from app.models.charity import (
    CharityDonation,
    CharityDonationItem,
    CharityProject,
    CharityProjectNeed,
    CharityReceipt,
    CharityReceiptItem,
)
from app.models.item import ItemCategory
from app.models.university import Station, StationManagerAssignment
from app.services.notification_service import notify_users, record_audit
from app.services.org_service import manager_scope

VALID_DONATION_CONDITIONS = ("new", "like_new", "good", "fair")


# ---------------------------------------------------------------------------
# 项目与需求
# ---------------------------------------------------------------------------


def create_project(
    actor,
    *,
    title: str,
    description: str,
    recipient_org: str,
    public_summary: str,
    deadline: datetime,
    needs: list[dict] | None = None,
    university_id: int | None = None,
) -> CharityProject:
    """创建公益项目（FR-C01）。

    公益管理员（回收）：项目属于本人所在高校，需持有站点授权；
    平台管理员：可支持创建（university_id 指定归属高校）。
    """
    _ensure_project_creator(actor)
    if university_id is None:
        university_id = actor.university_id
    if actor.role == "station_manager" and university_id != actor.university_id:
        raise PermissionDeniedError("只能创建本校公益项目。")
    if not manager_scope(actor) and actor.role == "station_manager":
        raise PermissionDeniedError("公益管理员需先持有站点授权才能创建公益项目。")

    title = (title or "").strip()
    if not title:
        raise InputError("请填写项目名称。", field_errors={"title": "项目名称不能为空。"})
    if deadline <= datetime.now(UTC):
        raise InputError("截止时间必须晚于当前时间。", field_errors={"deadline": "截止时间无效。"})
    # G4 加固（D-039）：项目页对本校学生公开，公开字段检测 PII（默认拒绝提交）
    from app.core.privacy import ensure_public_text_safe

    ensure_public_text_safe(title, "title")
    ensure_public_text_safe((description or "").strip(), "description")
    ensure_public_text_safe((recipient_org or "").strip(), "recipient_org")
    ensure_public_text_safe((public_summary or "").strip(), "public_summary")

    now = datetime.now(UTC)
    project = CharityProject(
        university_id=university_id,
        title=title,
        description=(description or "").strip() or "暂无描述",
        recipient_org=(recipient_org or "").strip() or "待定接收组织",
        public_summary=(public_summary or "").strip() or "暂无公开说明",
        deadline=deadline,
        status="active",
        created_by_user_id=actor.id,
        created_at=now,
        updated_at=now,
    )
    db.session.add(project)
    db.session.flush()

    for need_spec in needs or []:
        _add_need(project, **need_spec)
    db.session.commit()
    return project


def update_project_need(actor, project_id: int, **need_spec) -> CharityProjectNeed:
    """维护物资需求（FR-C01）：向募集中项目追加需求项。"""
    project = _get_managed_project(actor, project_id)
    need = _add_need(project, **need_spec)
    db.session.commit()
    return need


def _add_need(
    project: CharityProject,
    *,
    item_category_id: int,
    item_name: str,
    target_quantity: int,
    unit: str = "件",
) -> CharityProjectNeed:
    item_name = (item_name or "").strip()
    if not item_name:
        raise InputError("物资名称不能为空。", field_errors={"item_name": "物资名称不能为空。"})
    # G4 加固（D-039）：需求项名称随项目页公开，检测 PII
    from app.core.privacy import ensure_public_text_safe

    ensure_public_text_safe(item_name, "item_name")
    if target_quantity is None or target_quantity <= 0:
        raise InputError("目标数量必须大于 0。", field_errors={"target_quantity": "目标数量无效。"})
    category = db.session.get(ItemCategory, item_category_id)
    if category is None or not category.is_active:
        raise InputError("物资分类无效。", field_errors={"item_category_id": "分类无效。"})
    existing = db.session.scalar(
        select(CharityProjectNeed).where(
            CharityProjectNeed.project_id == project.id,
            CharityProjectNeed.item_category_id == item_category_id,
            CharityProjectNeed.item_name == item_name,
        )
    )
    if existing is not None:
        raise ConflictError("该项目已存在同分类同名物资需求。")
    need = CharityProjectNeed(
        project_id=project.id,
        item_category_id=item_category_id,
        item_name=item_name,
        target_quantity=target_quantity,
        accepted_quantity=0,
        unit=(unit or "件").strip() or "件",
        status="active",
        created_at=datetime.now(UTC),
    )
    db.session.add(need)
    db.session.flush()
    return need


def list_projects(actor) -> list[CharityProject]:
    """本校公益项目列表（FR-C01 展示）。"""
    stmt = (
        select(CharityProject)
        .where(
            CharityProject.university_id == actor.university_id,
            CharityProject.status.in_(("active", "completed")),
        )
        .order_by(CharityProject.deadline)
    )
    return list(db.session.scalars(stmt).all())


def get_project(actor, project_id: int) -> CharityProject:
    """本校项目详情；跨校 404（BR-034）。"""
    project = db.session.get(CharityProject, project_id)
    if project is None or project.university_id != actor.university_id:
        raise NotFoundError("没有找到该公益项目。")
    return project


def project_progress(project: CharityProject) -> list[CharityProjectNeed]:
    """目标与募集进度（FR-C04）：accepted_quantity 由核验写入。"""
    return sorted(project.needs, key=lambda n: n.id)


# ---------------------------------------------------------------------------
# 捐赠与核验
# ---------------------------------------------------------------------------


def submit_donation(
    actor, project_id: int, *, station_id: int, items: list[dict], donor_note: str | None = None
) -> CharityDonation:
    """提交实物捐赠（FR-C02、BR-034）。

    items: [{need_id, quantity, condition, note}]；图片随 R2 增量接入。
    """
    if not actor.is_student:
        raise PermissionDeniedError("只有在校学生可以提交实物捐赠。")
    project = get_project(actor, project_id)
    if project.status != "active":
        raise ConflictError("项目不在募集状态，不接受新捐赠（BR-037）。")
    if project.deadline <= datetime.now(UTC):
        raise ConflictError("项目已过截止时间，不接受新捐赠（BR-037）。")

    station = db.session.get(Station, station_id)
    if (
        station is None
        or station.university_id != actor.university_id
        or station.status != "active"
        # FR-C02：捐赠物资只能送入公益站点（charity/mixed），不能进纯回收站点
        or station.station_type not in ("charity", "mixed")
    ):
        raise InputError(
            "所选接收站点无效或不是公益站点。", field_errors={"station_id": "站点无效。"}
        )

    if not items:
        raise InputError("请至少填写一种捐赠物资。")

    now = datetime.now(UTC)
    donation = CharityDonation(
        university_id=actor.university_id,
        project_id=project.id,
        donor_user_id=actor.id,
        station_id=station_id,
        status="pending",
        donor_note=(donor_note or "").strip() or None,
        submitted_at=now,
        created_at=now,
        updated_at=now,
    )
    db.session.add(donation)
    db.session.flush()

    for spec in items:
        need = db.session.get(CharityProjectNeed, spec.get("need_id") or 0)
        if need is None or need.project_id != project.id:
            raise InputError("捐赠物资必须属于该项目。")
        quantity = spec.get("quantity")
        if not isinstance(quantity, int) or quantity <= 0:
            raise InputError("捐赠数量必须为正整数。", field_errors={"quantity": "数量无效。"})
        condition = spec.get("condition")
        if condition not in VALID_DONATION_CONDITIONS:
            raise InputError("物资成色无效。")
        image_key = spec.get("image_object_key")
        if image_key is not None and (not isinstance(image_key, str) or not image_key.strip()):
            image_key = None
        db.session.add(
            CharityDonationItem(
                donation_id=donation.id,
                project_id=project.id,
                project_need_id=need.id,
                item_name=need.item_name,
                quantity=quantity,
                accepted_quantity=0,
                condition=condition,
                note=(spec.get("note") or "").strip() or None,
                image_object_key=image_key,
                created_at=now,
            )
        )

    notify_users(
        university_id=project.university_id,
        recipient_ids=_station_managers(station_id),
        category="charity",
        title="站点收到新的实物捐赠",
        body=f"公益项目「{project.title}」收到新的实物捐赠，请到站点工作台核验。",
        related_entity_type="charity_donation",
        related_entity_id=donation.id,
    )
    db.session.commit()
    return donation


def review_donation(
    actor,
    donation_id: int,
    *,
    accept: bool,
    accepted_quantities: dict[int, int] | None = None,
    reject_reason: str | None = None,
) -> CharityDonation:
    """站点核验捐赠（FR-C03、BR-035/BR-036）。

    - 先行授权校验（不依赖行状态）；
    - 再锁定捐赠行并重读状态，防止并发核验重复累加；
    - 接收：锁定需求行，确认不超募后累加 accepted_quantity；
    - 拒绝：记录原因，不计入进度。
    """
    _get_managed_donation_actor_check(actor, donation_id)
    # 锁定捐赠行并重读：并发核验只有一个事务能通过状态检查
    donation = db.session.scalars(
        select(CharityDonation)
        .where(CharityDonation.id == donation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if donation is None or donation.university_id != actor.university_id:
        raise NotFoundError("没有找到该捐赠记录。")
    if donation.status != "pending":
        raise ConflictError("该捐赠已核验完毕，不能重复处理。")

    now = datetime.now(UTC)
    if accept:
        for item in donation.items:
            accepted = (accepted_quantities or {}).get(item.id, item.quantity)
            # G4 加固：恶意/越界数值直接拒绝，不进入累加
            if accepted < 0:
                raise InputError(f"物资「{item.item_name}」的确认数量不能为负数。")
            if accepted > item.quantity:
                raise InputError(f"物资「{item.item_name}」的确认数量不能超过捐赠数量。")
        # G4 加固：按 project_need_id 升序一次性锁定本次涉及的需求行（统一锁序防死锁），
        # 锁内以最新值判断超募（6.2 数据库设计 4.5）
        need_ids = sorted({item.project_need_id for item in donation.items})
        locked_needs: dict[int, CharityProjectNeed] = {
            need.id: need
            for need in db.session.scalars(
                select(CharityProjectNeed)
                .where(CharityProjectNeed.id.in_(need_ids))
                .order_by(CharityProjectNeed.id)
                .with_for_update().execution_options(populate_existing=True)
            ).all()
        }
        for item in donation.items:
            need = locked_needs[item.project_need_id]
            accepted = (accepted_quantities or {}).get(item.id, item.quantity)
            remaining = need.target_quantity - need.accepted_quantity
            if accepted > remaining:
                raise InputError(
                    f"物资「{item.item_name}」确认数量超出剩余目标 {remaining}，"
                    "请调整确认数量（BR-036，不得超募）。"
                )
            item.accepted_quantity = accepted
            need.accepted_quantity += accepted

        donation.status = "received"
        donation.reviewed_by_user_id = actor.id
        donation.reviewed_at = now
        donation.updated_at = now

        # 全部需求满足后项目进入已完成（BR-037）
        project = db.session.get(CharityProject, donation.project_id)
        if all(n.accepted_quantity >= n.target_quantity for n in project.needs):
            project.status = CHARITY_PROJECT_COMPLETED
            project.updated_at = now
            _write_project_history(
                project,
                from_status="active",
                to_status=CHARITY_PROJECT_COMPLETED,
                actor_user_id=actor.id,
                reason="全部物资目标已满足",
            )

        notify_users(
            university_id=donation.university_id,
            recipient_ids={donation.donor_user_id},
            category="charity",
            title="捐赠已核验接收",
            body=f"你在公益项目「{project.title}」提交的捐赠已核验接收，感谢你的善意。",
            related_entity_type="charity_donation",
            related_entity_id=donation.id,
        )
    else:
        if not (reject_reason or "").strip():
            raise InputError(
                "拒绝捐赠必须记录原因。", field_errors={"reject_reason": "请填写拒绝原因。"}
            )
        donation.status = "rejected"
        donation.reject_reason = reject_reason.strip()
        donation.reviewed_by_user_id = actor.id
        donation.reviewed_at = now
        donation.updated_at = now
        notify_users(
            university_id=donation.university_id,
            recipient_ids={donation.donor_user_id},
            category="charity",
            title="捐赠未通过核验",
            body=f"你提交的捐赠未通过核验：{reject_reason.strip()}。",
            related_entity_type="charity_donation",
            related_entity_id=donation.id,
        )

    record_audit(
        actor_user_id=actor.id,
        university_id=donation.university_id,
        action="charity.donation.review",
        entity_type="charity_donation",
        entity_id=donation.id,
        detail={"accept": accept},
    )
    db.session.commit()
    return donation


def station_donation_queue(actor) -> list[CharityDonation]:
    """站点工作台：授权站点待核验捐赠（FR-M03）。"""
    station_ids = [s.id for s in manager_scope(actor)]
    if not station_ids:
        return []
    stmt = (
        select(CharityDonation)
        .where(
            CharityDonation.station_id.in_(station_ids),
            CharityDonation.status == "pending",
        )
        .order_by(CharityDonation.submitted_at)
    )
    return list(db.session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# 回执
# ---------------------------------------------------------------------------


def publish_receipt(
    actor,
    project_id: int,
    *,
    station_id: int,
    title: str,
    recipient_org: str,
    received_at: datetime,
    public_note: str,
    items: list[dict],
    dispatched_at: datetime | None = None,
) -> CharityReceipt:
    """创建并公示脱敏回执（FR-C06、FR-C07、BR-038/BR-039）。

    - station_id 必须在操作者的授权站点范围内（FR-M03）；
    - items: [{donation_item_id, item_name, quantity, note}]；donation_item_id
      必须属于本项目且**累计登记数量不超过已接收数量**（同一明细跨回执累计）；
    - 回执内容不包含受助对象可识别个人信息（脱敏由字段设计保证），
      公开文本（标题/接收组织/说明/明细名称与备注）由 privacy 规则检测 PII（D-039）。

    G4 加固：按 donation_item_id 升序一次性锁定涉及的捐赠明细行，
    两个并发回执发布串行化，累计数量不会超过 accepted_quantity。
    """
    from app.core.privacy import ensure_public_text_safe

    project = _get_managed_project(actor, project_id, allow_completed=True)
    authorized_ids = {s.id for s in manager_scope(actor)}
    if actor.is_platform_admin and not authorized_ids:
        authorized_ids = {s.id for s in _project_stations(project)}
    if station_id not in authorized_ids:
        raise PermissionDeniedError("只能为授权站点登记回执（FR-M03）。")

    title = (title or "").strip()
    public_note = (public_note or "").strip()
    if not title:
        raise InputError("请填写回执标题。", field_errors={"title": "回执标题不能为空。"})
    if not public_note:
        raise InputError("请填写回执说明。", field_errors={"public_note": "回执说明不能为空。"})
    if not items:
        raise InputError("回执至少登记一种物资。")
    # G4 加固（D-039）：回执对本校学生公开，公开文本检测 PII
    ensure_public_text_safe(title, "title")
    ensure_public_text_safe((recipient_org or "").strip(), "recipient_org")
    ensure_public_text_safe(public_note, "public_note")

    now = datetime.now(UTC)
    receipt = CharityReceipt(
        university_id=project.university_id,
        project_id=project.id,
        station_id=station_id,
        title=title,
        recipient_org=(recipient_org or "").strip() or project.recipient_org,
        received_at=received_at,
        dispatched_at=dispatched_at,
        public_note=public_note,
        status="published",
        created_by_user_id=actor.id,
        published_at=now,
        created_at=now,
    )
    db.session.add(receipt)
    db.session.flush()

    # G4 加固：按 donation_item_id 升序一次性锁定涉及的捐赠明细行（统一锁序防死锁）
    lock_ids = sorted({spec.get("donation_item_id") or 0 for spec in items})
    locked_items: dict[int, CharityDonationItem] = {
        donation_item.id: donation_item
        for donation_item in db.session.scalars(
            select(CharityDonationItem)
            .where(CharityDonationItem.id.in_(lock_ids))
            .order_by(CharityDonationItem.id)
            .with_for_update().execution_options(populate_existing=True)
        ).all()
    }
    for spec in items:
        donation_item = locked_items.get(spec.get("donation_item_id") or 0)
        if donation_item is None or donation_item.project_id != project.id:
            raise InputError("回执物资必须可追溯到本项目的已接收捐赠明细。")
        if donation_item.accepted_quantity <= 0:
            raise ConflictError(
                f"物资「{donation_item.item_name}」尚未核验接收，不能登记回执（BR-038）。"
            )

    from sqlalchemy import func

    prior_totals: dict[int, int] = {}
    donation_item_ids = list(locked_items)
    if donation_item_ids:
        rows = db.session.execute(
            select(
                CharityReceiptItem.donation_item_id,
                func.coalesce(func.sum(CharityReceiptItem.quantity), 0),
            )
            .where(CharityReceiptItem.donation_item_id.in_(donation_item_ids))
            .group_by(CharityReceiptItem.donation_item_id)
        ).all()
        prior_totals = {row[0]: int(row[1]) for row in rows}

    registered_totals: dict[int, int] = {}
    for spec in items:
        donation_item = locked_items[spec["donation_item_id"]]
        quantity = spec.get("quantity", donation_item.accepted_quantity)
        if not isinstance(quantity, int) or quantity <= 0:
            raise InputError("回执数量必须为正整数。")
        registered_totals[donation_item.id] = (
            registered_totals.get(donation_item.id, 0) + quantity
        )
        if (
            prior_totals.get(donation_item.id, 0) + registered_totals[donation_item.id]
            > donation_item.accepted_quantity
        ):
            raise ConflictError(
                f"物资「{donation_item.item_name}」回执累计数量不能大于已接收数量"
                f"（已登记 {prior_totals.get(donation_item.id, 0)}，"
                f"已接收 {donation_item.accepted_quantity}）（BR-038）。"
            )

    for spec in items:
        donation_item = locked_items[spec["donation_item_id"]]
        quantity = spec.get("quantity", donation_item.accepted_quantity)
        item_name = spec.get("item_name") or donation_item.item_name
        note = (spec.get("note") or "").strip() or None
        # G4 加固（D-039）：回执明细名称与备注随回执公开，检测 PII
        ensure_public_text_safe(item_name, "item_name")
        if note:
            ensure_public_text_safe(note, "note")
        db.session.add(
            CharityReceiptItem(
                receipt_id=receipt.id,
                donation_item_id=donation_item.id,
                item_name=item_name,
                quantity=quantity,
                note=note,
            )
        )
    record_audit(
        actor_user_id=actor.id,
        university_id=project.university_id,
        action="charity.receipt.publish",
        entity_type="charity_receipt",
        entity_id=receipt.id,
        detail={"project_id": project.id, "station_id": station_id},
    )
    db.session.commit()
    return receipt


def receipt_form_data(actor, project_id: int | None) -> dict:
    """回执表单数据（FR-C06）：可管理项目 + 授权站点范围内已接收捐赠明细。

    捐赠明细只返回操作者授权站点的数据（FR-M03），其他站点不可见。
    """
    authorized_ids = {s.id for s in manager_scope(actor)}
    projects = []
    if actor.is_platform_admin and not authorized_ids:
        projects = _platform_projects(actor)
    else:
        stmt = (
            select(CharityProject)
            .where(
                CharityProject.university_id == actor.university_id,
                CharityProject.status.in_(("active", "completed")),
            )
            .order_by(CharityProject.deadline)
        )
        projects = list(db.session.scalars(stmt).all())

    donation_items: list[CharityDonationItem] = []
    if project_id:
        project = _get_managed_project(actor, project_id, allow_completed=True)
        stmt = (
            select(CharityDonationItem)
            .join(CharityDonation, CharityDonationItem.donation_id == CharityDonation.id)
            .where(
                CharityDonationItem.project_id == project.id,
                CharityDonation.station_id.in_(authorized_ids) if authorized_ids else False,
                CharityDonation.status == "received",
                CharityDonationItem.accepted_quantity > 0,
            )
            .order_by(CharityDonationItem.id)
        )
        donation_items = list(db.session.scalars(stmt).all())
    return {"projects": projects, "donation_items": donation_items}


def _platform_projects(actor) -> list[CharityProject]:
    stmt = (
        select(CharityProject)
        .where(CharityProject.university_id == actor.university_id)
        .order_by(CharityProject.deadline)
    )
    return list(db.session.scalars(stmt).all())


def list_published_receipts(actor) -> list[CharityReceipt]:
    """本校已公示回执（FR-C07）。"""
    stmt = (
        select(CharityReceipt)
        .where(
            CharityReceipt.university_id == actor.university_id,
            CharityReceipt.status == "published",
        )
        .order_by(CharityReceipt.received_at.desc())
    )
    return list(db.session.scalars(stmt).all())


def get_published_receipt(actor, receipt_id: int) -> CharityReceipt:
    """本校已公示回执详情；未公示仅站点与管理员可见。"""
    receipt = db.session.get(CharityReceipt, receipt_id)
    if receipt is None or receipt.university_id != actor.university_id:
        raise NotFoundError("没有找到该回执。")
    if receipt.status != "published" and not actor.is_platform_admin:
        raise NotFoundError("没有找到该回执。")
    return receipt


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _ensure_project_creator(actor) -> None:
    if actor.role not in ("station_manager", "platform_admin"):
        raise PermissionDeniedError("只有公益管理员（回收）或平台管理员可以创建公益项目。")


def _get_managed_project(
    actor, project_id: int, *, allow_completed: bool = False
) -> CharityProject:
    """核验与回执操作的项目归属校验：本校 + 公益管理员/管理员。"""
    project = db.session.get(CharityProject, project_id)
    if project is None or project.university_id != actor.university_id:
        raise NotFoundError("没有找到该公益项目。")
    if actor.is_platform_admin:
        return project
    if actor.role != "station_manager":
        raise PermissionDeniedError("只有公益管理员（回收）可以执行该操作。")
    if not manager_scope(actor):
        raise PermissionDeniedError("公益管理员需持有站点授权。")
    if not allow_completed and project.status != "active":
        raise ConflictError("项目不在募集状态，不能调整需求。")
    return project


def _get_managed_donation_actor_check(actor, donation_id: int) -> None:
    """核验前的授权校验（站点范围），不读取捐赠行状态（避免锁前判断）。"""
    donation = db.session.get(CharityDonation, donation_id)
    if donation is None or donation.university_id != actor.university_id:
        raise NotFoundError("没有找到该捐赠记录。")
    if actor.is_platform_admin:
        return
    station_ids = [s.id for s in manager_scope(actor)]
    if donation.station_id not in station_ids:
        raise PermissionDeniedError("只能核验授权站点的捐赠（FR-M03）。")


def _station_managers(station_id: int) -> set[int]:
    stmt = select(StationManagerAssignment.user_id).where(
        StationManagerAssignment.station_id == station_id,
        StationManagerAssignment.status == "active",
    )
    return set(db.session.scalars(stmt).all())


def _project_stations(project: CharityProject) -> list[Station]:
    stmt = select(Station).where(
        Station.university_id == project.university_id,
        Station.status == "active",
        Station.station_type.in_(("charity", "mixed")),
    )
    return list(db.session.scalars(stmt).all())


def list_university_charity_stations(actor) -> list[Station]:
    """本校启用的公益站点（捐赠/回执表单下拉，FR-C02）。"""
    stmt = select(Station).where(
        Station.university_id == actor.university_id,
        Station.status == "active",
        Station.station_type.in_(("charity", "mixed")),
    )
    return list(db.session.scalars(stmt.order_by(Station.id)).all())


def _write_project_history(project, *, from_status, to_status, actor_user_id, reason) -> None:
    from app.models.governance import StatusHistory

    db.session.add(
        StatusHistory(
            university_id=project.university_id,
            entity_type="charity_project",
            entity_id=project.id,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_user_id,
            reason=reason,
            created_at=datetime.now(UTC),
        )
    )
