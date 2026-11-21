"""SQLAlchemy 模型（组织与账号分组）。

表结构唯一来源是 sql/schema.sql；本模块只做持久化映射，
不新增字段、约束或索引（交接书第 8 节数据库契约）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app import db


class University(db.Model):
    """高校：多高校租户根（表 universities）。"""

    __tablename__ = "universities"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    province: Mapped[str] = mapped_column(String(32))
    city: Mapped[str] = mapped_column(String(64))
    education_level: Mapped[str] = mapped_column(String(16))
    ownership: Mapped[str] = mapped_column(String(16))
    authority_name: Mapped[str | None] = mapped_column(String(128))
    source_url: Mapped[str | None] = mapped_column(String(512))
    source_updated_on: Mapped[datetime | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    campuses: Mapped[list[Campus]] = db.relationship(
        back_populates="university", order_by="Campus.is_primary.desc(), Campus.id"
    )


class Campus(db.Model):
    """校区（表 campuses）。"""

    __tablename__ = "campuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(128))
    address: Mapped[str | None] = mapped_column(String(255))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_status: Mapped[str] = mapped_column(String(16), default="temporary")
    source_url: Mapped[str | None] = mapped_column(String(512))
    source_updated_on: Mapped[datetime | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    university: Mapped[University] = db.relationship(back_populates="campuses")

    __table_args__ = (
        UniqueConstraint("university_id", "code", name="campuses_university_id_code_key"),
        UniqueConstraint("id", "university_id", name="campuses_id_university_id_key"),
    )


class Station(db.Model):
    """回收/公益服务点（表 stations）。"""

    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    campus_id: Mapped[int]
    name: Mapped[str] = mapped_column(String(128))
    station_type: Mapped[str] = mapped_column(String(16))
    address: Mapped[str] = mapped_column(String(255))
    service_hours: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["campus_id", "university_id"], ["campuses.id", "campuses.university_id"]
        ),
        UniqueConstraint("id", "university_id", name="stations_id_university_id_key"),
    )


class StationManagerAssignment(db.Model):
    """公益管理员站点授权（表 station_manager_assignments）。"""

    __tablename__ = "station_manager_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    station_id: Mapped[int]
    user_id: Mapped[int]
    started_on: Mapped[datetime] = mapped_column(Date)
    ended_on: Mapped[datetime | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["station_id", "university_id"], ["stations.id", "stations.university_id"]
        ),
        ForeignKeyConstraint(["user_id", "university_id"], ["users.id", "users.university_id"]),
    )


class StudentImportBatch(db.Model):
    """学生名单导入批次（表 student_import_batches）。"""

    __tablename__ = "student_import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    uploaded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    original_filename: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64))
    total_rows: Mapped[int] = mapped_column(default=0)
    success_rows: Mapped[int] = mapped_column(default=0)
    failed_rows: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(16), default="processing")
    error_summary: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("id", "university_id", name="student_import_batches_id_university_id_key"),
    )


class StudentRegistryRecord(db.Model):
    """学生名单核验记录（表 student_registry_records）。"""

    __tablename__ = "student_registry_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    campus_id: Mapped[int]
    latest_import_batch_id: Mapped[int]
    student_no: Mapped[str] = mapped_column(String(32))
    full_name: Mapped[str] = mapped_column(String(64))
    phone_hash: Mapped[str] = mapped_column(String(64))
    phone_last4: Mapped[str] = mapped_column(String(4))
    grade: Mapped[str] = mapped_column(String(32))
    class_name: Mapped[str] = mapped_column(String(64))
    major: Mapped[str] = mapped_column(String(128))
    college: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="active")
    registered_user_id: Mapped[int | None] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["campus_id", "university_id"], ["campuses.id", "campuses.university_id"]
        ),
        ForeignKeyConstraint(
            ["latest_import_batch_id", "university_id"],
            ["student_import_batches.id", "student_import_batches.university_id"],
        ),
        ForeignKeyConstraint(
            ["registered_user_id", "university_id"], ["users.id", "users.university_id"]
        ),
        UniqueConstraint("university_id", "student_no", name="uq_registry_university_student_no"),
        UniqueConstraint("university_id", "phone_hash", name="uq_registry_university_phone_hash"),
        UniqueConstraint("id", "university_id", name="uq_registry_id_university_id"),
        CheckConstraint("phone_hash ~ '^[0-9a-f]{64}$'", name="ck_registry_phone_hash"),
        CheckConstraint("phone_last4 ~ '^[0-9]{4}$'", name="ck_registry_phone_last4"),
    )


class LoginVerificationCode(db.Model):
    """模拟手机验证码（表 login_verification_codes）。"""

    __tablename__ = "login_verification_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    purpose: Mapped[str] = mapped_column(String(16), default="login")
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_attempts: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("code_hash ~ '^[0-9a-f]{64}$'", name="ck_login_code_hash"),)
