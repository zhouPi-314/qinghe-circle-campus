"""Security incidents, blocks and application event log."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app import db


class SecurityEvent(db.Model):
    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(16))
    subject_type: Mapped[str] = mapped_column(String(16))
    subject_hash: Mapped[str] = mapped_column(String(64))
    university_id: Mapped[int | None] = mapped_column(ForeignKey("universities.id"))
    route: Mapped[str | None] = mapped_column(String(255))
    event_count: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(16), default="open")
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "category IN ('sms_ip_threshold', 'captcha_failure_burst', "
            "'registration_enumeration', 'blocked_ip_retry')",
            name="ck_security_event_category",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_security_event_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'contained', 'resolved', 'false_positive')",
            name="ck_security_event_status",
        ),
        CheckConstraint(
            "subject_hash ~ '^[0-9a-f]{64}$'",
            name="ck_security_event_subject_hash",
        ),
    )


class SecurityBlock(db.Model):
    __tablename__ = "security_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(16))
    subject_hash: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    revoked_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'expired', 'revoked')",
            name="ck_security_block_status",
        ),
        CheckConstraint(
            "ends_at > starts_at",
            name="ck_security_block_times",
        ),
        CheckConstraint(
            "subject_hash ~ '^[0-9a-f]{64}$'",
            name="ck_security_block_subject_hash",
        ),
    )


class ApplicationEvent(db.Model):
    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[str] = mapped_column(String(16))
    event_code: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    route: Mapped[str | None] = mapped_column(String(255))
    method: Mapped[str | None] = mapped_column(String(12))
    status_code: Mapped[int | None]
    university_id: Mapped[int | None] = mapped_column(ForeignKey("universities.id"))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    summary: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "level IN ('info', 'warning', 'error', 'critical')",
            name="ck_application_event_level",
        ),
        CheckConstraint(
            "btrim(event_code) <> '' AND btrim(summary) <> ''",
            name="ck_application_event_text",
        ),
    )
