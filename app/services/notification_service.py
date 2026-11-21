"""通知与审计 Service。

公开接口（交接书第 7 节）：notify()、list_notifications()、
mark_notification_read()、record_audit()。

notify/record_audit 由业务 service 在同一事务内调用（不单独 commit），
保证状态历史、通知与业务状态同时生效或同时回滚。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app import db
from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.permissions import ensure_actor_university, is_university_manager
from app.models.governance import AuditLog, Notification


def notify(
    *,
    university_id: int,
    recipient_user_id: int,
    category: str,
    title: str,
    body: str,
    related_entity_type: str | None = None,
    related_entity_id: int | None = None,
) -> None:
    """写入一条站内通知；调用方事务内提交。"""
    notification = Notification(
        university_id=university_id,
        recipient_user_id=recipient_user_id,
        category=category,
        title=title,
        body=body,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        created_at=datetime.now(UTC),
    )
    db.session.add(notification)


def notify_users(
    *,
    university_id: int,
    recipient_ids: set[int],
    category: str,
    title: str,
    body: str,
    related_entity_type: str | None = None,
    related_entity_id: int | None = None,
) -> None:
    """向多方写入同一业务事件的通知。"""
    for recipient in recipient_ids:
        notify(
            university_id=university_id,
            recipient_user_id=recipient,
            category=category,
            title=title,
            body=body,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
        )


def list_notifications(actor, *, unread_only: bool = False, limit: int = 50) -> list[Notification]:
    """当前用户的站内通知（默认最近 50 条，可筛选未读）。"""
    stmt = (
        select(Notification)
        .where(Notification.recipient_user_id == actor.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    return list(db.session.scalars(stmt).all())


def mark_notification_read(actor, notification_id: int) -> None:
    """标记当前用户自己的通知为已读；他人通知拒绝。"""
    notification = db.session.get(Notification, notification_id)
    if notification is None:
        raise NotFoundError("通知不存在或已删除。")
    if notification.recipient_user_id != actor.id:
        raise PermissionDeniedError("只能操作自己的通知。")
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        db.session.commit()


def record_audit(
    *,
    actor_user_id: int | None,
    university_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    detail: dict | None = None,
) -> None:
    """写入关键操作审计；调用方事务内提交。

    detail 不得包含密码、验证码、手机号明文、连接串或密钥。
    """
    audit = AuditLog(
        university_id=university_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=detail or {},
        created_at=datetime.now(UTC),
    )
    db.session.add(audit)


def list_audit_logs(actor, *, limit: int = 100) -> list[AuditLog]:
    """管理员查询审计日志；校级管理员只查看本校。"""
    if not is_university_manager(actor):
        raise PermissionDeniedError("当前身份无法查看审计日志。")
    stmt = select(AuditLog)
    if actor.is_university_admin:
        ensure_actor_university(actor, actor.university_id)
        stmt = stmt.where(AuditLog.university_id == actor.university_id)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
    return list(db.session.scalars(stmt).all())


def unread_count(actor) -> int:
    """当前用户未读通知数量。"""
    stmt = select(Notification).where(
        Notification.recipient_user_id == actor.id, Notification.read_at.is_(None)
    )
    return len(list(db.session.scalars(stmt).all()))
