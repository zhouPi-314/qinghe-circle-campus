"""SQLAlchemy 模型（物品与发布分组）。

表结构唯一来源是 sql/schema.sql；本模块只做持久化映射。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app import db


class ItemCategory(db.Model):
    """物品分类（表 item_categories）。"""

    __tablename__ = "item_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Item(db.Model):
    """可流转物品主记录（表 items）。"""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    campus_id: Mapped[int]
    owner_user_id: Mapped[int]
    category_id: Mapped[int] = mapped_column(ForeignKey("item_categories.id"))
    mode: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    condition: Mapped[str] = mapped_column(String(16))
    sale_price_cents: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="active")
    moderation_status: Mapped[str] = mapped_column(String(16), default="normal")
    moderation_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["campus_id", "university_id"], ["campuses.id", "campuses.university_id"]
        ),
        ForeignKeyConstraint(
            ["owner_user_id", "university_id"], ["users.id", "users.university_id"]
        ),
        UniqueConstraint("id", "university_id", name="items_id_university_id_key"),
        UniqueConstraint("id", "mode", name="items_id_mode_key"),
        CheckConstraint(
            "(mode = 'sale' AND sale_price_cents IS NOT NULL AND sale_price_cents > 0)"
            " OR (mode <> 'sale' AND sale_price_cents IS NULL)",
            name="ck_items_sale_price",
        ),
    )


class ItemImage(db.Model):
    """物品图片（表 item_images）。图片上传随 G3 增量实现。"""

    __tablename__ = "item_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    object_key: Mapped[str] = mapped_column(String(512), unique=True)
    content_type: Mapped[str] = mapped_column(String(32))
    byte_size: Mapped[int] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
