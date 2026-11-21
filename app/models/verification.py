"""注册验证请求（表 registration_verification_requests）。"""

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


class RegistrationVerificationRequest(db.Model):
    """一次注册验证码请求；不保存手机号或验证码明文。"""

    __tablename__ = "registration_verification_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    student_registry_record_id: Mapped[int | None]
    student_no_hash: Mapped[str] = mapped_column(String(64))
    phone_hash: Mapped[str] = mapped_column(String(64))
    code_hash: Mapped[str | None] = mapped_column(String(64))
    salt: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str | None] = mapped_column(String(16))
    out_id: Mapped[str] = mapped_column(String(64))
    provider_message_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    request_ip_hash: Mapped[str] = mapped_column(String(64))
    failed_attempts: Mapped[int] = mapped_column(default=0)
    resend_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["student_registry_record_id", "university_id"],
            ["student_registry_records.id", "student_registry_records.university_id"],
        ),
        UniqueConstraint("out_id", name="uq_registration_verification_out_id"),
        CheckConstraint(
            "status IN ('pending', 'sent', 'ignored', 'consumed', 'failed', 'expired')",
            name="ck_registration_verification_status",
        ),
        CheckConstraint(
            "student_no_hash ~ '^[0-9a-f]{64}$' "
            "AND phone_hash ~ '^[0-9a-f]{64}$' "
            "AND request_ip_hash ~ '^[0-9a-f]{64}$'",
            name="ck_registration_verification_hashes",
        ),
        CheckConstraint(
            "(provider IS NULL OR provider IN ('mock', 'aliyun_pnvs'))",
            name="ck_registration_verification_provider",
        ),
        CheckConstraint(
            "(status = 'ignored' "
            "AND student_registry_record_id IS NULL "
            "AND code_hash IS NULL AND salt IS NULL AND provider IS NULL) "
            "OR (status <> 'ignored' "
            "AND student_registry_record_id IS NOT NULL AND provider IS NOT NULL)",
            name="ck_registration_verification_scope",
        ),
        CheckConstraint(
            "provider IS DISTINCT FROM 'mock' "
            "OR (code_hash IS NOT NULL AND salt IS NOT NULL)",
            name="ck_registration_verification_mock_fields",
        ),
        CheckConstraint(
            "provider IS DISTINCT FROM 'aliyun_pnvs' "
            "OR (code_hash IS NULL AND salt IS NULL)",
            name="ck_registration_verification_aliyun_fields",
        ),
        CheckConstraint(
            "failed_attempts >= 0 AND btrim(out_id) <> ''",
            name="ck_registration_verification_values",
        ),
        CheckConstraint(
            "expires_at > created_at AND resend_after >= created_at",
            name="ck_registration_verification_times",
        ),
    )
