"""SQLAlchemy 模型（公益首版分组）。

表结构唯一来源是 sql/schema.sql；本模块只做持久化映射。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
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
    from app.models.user import User


class CharityProject(db.Model):
    """公益项目主记录（表 charity_projects）。"""

    __tablename__ = "charity_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    recipient_org: Mapped[str] = mapped_column(String(160))
    public_summary: Mapped[str] = mapped_column(Text)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    needs: Mapped[list[CharityProjectNeed]] = db.relationship("CharityProjectNeed", viewonly=True)

    __table_args__ = (
        UniqueConstraint("id", "university_id", name="charity_projects_id_university_id_key"),
    )


class CharityProjectNeed(db.Model):
    """公益项目物资目标（表 charity_project_needs）。"""

    __tablename__ = "charity_project_needs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("charity_projects.id"))
    item_category_id: Mapped[int] = mapped_column(ForeignKey("item_categories.id"))
    item_name: Mapped[str] = mapped_column(String(128))
    target_quantity: Mapped[int] = mapped_column(Integer)
    accepted_quantity: Mapped[int] = mapped_column(Integer, default=0)
    unit: Mapped[str] = mapped_column(String(16), default="件")
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "project_id", "item_category_id", "item_name", name="uq_need_project_category_name"
        ),
        CheckConstraint("target_quantity > 0", name="ck_need_target"),
        CheckConstraint(
            "accepted_quantity >= 0 AND accepted_quantity <= target_quantity",
            name="ck_need_accepted_within_target",
        ),
    )


class CharityDonation(db.Model):
    """一次实物捐赠的抬头（表 charity_donations）。"""

    __tablename__ = "charity_donations"

    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    project_id: Mapped[int]
    donor_user_id: Mapped[int]
    station_id: Mapped[int]
    status: Mapped[str] = mapped_column(String(16), default="pending")
    donor_note: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reject_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    items: Mapped[list[CharityDonationItem]] = db.relationship("CharityDonationItem", viewonly=True)
    project: Mapped[CharityProject] = db.relationship(
        "CharityProject", foreign_keys="CharityDonation.project_id", viewonly=True
    )
    donor: Mapped[User] = db.relationship(
        "User", foreign_keys="CharityDonation.donor_user_id", viewonly=True
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "university_id"],
            ["charity_projects.id", "charity_projects.university_id"],
        ),
        ForeignKeyConstraint(
            ["donor_user_id", "university_id"], ["users.id", "users.university_id"]
        ),
        ForeignKeyConstraint(
            ["station_id", "university_id"], ["stations.id", "stations.university_id"]
        ),
        UniqueConstraint("id", "project_id", name="charity_donations_id_project_id_key"),
        CheckConstraint(
            "status <> 'rejected' OR (reject_reason IS NOT NULL AND btrim(reject_reason) <> '')",
            name="ck_donation_reject_reason",
        ),
    )


class CharityDonationItem(db.Model):
    """捐赠物资明细（表 charity_donation_items）。"""

    __tablename__ = "charity_donation_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    donation_id: Mapped[int]
    project_id: Mapped[int]
    project_need_id: Mapped[int]
    item_name: Mapped[str] = mapped_column(String(128))
    quantity: Mapped[int] = mapped_column(Integer)
    accepted_quantity: Mapped[int] = mapped_column(Integer, default=0)
    condition: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    image_object_key: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["donation_id", "project_id"],
            ["charity_donations.id", "charity_donations.project_id"],
        ),
        ForeignKeyConstraint(
            ["project_need_id", "project_id"],
            ["charity_project_needs.id", "charity_project_needs.project_id"],
        ),
        CheckConstraint("quantity > 0", name="ck_donation_item_quantity"),
        CheckConstraint(
            "accepted_quantity >= 0 AND accepted_quantity <= quantity",
            name="ck_donation_item_accepted",
        ),
    )


class CharityReceipt(db.Model):
    """公益回执抬头（表 charity_receipts）。"""

    __tablename__ = "charity_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    project_id: Mapped[int]
    station_id: Mapped[int]
    title: Mapped[str] = mapped_column(String(160))
    recipient_org: Mapped[str] = mapped_column(String(160))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    public_note: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    items: Mapped[list[CharityReceiptItem]] = db.relationship("CharityReceiptItem", viewonly=True)
    project: Mapped[CharityProject] = db.relationship(
        "CharityProject", foreign_keys="CharityReceipt.project_id", viewonly=True
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "university_id"],
            ["charity_projects.id", "charity_projects.university_id"],
        ),
        ForeignKeyConstraint(
            ["station_id", "university_id"], ["stations.id", "stations.university_id"]
        ),
    )


class CharityReceiptItem(db.Model):
    """回执物资明细（表 charity_receipt_items）：可追溯到已接收捐赠明细。"""

    __tablename__ = "charity_receipt_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("charity_receipts.id"))
    donation_item_id: Mapped[int | None] = mapped_column(ForeignKey("charity_donation_items.id"))
    item_name: Mapped[str] = mapped_column(String(128))
    quantity: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (CheckConstraint("quantity > 0", name="ck_receipt_item_quantity"),)
