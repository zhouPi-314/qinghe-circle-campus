"""SQLAlchemy 模型（通知与治理分组）。

表结构唯一来源是 sql/schema.sql；本模块只做持久化映射。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app import db


class StatusHistory(db.Model):
    """关键状态历史（表 status_history）：只追加，不更新或删除。"""

    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int]
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Notification(db.Model):
    """站内通知（表 notifications）。"""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    recipient_user_id: Mapped[int]
    category: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    related_entity_type: Mapped[str | None] = mapped_column(String(32))
    related_entity_id: Mapped[int | None]
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["recipient_user_id", "university_id"], ["users.id", "users.university_id"]
        ),
    )


class Dispute(db.Model):
    """争议主记录（表 disputes）。"""

    __tablename__ = "disputes"

    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    circulation_request_id: Mapped[int]
    opened_by_user_id: Mapped[int]
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["circulation_request_id", "university_id"],
            ["circulation_requests.id", "circulation_requests.university_id"],
        ),
        ForeignKeyConstraint(
            ["opened_by_user_id", "university_id"], ["users.id", "users.university_id"]
        ),
    )


class DisputeMessage(db.Model):
    """争议双方说明（表 dispute_messages）：只追加。"""

    __tablename__ = "dispute_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    dispute_id: Mapped[int] = mapped_column(ForeignKey("disputes.id"))
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    attachment_object_key: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditLog(db.Model):
    """关键操作审计（表 audit_logs）：只追加。"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int | None] = mapped_column(ForeignKey("universities.id"))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[int | None]
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("btrim(action) <> ''", name="ck_audit_action"),
        CheckConstraint("btrim(entity_type) <> ''", name="ck_audit_entity_type"),
    )
