"""Platform operations, abuse blocking and safe application events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app import db
from app.core.errors import (
    InputError,
    NotFoundError,
    PermissionDeniedError,
    TooManyRequestsError,
)
from app.core.security_monitor import safe_event_detail
from app.models.security import ApplicationEvent, SecurityBlock, SecurityEvent
from app.models.verification import RegistrationVerificationRequest
from app.services.notification_service import record_audit

REGISTRATION_IP_WINDOW = timedelta(minutes=10)
REGISTRATION_IP_LIMIT = 8
REGISTRATION_BLOCK_DURATION = timedelta(minutes=15)
REPEATED_BLOCK_DURATION = timedelta(hours=24)


def _require_platform(actor) -> None:
    if actor is None or not actor.is_platform_admin:
        raise PermissionDeniedError("运维与安全中心仅对平台管理员开放。")


def ensure_ip_allowed(
    subject_hash: str,
    *,
    university_id: int | None,
    route: str,
    now: datetime | None = None,
) -> None:
    """Block the ninth registration request from one IP hash in ten minutes."""
    now = now or datetime.now(UTC)
    lock_key = int(subject_hash[:16], 16)
    if lock_key >= 2**63:
        lock_key -= 2**64
    db.session.execute(select(func.pg_advisory_xact_lock(lock_key)))
    block = db.session.scalar(
        select(SecurityBlock)
        .where(
            SecurityBlock.subject_type == "ip",
            SecurityBlock.subject_hash == subject_hash,
            SecurityBlock.status == "active",
        )
        .with_for_update()
    )
    if block is not None:
        if block.ends_at <= now:
            block.status = "expired"
            block.updated_at = now
            db.session.commit()
        else:
            raise TooManyRequestsError("请求过于频繁，请稍后再试。")

    attempts = db.session.scalar(
        select(func.count())
        .select_from(RegistrationVerificationRequest)
        .where(
            RegistrationVerificationRequest.request_ip_hash == subject_hash,
            RegistrationVerificationRequest.created_at >= now - REGISTRATION_IP_WINDOW,
        )
    ) or 0
    if attempts < REGISTRATION_IP_LIMIT:
        return

    recent_blocks = db.session.scalar(
        select(func.count())
        .select_from(SecurityBlock)
        .where(
            SecurityBlock.subject_type == "ip",
            SecurityBlock.subject_hash == subject_hash,
            SecurityBlock.created_at >= now - timedelta(hours=24),
        )
    ) or 0
    duration = REPEATED_BLOCK_DURATION if recent_blocks >= 2 else REGISTRATION_BLOCK_DURATION
    try:
        create_ip_block(
            subject_hash=subject_hash,
            category="sms_ip_threshold",
            duration=duration,
            detail={
                "attempts": attempts,
                "window_minutes": 10,
                "route": route,
            },
            university_id=university_id,
            now=now,
        )
    except IntegrityError:
        db.session.rollback()
    raise TooManyRequestsError("请求过于频繁，请稍后再试。")


def create_ip_block(
    *,
    subject_hash: str,
    category: str,
    duration: timedelta,
    detail: dict | None = None,
    university_id: int | None = None,
    now: datetime | None = None,
):
    now = now or datetime.now(UTC)
    block = SecurityBlock(
        subject_type="ip",
        subject_hash=subject_hash,
        category=category,
        severity="high",
        reason="同一 IP 短时间内高频请求注册短信验证码",
        status="active",
        starts_at=now,
        ends_at=now + duration,
        created_at=now,
        updated_at=now,
    )
    event = SecurityEvent(
        category=category,
        severity="high",
        subject_type="ip",
        subject_hash=subject_hash,
        university_id=university_id,
        route="/auth/register/sms-code",
        event_count=int((detail or {}).get("attempts", 1)),
        status="contained",
        detail=safe_event_detail(detail or {}),
        first_seen_at=now,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )
    db.session.add_all((block, event))
    db.session.commit()
    return block


def set_block_disposition(
    actor,
    block_id: int,
    *,
    action: str,
    reason: str,
) -> SecurityBlock:
    _require_platform(actor)
    if action not in ("revoke", "false_positive"):
        raise InputError("无效的封禁处置。")
    reason = (reason or "").strip()
    if not reason:
        raise InputError("请填写处置原因。")
    block = db.session.scalar(
        select(SecurityBlock).where(SecurityBlock.id == block_id).with_for_update()
    )
    if block is None:
        raise NotFoundError("封禁记录不存在。")
    now = datetime.now(UTC)
    block.status = "revoked"
    block.revoked_by_user_id = actor.id
    block.revoked_at = now
    block.updated_at = now
    if action == "false_positive":
        event = db.session.scalar(
            select(SecurityEvent)
            .where(
                SecurityEvent.subject_type == block.subject_type,
                SecurityEvent.subject_hash == block.subject_hash,
                SecurityEvent.category == block.category,
            )
            .order_by(SecurityEvent.created_at.desc())
            .with_for_update()
        )
        if event is not None:
            event.status = "false_positive"
            event.updated_at = now
    record_audit(
        actor_user_id=actor.id,
        university_id=block.university_id if hasattr(block, "university_id") else None,
        action=f"security.block.{action}",
        entity_type="security_block",
        entity_id=block.id,
        detail={"reason": reason},
    )
    db.session.commit()
    return block


def record_application_event(
    *,
    level: str,
    event_code: str,
    summary: str,
    request_id: str | None = None,
    route: str | None = None,
    method: str | None = None,
    status_code: int | None = None,
    university_id: int | None = None,
    actor_user_id: int | None = None,
    detail: dict | None = None,
) -> None:
    db.session.rollback()
    db.session.add(
        ApplicationEvent(
            level=level,
            event_code=event_code,
            request_id=request_id,
            route=route,
            method=method,
            status_code=status_code,
            university_id=university_id,
            actor_user_id=actor_user_id,
            summary=(summary or "应用事件")[:500],
            detail=safe_event_detail(detail or {}),
            created_at=datetime.now(UTC),
        )
    )
    db.session.commit()


def operations_snapshot(actor) -> dict:
    _require_platform(actor)
    now = datetime.now(UTC)
    since = now - timedelta(hours=24)
    try:
        db.session.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        db.session.rollback()
        database = "unavailable"
    return {
        "database": database,
        "sms_sent": db.session.scalar(
            select(func.count())
            .select_from(RegistrationVerificationRequest)
            .where(
                RegistrationVerificationRequest.created_at >= since,
                RegistrationVerificationRequest.status.in_(("sent", "consumed")),
            )
        )
        or 0,
        "sms_failed": db.session.scalar(
            select(func.count())
            .select_from(RegistrationVerificationRequest)
            .where(
                RegistrationVerificationRequest.created_at >= since,
                RegistrationVerificationRequest.status == "failed",
            )
        )
        or 0,
        "active_blocks": db.session.scalar(
            select(func.count())
            .select_from(SecurityBlock)
            .where(SecurityBlock.status == "active", SecurityBlock.ends_at > now)
        )
        or 0,
        "open_events": db.session.scalar(
            select(func.count())
            .select_from(SecurityEvent)
            .where(SecurityEvent.status.in_(("open", "contained")))
        )
        or 0,
        "recent_errors": db.session.scalar(
            select(func.count())
            .select_from(ApplicationEvent)
            .where(
                ApplicationEvent.created_at >= since,
                ApplicationEvent.level.in_(("error", "critical")),
            )
        )
        or 0,
    }


def list_security_events(actor, *, limit: int = 100) -> list[SecurityEvent]:
    _require_platform(actor)
    return list(
        db.session.scalars(
            select(SecurityEvent).order_by(SecurityEvent.created_at.desc()).limit(limit)
        ).all()
    )


def list_security_blocks(actor, *, limit: int = 100) -> list[SecurityBlock]:
    _require_platform(actor)
    return list(
        db.session.scalars(
            select(SecurityBlock).order_by(SecurityBlock.created_at.desc()).limit(limit)
        ).all()
    )


def list_application_events(actor, *, limit: int = 100) -> list[ApplicationEvent]:
    _require_platform(actor)
    return list(
        db.session.scalars(
            select(ApplicationEvent).order_by(ApplicationEvent.created_at.desc()).limit(limit)
        ).all()
    )
