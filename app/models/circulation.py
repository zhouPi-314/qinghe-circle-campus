"""SQLAlchemy 模型（申请与履约分组）。

表结构唯一来源是 sql/schema.sql；本模块只做持久化映射。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app import db

if TYPE_CHECKING:
    from app.models.item import Item
    from app.models.user import User


class CirculationRequest(db.Model):
    """四类流转统一申请（表 circulation_requests）。"""

    __tablename__ = "circulation_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    item_id: Mapped[int]
    requester_user_id: Mapped[int]
    owner_user_id: Mapped[int]
    mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    request_note: Mapped[str | None] = mapped_column(Text)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # 展示用只读关系（模板与页面组装使用；业务规则仍在 service 层）
    item: Mapped[Item] = db.relationship(
        "Item", primaryjoin="CirculationRequest.item_id == Item.id", viewonly=True
    )
    requester: Mapped[User] = db.relationship(
        "User", foreign_keys="CirculationRequest.requester_user_id", viewonly=True
    )
    owner: Mapped[User] = db.relationship(
        "User", foreign_keys="CirculationRequest.owner_user_id", viewonly=True
    )
    borrow_details: Mapped[BorrowDetails | None] = db.relationship("BorrowDetails", viewonly=True)

    __table_args__ = (
        ForeignKeyConstraint(["item_id", "university_id"], ["items.id", "items.university_id"]),
        ForeignKeyConstraint(["item_id", "mode"], ["items.id", "items.mode"]),
        ForeignKeyConstraint(
            ["requester_user_id", "university_id"], ["users.id", "users.university_id"]
        ),
        ForeignKeyConstraint(
            ["owner_user_id", "university_id"], ["users.id", "users.university_id"]
        ),
        UniqueConstraint("id", "university_id", name="circulation_requests_id_university_id_key"),
        CheckConstraint("requester_user_id <> owner_user_id", name="ck_requests_not_self"),
        CheckConstraint(
            "mode = 'sale' OR status <> 'payment_pending'", name="ck_requests_sale_payment"
        ),
        CheckConstraint(
            "mode = 'borrow' OR status NOT IN ('in_progress', 'return_pending')",
            name="ck_requests_borrow_states",
        ),
        CheckConstraint(
            "mode = 'recycle' OR status <> 'inspection_pending'", name="ck_requests_recycle_state"
        ),
    )


class BorrowDetails(db.Model):
    """借用专属字段（表 borrow_details）。"""

    __tablename__ = "borrow_details"

    request_id: Mapped[int] = mapped_column(ForeignKey("circulation_requests.id"), primary_key=True)
    start_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    return_note: Mapped[str | None] = mapped_column(Text)
    return_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    return_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    condition_ok: Mapped[bool | None] = mapped_column(Boolean)

    __table_args__ = (CheckConstraint("due_date >= start_date", name="ck_borrow_dates"),)


class SaleDetails(db.Model):
    """出售与模拟支付字段（表 sale_details）。出售流转随 G3 增量实现。"""

    __tablename__ = "sale_details"

    request_id: Mapped[int] = mapped_column(ForeignKey("circulation_requests.id"), primary_key=True)
    agreed_price_cents: Mapped[int] = mapped_column(Integer)
    payment_status: Mapped[str] = mapped_column(String(24), default="not_started")
    payment_reference: Mapped[str | None] = mapped_column(String(64))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("agreed_price_cents > 0", name="ck_sale_price_positive"),
        CheckConstraint(
            "(payment_status = 'paid' AND paid_at IS NOT NULL) OR payment_status <> 'paid'",
            name="ck_sale_paid_at",
        ),
    )


class RecycleDetails(db.Model):
    """回收站点与验收字段（表 recycle_details）。回收流转随 G3 增量实现。"""

    __tablename__ = "recycle_details"

    request_id: Mapped[int] = mapped_column(ForeignKey("circulation_requests.id"), primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"))
    preferred_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    preferred_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    inspection_status: Mapped[str] = mapped_column(String(16), default="pending")
    inspection_note: Mapped[str | None] = mapped_column(Text)
    inspected_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    inspected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("preferred_end_at > preferred_start_at", name="ck_recycle_window"),
    )


class HandoverRecord(db.Model):
    """一次性交接凭证（表 handover_records）。"""

    __tablename__ = "handover_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("circulation_requests.id"), unique=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    code_version: Mapped[int] = mapped_column(Integer, default=1)
    generated_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="active")

    __table_args__ = (
        CheckConstraint("code_version > 0", name="ck_handover_version"),
        CheckConstraint("code_hash ~ '^[0-9a-f]{64}$'", name="ck_handover_code_hash"),
        CheckConstraint(
            "(status = 'used' AND consumed_by_user_id IS NOT NULL AND consumed_at IS NOT NULL)"
            " OR (status <> 'used')",
            name="ck_handover_used",
        ),
    )
