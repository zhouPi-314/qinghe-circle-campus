"""物品与媒体 Service。

公开接口（交接书第 7 节）：create_item()、search_items()、
get_visible_item()、update_item()、change_item_shelf_state()。

G2 范围说明：图片上传（R2）随 G3 增量接入 item_images；
本模块其余接口完整实现。

核心规则（SRS BR-011 ~ BR-015、FR-I01 ~ FR-I06）：
- 物品必须属于本校（高校隔离，service 层校验）；
- 一个物品只能有一种流转方式；
- 存在进行中业务时不能编辑关键字段、下架或切换流转方式；
- 管理员可强制下架并记录原因与审计；
- 状态变更写状态历史（同一事务）。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, or_, select

from app import db
from app.core.errors import ConflictError, InputError, NotFoundError, PermissionDeniedError
from app.core.permissions import ensure_actor_university, is_university_manager
from app.core.states import (
    ITEM_ACTIVE,
    ITEM_COMPLETED,
    ITEM_OFF_SHELF,
    ITEM_STATUS_LABELS,
    validate_item_transition,
)
from app.models.governance import StatusHistory
from app.models.item import Item, ItemCategory, ItemImage
from app.models.university import Campus

VALID_MODES = ("borrow", "sale", "give", "recycle")
VALID_CONDITIONS = ("new", "like_new", "good", "fair")

# 可浏览状态：下架物品不对他人展示
_VISIBLE_STATUSES = ("active", "reserved", "in_progress", "completed")

# 无活动业务时才允许编辑/下架/切换流转方式
_EDITABLE_ITEM_STATUSES = (ITEM_ACTIVE, ITEM_OFF_SHELF)


# ---------------------------------------------------------------------------
# 创建与查询
# ---------------------------------------------------------------------------


def create_item(
    actor,
    *,
    category_id: int,
    mode: str,
    title: str,
    description: str,
    condition: str,
    campus_id: int,
    sale_price_cents: int | None = None,
) -> Item:
    """在校学生发布物品（FR-I01）。

    - 只允许在校学生发布；
    - 校区必须属于本人所在高校；
    - 出售模式必须提供价格（分为单位）；其他模式价格必须为空；
    - 物品初始状态为可申请，并写状态历史。
    """
    _require_student(actor)

    field_errors: dict[str, str] = {}
    title = (title or "").strip()
    description = (description or "").strip()
    if not title:
        field_errors["title"] = "请输入物品名称。"
    if len(title) > 160:
        field_errors["title"] = "物品名称过长（最多 160 字）。"
    if not description:
        field_errors["description"] = "请填写物品描述。"
    # G4 加固（D-039）：公开字段自动检测 PII，命中即拒绝提交
    from app.core.privacy import public_text_error

    for _name, _value in (("title", title), ("description", description)):
        _pii = public_text_error(_value)
        if _pii:
            field_errors[_name] = _pii
    if mode not in VALID_MODES:
        field_errors["mode"] = "请选择有效的流转方式。"
    if condition not in VALID_CONDITIONS:
        field_errors["condition"] = "请选择物品成色。"
    if mode == "sale":
        if sale_price_cents is None or sale_price_cents <= 0:
            field_errors["sale_price"] = "出售物品必须填写大于 0 的价格。"
    elif sale_price_cents is not None:
        field_errors["sale_price"] = "非出售物品不能填写价格。"
    if field_errors:
        raise InputError("请检查发布表单。", field_errors=field_errors)

    category = db.session.get(ItemCategory, category_id)
    if category is None or not category.is_active:
        raise InputError("所选分类不存在或已停用。", field_errors={"category_id": "分类无效。"})

    campus = db.session.get(Campus, campus_id)
    if campus is None or campus.status != "active" or campus.university_id != actor.university_id:
        raise InputError("所选校区不属于你所在的学校。", field_errors={"campus_id": "校区无效。"})

    now = datetime.now(UTC)
    item = Item(
        university_id=actor.university_id,
        campus_id=campus_id,
        owner_user_id=actor.id,
        category_id=category_id,
        mode=mode,
        title=title,
        description=description,
        condition=condition,
        sale_price_cents=sale_price_cents,
        status=ITEM_ACTIVE,
        created_at=now,
        updated_at=now,
    )
    db.session.add(item)
    db.session.flush()

    _write_item_history(
        university_id=actor.university_id,
        item_id=item.id,
        from_status=None,
        to_status=ITEM_ACTIVE,
        actor_user_id=actor.id,
        reason="发布物品",
    )
    db.session.commit()
    return item


def search_items(
    actor,
    *,
    keyword: str | None = None,
    category_id: int | None = None,
    mode: str | None = None,
    campus_id: int | None = None,
) -> list[Item]:
    """浏览与筛选本校物品（FR-I03、FR-I04）。

    - 只返回本校物品；跨学校数据不可见；
    - 下架与被隐藏物品不进入列表；
    - 组合条件：关键词（名称/描述）、分类、流转方式、校区。
    """
    stmt = select(Item).where(
        Item.university_id == actor.university_id,
        Item.moderation_status == "normal",
        Item.status.in_(_VISIBLE_STATUSES),
    )
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(Item.title.ilike(like), Item.description.ilike(like)))
    if category_id:
        stmt = stmt.where(Item.category_id == category_id)
    if mode:
        stmt = stmt.where(Item.mode == mode)
    if campus_id:
        stmt = stmt.where(Item.campus_id == campus_id)
    stmt = stmt.order_by(Item.created_at.desc()).limit(100)
    return list(db.session.scalars(stmt).all())


def get_visible_item(actor, item_id: int) -> Item:
    """读取本校可见物品详情（FR-I05）。

    跨校对象返回 404，不泄露对象存在与否（BR-002）；
    被隐藏物品仅所有者与管理员可见。
    """
    item = db.session.get(Item, item_id)
    if (
        item is None
        or item.university_id != actor.university_id
        or (
            item.moderation_status != "normal"
            and not (actor.is_platform_admin or item.owner_user_id == actor.id)
        )
    ):
        raise NotFoundError("没有找到该物品。")
    return item


def list_owner_items(actor) -> list[Item]:
    """我的物品列表（FR-I06 列表部分）。"""
    stmt = select(Item).where(Item.owner_user_id == actor.id).order_by(Item.created_at.desc())
    return list(db.session.scalars(stmt).all())


def list_categories() -> list[ItemCategory]:
    """启用的物品分类（供发布与筛选表单）。"""
    stmt = (
        select(ItemCategory)
        .where(ItemCategory.is_active.is_(True))
        .order_by(ItemCategory.display_order)
    )
    return list(db.session.scalars(stmt).all())


def list_university_campuses(actor) -> list[Campus]:
    """本校启用校区（发布与筛选下拉）。"""
    stmt = (
        select(Campus)
        .where(Campus.university_id == actor.university_id, Campus.status == "active")
        .order_by(Campus.is_primary.desc(), Campus.id)
    )
    return list(db.session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# 编辑与上下架
# ---------------------------------------------------------------------------


def update_item(actor, item_id: int, *, fields: dict) -> Item:
    """编辑物品（FR-I06）。

    - 仅所有者可编辑；
    - 存在进行中业务时拒绝（BR-013）；
    - 可修改：名称、描述、成色、分类、校区、流转方式、价格。
    """
    item = _get_owned_item(actor, item_id)
    _require_no_active_request(item)

    allowed = {
        "title",
        "description",
        "condition",
        "category_id",
        "campus_id",
        "mode",
        "sale_price_cents",
    }
    unknown = set(fields) - allowed
    if unknown:
        raise InputError("包含不可修改的字段。")

    field_errors: dict[str, str] = {}
    new_mode = fields.get("mode", item.mode)
    if new_mode not in VALID_MODES:
        field_errors["mode"] = "请选择有效的流转方式。"
    if "title" in fields:
        title = fields["title"].strip()
        if not title or len(title) > 160:
            field_errors["title"] = "物品名称不能为空且最多 160 字。"
    if "description" in fields and not fields["description"].strip():
        field_errors["description"] = "物品描述不能为空。"
    # G4 加固（D-039）：公开字段自动检测 PII，命中即拒绝提交
    from app.core.privacy import public_text_error

    for _name in ("title", "description"):
        if _name in fields:
            _pii = public_text_error(fields[_name])
            if _pii:
                field_errors[_name] = _pii
    if "condition" in fields and fields["condition"] not in VALID_CONDITIONS:
        field_errors["condition"] = "成色无效。"
    if new_mode == "sale":
        price = fields.get("sale_price_cents", item.sale_price_cents)
        if price is None or price <= 0:
            field_errors["sale_price"] = "出售物品必须填写大于 0 的价格。"
    elif "sale_price_cents" in fields or new_mode != item.mode:
        # 非出售模式价格必须为空
        fields["sale_price_cents"] = None
    if field_errors:
        raise InputError("请检查编辑内容。", field_errors=field_errors)

    if "category_id" in fields:
        category = db.session.get(ItemCategory, fields["category_id"])
        if category is None or not category.is_active:
            raise InputError("所选分类无效。", field_errors={"category_id": "分类无效。"})
    if "campus_id" in fields:
        campus = db.session.get(Campus, fields["campus_id"])
        if (
            campus is None
            or campus.status != "active"
            or campus.university_id != actor.university_id
        ):
            raise InputError("所选校区无效。", field_errors={"campus_id": "校区无效。"})

    for key, value in fields.items():
        if key == "title":
            setattr(item, key, value.strip())
        elif key == "description":
            setattr(item, key, value.strip())
        else:
            setattr(item, key, value)
    item.updated_at = datetime.now(UTC)
    db.session.commit()
    return item


def change_item_shelf_state(actor, item_id: int, *, action: str, reason: str | None = None) -> Item:
    """下架 / 重新上架（FR-I06）。

    - action = "off_shelf"：所有者下架（无进行中业务时）；
    - action = "relist"：所有者重新上架（回收模式完成后不可重新上架，BR-015）；
    - 平台管理员可用 action = "force_off_shelf" 强制下架并记录原因与审计（FR-M02）。
    """
    item = db.session.get(Item, item_id)
    # 平台管理员跨高校执行强制下架（FR-M02），不受本校范围限制
    if item is None or (
        item.university_id != actor.university_id and not actor.is_platform_admin
    ):
        raise NotFoundError("没有找到该物品。")

    if action == "force_off_shelf":
        if not is_university_manager(actor):
            raise PermissionDeniedError("当前身份无法强制下架。")
        ensure_actor_university(actor, item.university_id)
        if not (reason and reason.strip()):
            raise InputError("强制下架必须填写原因。", field_errors={"reason": "请填写下架原因。"})
        item.moderation_status = "hidden"
        item.moderation_reason = reason.strip()
        item.updated_at = datetime.now(UTC)
        # BR-043：存在进行中业务时先进入异常冻结；无业务则真正下架。
        # 历史如实记录 from→to，不伪造从未发生的状态变化。
        if item.status == ITEM_OFF_SHELF:
            to_status = ITEM_OFF_SHELF
            reason_text = f"管理员标记隐藏（原已下架）：{reason.strip()}"
        elif item_has_active_request(item):
            to_status = "on_hold"
            reason_text = f"管理员异常冻结（存在进行中业务）：{reason.strip()}"
        else:
            to_status = ITEM_OFF_SHELF
            reason_text = f"管理员强制下架：{reason.strip()}"
        from_status = item.status
        if to_status != from_status:
            validate_item_transition(from_status, to_status)
            item.status = to_status
        _write_item_history(
            university_id=item.university_id,
            item_id=item.id,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor.id,
            reason=reason_text,
        )
        from app.services.notification_service import record_audit

        record_audit(
            actor_user_id=actor.id,
            university_id=item.university_id,
            action="item.force_off_shelf",
            entity_type="item",
            entity_id=item.id,
            detail={"reason": reason.strip(), "status": to_status},
        )
        db.session.commit()
        return item

    # 所有者操作
    if item.owner_user_id != actor.id:
        raise PermissionDeniedError("只能管理自己发布的物品。")
    _require_no_active_request(item)

    if action == "off_shelf":
        validate_item_transition(item.status, ITEM_OFF_SHELF)
        from_status = item.status
        item.status = ITEM_OFF_SHELF
        reason_text = "所有者下架"
    elif action == "relist":
        if item.status == ITEM_COMPLETED and item.mode == "recycle":
            raise PermissionDeniedError("回收完成的物品不能重新上架（BR-015）。")
        validate_item_transition(item.status, ITEM_ACTIVE)
        from_status = item.status
        item.status = ITEM_ACTIVE
        reason_text = "所有者重新上架"
    else:
        raise ValueError("无效的上下架操作")

    item.updated_at = datetime.now(UTC)
    _write_item_history(
        university_id=item.university_id,
        item_id=item.id,
        from_status=from_status,
        to_status=item.status,
        actor_user_id=actor.id,
        reason=reason_text,
    )
    db.session.commit()
    return item


def item_status_label(item: Item) -> str:
    return ITEM_STATUS_LABELS.get(item.status, item.status)


def list_recent_items(actor, *, limit: int = 50) -> list[Item]:
    """管理员审核页：最近更新的物品；校级管理员仅本校（FR-M02）。"""
    if not is_university_manager(actor):
        raise PermissionDeniedError("当前身份无法查看审核列表。")
    stmt = select(Item)
    if actor.is_university_admin:
        ensure_actor_university(actor, actor.university_id)
        stmt = stmt.where(Item.university_id == actor.university_id)
    stmt = stmt.order_by(Item.updated_at.desc()).limit(limit)
    return list(db.session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _require_student(actor) -> None:
    if not actor.is_student:
        raise PermissionDeniedError("只有在校学生可以发布物品。")


def _get_owned_item(actor, item_id: int) -> Item:
    item = db.session.get(Item, item_id)
    if item is None or item.university_id != actor.university_id:
        raise NotFoundError("没有找到该物品。")
    if item.owner_user_id != actor.id:
        raise PermissionDeniedError("只能管理自己发布的物品。")
    return item


def item_has_active_request(item: Item) -> bool:
    """物品是否存在活动申请（BR-012/BR-013）。

    数据库部分唯一索引是第二道防线；本查询供编辑/下架前检查。
    """
    from app.core.states import ACTIVE_REQUEST_STATUSES
    from app.models.circulation import CirculationRequest

    request = db.session.scalar(
        select(CirculationRequest).where(
            CirculationRequest.item_id == item.id,
            CirculationRequest.status.in_(ACTIVE_REQUEST_STATUSES),
        )
    )
    return request is not None


def _require_no_active_request(item: Item) -> None:
    if item_has_active_request(item):
        raise PermissionDeniedError("物品存在进行中的流转业务，当前不能编辑或下架（BR-013）。")


def _write_item_history(
    *,
    university_id: int,
    item_id: int,
    from_status: str | None,
    to_status: str,
    actor_user_id: int,
    reason: str,
) -> None:
    history = StatusHistory(
        university_id=university_id,
        entity_type="item",
        entity_id=item_id,
        from_status=from_status,
        to_status=to_status,
        actor_user_id=actor_user_id,
        reason=reason,
        created_at=datetime.now(UTC),
    )
    db.session.add(history)


def item_history(item: Item) -> list[StatusHistory]:
    """物品状态历史（时间线展示）。"""
    stmt = (
        select(StatusHistory)
        .where(
            StatusHistory.entity_type == "item",
            StatusHistory.entity_id == item.id,
            StatusHistory.university_id == item.university_id,
        )
        .order_by(StatusHistory.created_at.desc())
    )
    return list(db.session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# 图片（G3：FR-I02；R2 上传，数据库只保存对象 key）
# ---------------------------------------------------------------------------


def add_item_image(actor, item_id: int, *, content: bytes, content_type: str) -> ItemImage:
    """上传物品图片（最多 5 张、单张 3 MB、JPEG/PNG/WebP）。

    G4 加固：先以行锁读取物品行，再统计图片数量，并发上传不会突破 5 张；
    数据库提交失败时尽力删除刚上传的 R2 对象（失败只记录不含密钥的警告，
    不覆盖原异常）。
    """
    item = _get_owned_item(actor, item_id)
    _require_no_active_request(item)
    # 行锁读取物品行（与统计之间不允许并发上传插入）
    db.session.scalars(
        select(Item).where(Item.id == item_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()

    from flask import current_app

    from app.core.storage import StorageError, storage_from_config

    existing_count = (
        db.session.scalar(
            select(func.count()).select_from(ItemImage).where(ItemImage.item_id == item_id)
        )
        or 0
    )
    if existing_count >= 5:
        raise ConflictError("每个物品最多上传 5 张图片。")

    config = current_app.config["APP_CONFIG"]
    try:
        storage = storage_from_config(config)
        object_key = storage.put_image(content, content_type)
    except StorageError as err:
        raise InputError(str(err)) from None

    image = ItemImage(
        item_id=item_id,
        object_key=object_key,
        content_type=content_type,
        byte_size=len(content),
        sort_order=existing_count,
        created_at=datetime.now(UTC),
    )
    db.session.add(image)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        # 尽力删除刚上传的对象；失败只记录警告（不含密钥/连接串），不覆盖原异常
        try:
            storage.delete_image(object_key)
        except Exception:
            current_app.logger.warning(
                "图片数据库写入失败，清理对象存储对象未成功：key=%s", object_key
            )
        raise
    return image


def list_item_images(item_id: int) -> list[ItemImage]:
    """物品图片（按上传顺序）。"""
    stmt = select(ItemImage).where(ItemImage.item_id == item_id).order_by(ItemImage.sort_order)
    return list(db.session.scalars(stmt).all())


def delete_item_image(actor, item_id: int, image_id: int) -> None:
    """删除物品图片（仅所有者，且无进行中业务）。"""
    from app.core.errors import NotFoundError as _NF

    item = _get_owned_item(actor, item_id)
    _require_no_active_request(item)
    image = db.session.get(ItemImage, image_id)
    if image is None or image.item_id != item_id:
        raise _NF("没有找到该图片。")
    db.session.delete(image)
    db.session.commit()
