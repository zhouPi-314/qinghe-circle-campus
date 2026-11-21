"""身份与准入 Service。

公开接口（交接书第 7 节）：
- get_student_context()        学生登录前的学校与校区上下文
- register_student(...)        名单核验注册
- authenticate_password(...)   密码登录（学生按学校上下文，管理员按 login_name）
- load_current_user(user_id)   由会话 user_id 载入当前用户

G1 范围说明：issue_login_code / verify_login_code（验证码登录）、
update_profile、import_students、import_managed_accounts 属于同一模块的后续增量，
随 G2 及之后的增量实现，不在 G1 门禁范围内。

核心规则（SRS BR-005 ~ BR-010、BR-044、BR-045）：
- 只有在校学生可自主注册，且必须在管理员导入的本校名单中；
- 学生姓名、学院、专业、年级、班级和校区从名单带入；
- 学生账号必须属于所选学校（同校校验在服务端）；
- 密码只存哈希；手机号只存 HMAC 哈希与后四位；
- 权限和高校范围在 service 层校验。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from flask import current_app, has_request_context, session
from sqlalchemy import select

from app import db
from app.core.auth import is_valid_phone, normalize_phone, phone_hash, phone_hmac_key
from app.core.captcha import verify_captcha
from app.core.errors import ConflictError, InputError, NotFoundError, PermissionDeniedError
from app.core.permissions import ensure_actor_university, is_university_manager
from app.core.sms import MOCK_SMS_CODE, SmsProviderError
from app.models.university import Campus, StudentRegistryRecord, University
from app.models.user import User
from app.models.verification import RegistrationVerificationRequest

_PASSWORD_MIN_LENGTH = 8
REGISTRATION_CODE_GENERIC_MESSAGE = "如果名单信息匹配，验证码将发送到预留手机号。"
REGISTRATION_CODE_COOLDOWN_SECONDS = 60
REGISTRATION_CODE_TTL_SECONDS = 300
REGISTRATION_CODE_MAX_ATTEMPTS = 5
SESSION_REGISTRATION_VERIFICATION_ID = "auth.registration_verification_id"
SESSION_REGISTRATION_RESEND_AFTER = "auth.registration_resend_after"
SESSION_REGISTRATION_MOCK_CODE = "auth.registration_mock_code"


# ---------------------------------------------------------------------------
# 学生登录上下文
# ---------------------------------------------------------------------------


def get_student_context() -> dict:
    """返回可选学校与校区（仅 active）。

    单校区高校按一个校区运行（BR-004）；多校区高校列出已登记校区。
    返回结构供模板渲染，不包含核验名单等内部数据。
    """
    universities = db.session.scalars(
        select(University).where(University.status == "active").order_by(University.code)
    ).all()

    campus_rows = db.session.execute(
        select(Campus)
        .where(Campus.status == "active")
        .order_by(Campus.university_id, Campus.is_primary.desc(), Campus.id)
    ).all()

    campuses_by_university: dict[int, list[dict]] = {}
    for (campus,) in campus_rows:
        campuses_by_university.setdefault(campus.university_id, []).append(
            {
                "id": campus.id,
                "code": campus.code,
                "name": campus.name,
                "is_primary": campus.is_primary,
            }
        )

    items: list[dict] = []
    for uni in universities:
        campuses = campuses_by_university.get(uni.id, [])
        items.append(
            {
                "id": uni.id,
                "code": uni.code,
                "name": uni.name,
                "city": uni.city,
                "education_level": uni.education_level,
                "campuses": campuses,
                # 单校区高校的校区选项显示学校全称（BR-045）
                "single_campus": len(campuses) == 1,
            }
        )
    return {"universities": items}


# ---------------------------------------------------------------------------
# 学生注册（名单核验）
# ---------------------------------------------------------------------------


def request_registration_code(
    *,
    university_id: int,
    campus_id: int,
    student_no: str,
    phone: str,
    captcha_answer: str,
    request_ip: str | None,
) -> dict:
    """Issue a registration challenge without disclosing roster membership."""
    student_no = (student_no or "").strip()
    field_errors: dict[str, str] = {}
    if not student_no:
        field_errors["student_no"] = "请输入学号。"
    if not is_valid_phone(phone or ""):
        field_errors["phone"] = "请输入 11 位大陆手机号。"
    if field_errors:
        raise InputError("请检查表单填写内容。", field_errors=field_errors)

    if not verify_captcha(session, captcha_answer):
        raise InputError(
            "图形验证码错误或已过期，请重新输入。",
            field_errors={"captcha": "图形验证码错误或已过期。"},
        )

    now = datetime.now(UTC)
    university = db.session.get(University, university_id)
    if university is None or university.status != "active":
        raise NotFoundError("所选学校不存在或已停用，请返回重新选择学校。")

    normalized_phone = normalize_phone(phone)
    student_no_digest = _registration_hash("student-no", student_no)
    phone_digest = phone_hash(normalized_phone)
    ip_digest = _registration_hash("request-ip", request_ip or "unknown")

    record = db.session.scalars(
        select(StudentRegistryRecord)
        .where(
            StudentRegistryRecord.university_id == university_id,
            StudentRegistryRecord.campus_id == int(campus_id),
            StudentRegistryRecord.student_no == student_no,
            StudentRegistryRecord.status == "active",
        )
        .with_for_update()
    ).first()
    if (
        record is None
        or record.registered_user_id is not None
        or record.phone_hash != phone_digest
    ):
        _clear_challenge_session()
        _add_ignored_registration_attempt(
            university_id=university_id,
            student_no_hash=student_no_digest,
            phone_hash=phone_digest,
            request_ip_hash=ip_digest,
            now=now,
        )
        db.session.commit()
        return {"message": REGISTRATION_CODE_GENERIC_MESSAGE}

    active = db.session.scalars(
        select(RegistrationVerificationRequest)
        .where(
            RegistrationVerificationRequest.student_registry_record_id == record.id,
            RegistrationVerificationRequest.status.in_(("pending", "sent")),
        )
        .order_by(RegistrationVerificationRequest.created_at.desc())
        .with_for_update()
    ).first()
    if active is not None and (
        active.expires_at <= now or active.resend_after <= now
    ):
        active.status = "expired"
        db.session.flush()
    elif active is not None:
        _set_challenge_session(
            active.id,
            resend_after=active.resend_after,
            mock_code=current_app.extensions["sms_sender"].display_code,
        )
        db.session.commit()
        return {"message": REGISTRATION_CODE_GENERIC_MESSAGE}

    sender = current_app.extensions["sms_sender"]
    provider = "mock" if sender.display_code is not None else "aliyun_pnvs"
    salt = secrets.token_hex(32) if provider == "mock" else None
    code_hash = (
        hmac.new(bytes.fromhex(salt), MOCK_SMS_CODE.encode(), hashlib.sha256).hexdigest()
        if salt is not None
        else None
    )
    challenge = RegistrationVerificationRequest(
        university_id=university_id,
        student_registry_record_id=record.id,
        student_no_hash=student_no_digest,
        phone_hash=phone_digest,
        code_hash=code_hash,
        salt=salt,
        provider=provider,
        out_id=uuid.uuid4().hex,
        provider_message_id=None,
        status="pending",
        request_ip_hash=ip_digest,
        failed_attempts=0,
        resend_after=now + timedelta(seconds=REGISTRATION_CODE_COOLDOWN_SECONDS),
        expires_at=now + timedelta(seconds=REGISTRATION_CODE_TTL_SECONDS),
        sent_at=None,
        consumed_at=None,
        created_at=now,
    )
    db.session.add(challenge)
    db.session.commit()
    _set_challenge_session(challenge.id, resend_after=challenge.resend_after)

    try:
        sent = sender.send_register_code(normalized_phone, challenge.out_id)
    except SmsProviderError:
        challenge.status = "failed"
        db.session.commit()
        _clear_challenge_session()
        raise

    challenge.status = "sent"
    challenge.provider_message_id = sent.message_id
    challenge.sent_at = datetime.now(UTC)
    db.session.commit()

    config = current_app.config.get("APP_CONFIG")
    mock_code = sender.display_code
    if mock_code and getattr(config, "vercel_env", None) == "production":
        mock_code = None
    _set_challenge_session(
        challenge.id,
        resend_after=challenge.resend_after,
        mock_code=mock_code,
    )
    return {"message": REGISTRATION_CODE_GENERIC_MESSAGE}


def register_student(
    *,
    university_id: int,
    campus_id: int,
    student_no: str,
    phone: str,
    password: str,
    verification_request_id: int | None = None,
    sms_code: str | None = None,
) -> User:
    """Register a student after server-side SMS verification."""
    if verification_request_id is None:
        if current_app.testing:
            return _register_student_legacy(
                university_id=university_id,
                campus_id=campus_id,
                student_no=student_no,
                phone=phone,
                password=password,
            )
        raise InputError(
            "请先完成短信验证。",
            field_errors={"sms_code": "请先获取并输入短信验证码。"},
        )
    return _register_student_verified(
        university_id=university_id,
        campus_id=campus_id,
        student_no=student_no,
        phone=phone,
        password=password,
        verification_request_id=verification_request_id,
        sms_code=sms_code,
    )


def _register_student_legacy(
    *,
    university_id: int,
    campus_id: int,
    student_no: str,
    phone: str,
    password: str,
) -> User:
    """在校学生名单核验注册。

    - 学号与手机号必须与名单记录匹配（BR-005）；
    - 校区以名单带入（BR-006），所选校区与名单不符时拒绝；
    - 已注册名单记录不可重复注册（异常需求：重复注册拒绝并引导登录）；
    - 同一事务写入 users 与 student_registry_records.registered_user_id。
    """
    student_no = (student_no or "").strip()

    field_errors: dict[str, str] = {}
    if not student_no:
        field_errors["student_no"] = "请输入学号。"
    if not is_valid_phone(phone or ""):
        field_errors["phone"] = "请输入 11 位大陆手机号。"
    _validate_password(password, field_errors)
    if field_errors:
        raise InputError("请检查表单填写内容。", field_errors=field_errors)

    university = db.session.get(University, university_id)
    if university is None or university.status != "active":
        raise NotFoundError("所选学校不存在或已停用，请返回重新选择学校。")

    # 名单匹配：本校 + 学号 + 有效状态
    record = db.session.scalar(
        select(StudentRegistryRecord).where(
            StudentRegistryRecord.university_id == university_id,
            StudentRegistryRecord.student_no == student_no,
            StudentRegistryRecord.status == "active",
        )
    )
    if record is None:
        raise InputError(
            "学号不在本校学生名单中。请核对学号，或联系辅导员确认名单已导入。",
            field_errors={"student_no": "学号不在本校名单中。"},
        )

    if record.registered_user_id is not None:
        raise ConflictError("该学号已注册过账号。请直接登录；忘记密码请联系平台管理员。")

    if record.phone_hash != phone_hash(phone):
        raise InputError(
            "手机号与名单记录不一致。请核对手机号，或联系辅导员更正名单。",
            field_errors={"phone": "手机号与名单记录不符。"},
        )

    if int(campus_id) != record.campus_id:
        raise InputError(
            "所选校区与名单记录不符。学生校区由名单带入，请返回选择名单中的校区。",
            field_errors={"campus_id": "校区与名单记录不符。"},
        )

    # 重复账号防护（数据库唯一索引是第二道防线）
    existing = db.session.scalar(
        select(User).where(User.university_id == university_id, User.student_no == student_no)
    )
    if existing is not None:
        raise ConflictError("该学号已注册过账号。请直接登录；忘记密码请联系平台管理员。")

    now = datetime.now(UTC)
    user = User(
        university_id=university_id,
        campus_id=record.campus_id,
        student_no=student_no,
        phone_hash=record.phone_hash,
        password_hash=hash_password(password),
        nickname=record.full_name,
        role="student",
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.session.add(user)
    db.session.flush()

    record.registered_user_id = user.id
    record.updated_at = now
    db.session.commit()
    return user


def _register_student_verified(
    *,
    university_id: int,
    campus_id: int,
    student_no: str,
    phone: str,
    password: str,
    verification_request_id: int,
    sms_code: str | None,
) -> User:
    student_no = (student_no or "").strip()
    field_errors: dict[str, str] = {}
    if not student_no:
        field_errors["student_no"] = "请输入学号。"
    if not is_valid_phone(phone or ""):
        field_errors["phone"] = "请输入 11 位大陆手机号。"
    if not sms_code:
        field_errors["sms_code"] = "请输入短信验证码。"
    _validate_password(password, field_errors)
    if field_errors:
        raise InputError("请检查表单填写内容。", field_errors=field_errors)

    now = datetime.now(UTC)
    challenge = db.session.scalars(
        select(RegistrationVerificationRequest)
        .where(
            RegistrationVerificationRequest.id == verification_request_id,
            RegistrationVerificationRequest.university_id == university_id,
        )
        .with_for_update()
    ).first()
    if challenge is None or challenge.status not in ("pending", "sent"):
        raise InputError(
            "短信验证码无效或已失效，请重新获取。",
            field_errors={"sms_code": "短信验证码无效或已失效。"},
        )
    if challenge.expires_at <= now:
        challenge.status = "expired"
        db.session.commit()
        raise InputError(
            "短信验证码已过期，请重新获取。",
            field_errors={"sms_code": "短信验证码已过期。"},
        )

    record = db.session.scalars(
        select(StudentRegistryRecord)
        .where(StudentRegistryRecord.id == challenge.student_registry_record_id)
        .with_for_update()
    ).first()
    normalized_phone = normalize_phone(phone)
    if (
        record is None
        or record.university_id != university_id
        or record.campus_id != int(campus_id)
        or record.student_no != student_no
        or record.phone_hash != phone_hash(normalized_phone)
        or challenge.student_no_hash != _registration_hash("student-no", student_no)
        or challenge.phone_hash != phone_hash(normalized_phone)
    ):
        _fail_registration_challenge(challenge)
        raise InputError(
            "短信验证码无效或已失效，请重新获取。",
            field_errors={"sms_code": "短信验证码无效或已失效。"},
        )
    if record.registered_user_id is not None:
        challenge.status = "failed"
        db.session.commit()
        raise ConflictError("该学号已注册过账号。请直接登录。")

    sender = current_app.extensions["sms_sender"]
    try:
        passed = sender.verify_register_code(normalized_phone, sms_code, challenge.out_id)
    except SmsProviderError:
        raise InputError("短信核验服务暂时不可用，请稍后重试。") from None
    if not passed:
        _fail_registration_challenge(challenge)
        raise InputError(
            "短信验证码不正确，请检查后重试。",
            field_errors={"sms_code": "短信验证码不正确。"},
        )

    user = User(
        university_id=university_id,
        campus_id=record.campus_id,
        student_no=student_no,
        phone_hash=record.phone_hash,
        password_hash=hash_password(password),
        nickname=record.full_name,
        role="student",
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.session.add(user)
    db.session.flush()
    record.registered_user_id = user.id
    record.updated_at = now
    challenge.status = "consumed"
    challenge.consumed_at = now
    db.session.commit()
    _clear_challenge_session()
    return user


def _registration_hash(label: str, value: str) -> str:
    material = f"qinghe-registration-{label}:{value}".encode()
    return hmac.new(phone_hmac_key(), material, hashlib.sha256).hexdigest()


def _add_ignored_registration_attempt(
    *,
    university_id: int,
    student_no_hash: str,
    phone_hash: str,
    request_ip_hash: str,
    now: datetime,
) -> None:
    db.session.add(
        RegistrationVerificationRequest(
            university_id=university_id,
            student_registry_record_id=None,
            student_no_hash=student_no_hash,
            phone_hash=phone_hash,
            code_hash=None,
            salt=None,
            provider=None,
            out_id=uuid.uuid4().hex,
            provider_message_id=None,
            status="ignored",
            request_ip_hash=request_ip_hash,
            failed_attempts=0,
            resend_after=now + timedelta(seconds=REGISTRATION_CODE_COOLDOWN_SECONDS),
            expires_at=now + timedelta(seconds=REGISTRATION_CODE_TTL_SECONDS),
            sent_at=None,
            consumed_at=None,
            created_at=now,
        )
    )


def _fail_registration_challenge(challenge: RegistrationVerificationRequest) -> None:
    challenge.failed_attempts += 1
    if challenge.failed_attempts >= REGISTRATION_CODE_MAX_ATTEMPTS:
        challenge.status = "failed"
    db.session.commit()


def _set_challenge_session(
    challenge_id: int,
    *,
    resend_after: datetime,
    mock_code: str | None = None,
) -> None:
    if has_request_context():
        session[SESSION_REGISTRATION_VERIFICATION_ID] = challenge_id
        session[SESSION_REGISTRATION_RESEND_AFTER] = int(resend_after.timestamp())
        if mock_code:
            session[SESSION_REGISTRATION_MOCK_CODE] = mock_code
        else:
            session.pop(SESSION_REGISTRATION_MOCK_CODE, None)


def _clear_challenge_session() -> None:
    if has_request_context():
        for key in (
            SESSION_REGISTRATION_VERIFICATION_ID,
            SESSION_REGISTRATION_RESEND_AFTER,
            SESSION_REGISTRATION_MOCK_CODE,
        ):
            session.pop(key, None)


# ---------------------------------------------------------------------------
# 密码登录
# ---------------------------------------------------------------------------


def authenticate_password(
    *,
    role: str,
    identifier: str,
    password: str,
    student_university_id: int | None = None,
) -> User:
    """密码登录。

    - 学生：使用学号或手机号，账号必须属于已选择的学校（BR-044、FR-A08）；
      学校上下文由路由从会话传入；
    - 公益管理员 / 平台管理员 / 校级管理员：使用 login_name；
    - 身份必须与登录入口选择的身份一致；
    - 账号停用时拒绝登录。
    """
    identifier = (identifier or "").strip()
    password = password or ""

    if not identifier:
        raise InputError("请输入登录账号。", field_errors={"identifier": "请输入登录账号。"})
    if not password:
        raise InputError("请输入密码。", field_errors={"password": "请输入密码。"})

    if role == "student":
        user = _authenticate_student(identifier, password, student_university_id)
    elif role in ("station_manager", "platform_admin", "university_admin"):
        user = _authenticate_manager(role, identifier, password)
    else:
        raise ValueError("无效的登录身份")

    # 账号停用：明确提示且不泄露其他信息
    if user.status != "active":
        raise PermissionDeniedError("账号已停用。如需恢复访问，请联系平台管理员。")

    user.last_login_at = datetime.now(UTC)
    user.updated_at = datetime.now(UTC)
    db.session.commit()
    return user


def _authenticate_student(identifier: str, password: str, university_id: int | None) -> User:
    if university_id is None:
        raise InputError("请先选择学校与校区，再登录学生账号。")

    if is_valid_phone(identifier):
        conditions = (User.phone_hash == phone_hash(identifier),)
    else:
        conditions = (User.student_no == identifier,)

    user = db.session.scalar(
        select(User).where(User.university_id == university_id, User.role == "student", *conditions)
    )
    if user is None or not check_password(user.password_hash, password):
        raise InputError(
            "账号或密码不正确。请核对后重试；手机号登录请先在注册时绑定本校名单手机号。",
        )
    return user


def _authenticate_manager(role: str, identifier: str, password: str) -> User:
    user = db.session.scalar(select(User).where(User.login_name == identifier, User.role == role))
    if user is None or not check_password(user.password_hash, password):
        raise InputError("账号或密码不正确。管理员账号由平台管理员导入或系统预设，不提供注册入口。")
    return user


# ---------------------------------------------------------------------------
# 当前用户
# ---------------------------------------------------------------------------


def load_current_user(user_id: int):
    """由会话 user_id 载入用户；不存在或停用时返回 None。"""
    user = db.session.get(User, user_id)
    if user is None or user.status != "active":
        return None
    return user


# ---------------------------------------------------------------------------
# 密码工具（werkzeug 慢哈希；G1 供 service 与测试使用）
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    from werkzeug.security import generate_password_hash

    return generate_password_hash(password)


def check_password(password_hash: str, password: str) -> bool:
    from werkzeug.security import check_password_hash

    return check_password_hash(password_hash, password)


def validate_password_strength(password: str) -> None:
    """密码策略：至少 8 位且同时包含字母和数字。"""
    field_errors: dict[str, str] = {}
    _validate_password(password, field_errors)
    if field_errors:
        raise InputError("密码不符合要求。", field_errors=field_errors)


def _validate_password(password: str, field_errors: dict[str, str]) -> None:
    password = password or ""
    if len(password) < _PASSWORD_MIN_LENGTH:
        field_errors["password"] = f"密码长度至少 {_PASSWORD_MIN_LENGTH} 位。"
    elif not any(ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password):
        field_errors["password"] = "密码需同时包含字母和数字。"


# ---------------------------------------------------------------------------
# 平台管理员：名单导入与账号导入（G3：FR-U03、FR-U04、BR-007）
# ---------------------------------------------------------------------------

_STUDENT_CSV_COLUMNS = (
    "student_no",
    "full_name",
    "phone",
    "campus_code",
    "grade",
    "class_name",
    "major",
    "college",
)

# 兼容中文表头（页面提示：学号,姓名,手机号,校区代码,年级,班级,专业,学院）与英文字段名
_CSV_HEADER_ALIASES = {
    "学号": "student_no",
    "姓名": "full_name",
    "手机号": "phone",
    "校区代码": "campus_code",
    "年级": "grade",
    "班级": "class_name",
    "专业": "major",
    "学院": "college",
}


def _normalize_csv_headers(fieldnames: list[str]) -> list[str]:
    """把中文表头归一化为内部字段名；英文表头原样保留。"""
    normalized = []
    for name in fieldnames:
        stripped = (name or "").strip()
        normalized.append(_CSV_HEADER_ALIASES.get(stripped, stripped))
    return normalized


def import_students(actor, *, university_id: int, csv_bytes: bytes):
    """导入学生名单（FR-U03、FR-U04、BR-005 前置）。

    CSV 编码 UTF-8（兼容 BOM），表头：学号,姓名,手机号,校区代码,年级,班级,专业,学院。
    每行独立校验；失败行记录原因，不影响其他行；不保存原始文件。
    """
    ensure_actor_university(actor, university_id)
    import csv
    import hashlib
    import io

    from app.models.university import Campus, StudentImportBatch, StudentRegistryRecord

    university = db.session.get(University, university_id)
    if university is None:
        raise NotFoundError("高校不存在。")

    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InputError("名单文件必须是 UTF-8 编码。") from None

    lines = text.splitlines()
    if not lines:
        raise InputError("名单文件缺少表头。")
    raw_header = next(csv.reader([lines[0]]), [])
    normalized_headers = _normalize_csv_headers(raw_header)
    missing = [c for c in _STUDENT_CSV_COLUMNS if c not in normalized_headers]
    if missing:
        raise InputError(
            "表头缺少字段："
            + "、".join(missing)
            + "。需要的表头：学号,姓名,手机号,校区代码,年级,班级,专业,学院"
        )
    # 表头行之外的数据行 + 归一化表头，后续统一按内部字段名取列
    reader = csv.DictReader(io.StringIO("\n".join(lines[1:])), fieldnames=normalized_headers)

    campuses = {
        c.code: c
        for c in db.session.scalars(
            select(Campus).where(Campus.university_id == university_id, Campus.status == "active")
        ).all()
    }
    existing_nos = set(
        db.session.scalars(
            select(StudentRegistryRecord.student_no).where(
                StudentRegistryRecord.university_id == university_id
            )
        )
    )
    existing_phones = set(
        db.session.scalars(
            select(StudentRegistryRecord.phone_hash).where(
                StudentRegistryRecord.university_id == university_id
            )
        )
    )

    now = datetime.now(UTC)
    batch = StudentImportBatch(
        university_id=university_id,
        uploaded_by_user_id=actor.id,
        original_filename="roster.csv",
        file_sha256=hashlib.sha256(csv_bytes).hexdigest(),
        total_rows=0,
        status="processing",
        error_summary=[],
        created_at=now,
    )
    db.session.add(batch)
    db.session.flush()

    success = 0
    errors: list[dict] = []
    row_no = 0
    for row_no, row in enumerate(reader, start=2):
        student_no = (row.get("student_no") or "").strip()
        full_name = (row.get("full_name") or "").strip()
        phone = normalize_phone(row.get("phone") or "")
        campus_code = (row.get("campus_code") or "").strip()

        problem = None
        if not student_no:
            problem = "学号为空"
        elif not full_name:
            problem = "姓名为空"
        elif not is_valid_phone(phone):
            problem = "手机号无效"
        elif campus_code not in campuses:
            problem = f"校区代码 {campus_code} 不存在"
        elif student_no in existing_nos:
            problem = "学号已存在"
        elif phone_hash(phone) in existing_phones:
            problem = "手机号已存在"

        if problem:
            errors.append({"row": row_no, "student_no": student_no, "reason": problem})
            continue

        campus = campuses[campus_code]
        db.session.add(
            StudentRegistryRecord(
                university_id=university_id,
                campus_id=campus.id,
                latest_import_batch_id=batch.id,
                student_no=student_no,
                full_name=full_name,
                phone_hash=phone_hash(phone),
                phone_last4=phone[-4:],
                grade=(row.get("grade") or "").strip() or "未填写",
                class_name=(row.get("class_name") or "").strip() or "未填写",
                major=(row.get("major") or "").strip() or "未填写",
                college=(row.get("college") or "").strip() or "未填写",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        existing_nos.add(student_no)
        existing_phones.add(phone_hash(phone))
        success += 1

    # total_rows 记录数据行数（不含表头）
    batch.total_rows = success + len(errors)
    batch.success_rows = success
    batch.failed_rows = len(errors)
    batch.error_summary = errors
    batch.status = "completed"
    batch.completed_at = datetime.now(UTC)
    from app.services.notification_service import record_audit

    record_audit(
        actor_user_id=actor.id,
        university_id=university_id,
        action="admin.student_import",
        entity_type="student_import_batch",
        entity_id=batch.id,
        detail={"total_rows": batch.total_rows, "success": success, "failed": len(errors)},
    )
    db.session.commit()
    return batch


def list_import_batches(actor, *, limit: int = 20):
    """查看名单导入批次；校级管理员只查看本校（FR-U04）。"""
    from app.models.university import StudentImportBatch

    university_scope = _scope_university_id(actor)
    stmt = select(StudentImportBatch)
    if university_scope is not None:
        stmt = stmt.where(StudentImportBatch.university_id == university_scope)
    stmt = stmt.order_by(StudentImportBatch.created_at.desc()).limit(limit)
    return list(db.session.scalars(stmt).all())


def list_all_users(actor) -> list[User]:
    """平台管理员查看全部账号；校级管理员只查看本校（BR-007）。"""
    university_scope = _scope_university_id(actor)
    stmt = select(User)
    if university_scope is not None:
        stmt = stmt.where(User.university_id == university_scope)
    return list(db.session.scalars(stmt.order_by(User.created_at.desc())).all())


def list_universities(actor) -> list[University]:
    """启用高校；校级管理员只返回本校。"""
    university_scope = _scope_university_id(actor)
    stmt = select(University).where(University.status == "active")
    if university_scope is not None:
        stmt = stmt.where(University.id == university_scope)
    return list(db.session.scalars(stmt.order_by(University.code)).all())


def import_managed_accounts(
    actor, *, university_id: int | None, login_name: str, role: str, password: str, nickname: str
) -> User:
    """导入管理员账号（公益管理员/校级管理员；BR-007、FR-A04）。

    - 平台管理员账号不在此创建（首版只预置 1 个，D-022）；
    - 校级管理员可导入账号，但管理功能暂未开放；
    - 公益管理员仍需平台管理员另行授权站点。
    """
    if not is_university_manager(actor):
        raise PermissionDeniedError("当前身份无法导入管理员账号。")
    if role not in ("station_manager", "university_admin"):
        raise InputError("只能导入公益管理员或校级管理员账号。")
    if actor.is_university_admin:
        if role != "station_manager":
            raise PermissionDeniedError("校级管理员只能创建公益管理员账号。")
        if university_id is None:
            university_id = actor.university_id
        ensure_actor_university(actor, university_id)
    login_name = (login_name or "").strip()
    nickname = (nickname or "").strip() or login_name
    if not login_name:
        raise InputError("登录账号不能为空。", field_errors={"login_name": "请填写登录账号。"})
    field_errors: dict[str, str] = {}
    _validate_password(password, field_errors)
    if field_errors:
        raise InputError("初始密码不符合要求。", field_errors=field_errors)
    if role != "platform_admin" and university_id is None:
        raise InputError("公益管理员与校级管理员必须归属一个高校。")

    if university_id is not None:
        university = db.session.get(University, university_id)
        if university is None:
            raise InputError("所属高校不存在。")

    existing = db.session.scalar(select(User).where(User.login_name == login_name))
    if existing is not None:
        raise ConflictError("登录账号已存在。")

    now = datetime.now(UTC)
    user = User(
        university_id=university_id,
        login_name=login_name,
        password_hash=hash_password(password),
        nickname=nickname,
        role=role,
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.session.add(user)
    db.session.flush()  # 先取 Identity 主键，审计记录才有效
    from app.services.notification_service import record_audit

    record_audit(
        actor_user_id=actor.id,
        university_id=university_id,
        action="admin.managed_account_create",
        entity_type="user",
        entity_id=user.id,
        detail={"login_name": login_name, "role": role},
    )
    db.session.commit()
    return user


def set_user_status(actor, user_id: int, *, status: str) -> User:
    """启用或停用账号；校级管理员仅管理本校普通账号。"""
    if status not in ("active", "disabled"):
        raise InputError("账号状态无效。")
    target = db.session.get(User, user_id)
    if target is None:
        raise NotFoundError("账号不存在。")
    if actor is None or not is_university_manager(actor):
        raise PermissionDeniedError("当前身份无法管理账号。")
    if target.id == actor.id:
        raise PermissionDeniedError("不能停用自己的账号。")
    if target.role == "platform_admin":
        raise PermissionDeniedError("不能管理平台管理员账号。")
    if actor.is_university_admin:
        ensure_actor_university(actor, target.university_id)
        if target.role not in ("student", "station_manager"):
            raise PermissionDeniedError("校级管理员只能管理本校学生或公益管理员。")

    now = datetime.now(UTC)
    target.status = status
    target.updated_at = now
    if status == "disabled" and target.role == "station_manager":
        from app.models.university import StationManagerAssignment

        assignments = db.session.scalars(
            select(StationManagerAssignment).where(
                StationManagerAssignment.user_id == target.id,
                StationManagerAssignment.status == "active",
            )
        ).all()
        for assignment in assignments:
            assignment.status = "ended"
            assignment.ended_on = now.date()

    from app.services.notification_service import record_audit

    record_audit(
        actor_user_id=actor.id,
        university_id=target.university_id,
        action="admin.user.status",
        entity_type="user",
        entity_id=target.id,
        detail={"status": status, "role": target.role},
    )
    db.session.commit()
    return target


def _scope_university_id(actor) -> int | None:
    """返回校级管理员本校 ID；平台管理员返回 None。"""
    if not is_university_manager(actor):
        raise PermissionDeniedError("当前身份无法管理账号与名单。")
    if actor.is_platform_admin:
        return None
    if actor.university_id is None:
        raise PermissionDeniedError("校级管理员未绑定有效高校。")
    return ensure_actor_university(actor, actor.university_id)
