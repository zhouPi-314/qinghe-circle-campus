"""SQLAlchemy 模型：统一账号（表 users）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app import db


class User(db.Model):
    """四类登录身份统一账号（表 users）。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int | None] = mapped_column(ForeignKey("universities.id"))
    campus_id: Mapped[int | None]
    login_name: Mapped[str | None] = mapped_column(String(64), unique=True)
    student_no: Mapped[str | None] = mapped_column(String(32))
    phone_hash: Mapped[str | None] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(255))
    password_must_change: Mapped[bool] = mapped_column(default=False)
    nickname: Mapped[str] = mapped_column(String(64))
    avatar_object_key: Mapped[str | None] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(32), default="student")
    status: Mapped[str] = mapped_column(String(16), default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("id", "university_id", name="users_id_university_id_key"),
        ForeignKeyConstraint(
            ["campus_id", "university_id"], ["campuses.id", "campuses.university_id"]
        ),
        CheckConstraint(
            "phone_hash IS NULL OR phone_hash ~ '^[0-9a-f]{64}$'", name="ck_users_phone_hash"
        ),
        CheckConstraint(
            "login_name IS NULL OR btrim(login_name) <> ''", name="ck_users_login_name"
        ),
    )
