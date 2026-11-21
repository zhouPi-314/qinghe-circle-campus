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

from datetime import UTC, datetime

from sqlalchemy import select

from app import db
from app.core.auth import is_valid_phone, normalize_phone, phone_hash
from app.core.errors import ConflictError, InputError, NotFoundError, PermissionDeniedError
from app.models.university import Campus, StudentRegistryRecord, University
from app.models.user import User

_PASSWORD_MIN_LENGTH = 8


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


def register_student(
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
    if not actor.is_platform_admin:
        raise PermissionDeniedError("只有平台管理员可以导入学生名单。")
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
    """平台管理员查看名单导入批次（FR-U04）。"""
    if not actor.is_platform_admin:
        raise PermissionDeniedError("只有平台管理员可以查看导入批次。")
    from app.models.university import StudentImportBatch

    stmt = select(StudentImportBatch).order_by(StudentImportBatch.created_at.desc()).limit(limit)
    return list(db.session.scalars(stmt).all())


def list_all_users(actor) -> list[User]:
    """平台管理员查看全部账号（BR-007 账号管理页）。"""
    if not actor.is_platform_admin:
        raise PermissionDeniedError("只有平台管理员可以查看账号列表。")
    return list(db.session.scalars(select(User).order_by(User.created_at.desc())).all())


def list_universities(actor) -> list[University]:
    """启用高校（管理页下拉；service 层复验平台管理员）。"""
    if not actor.is_platform_admin:
        raise PermissionDeniedError("只有平台管理员可以查看高校列表。")
    return list(
        db.session.scalars(
            select(University)
            .where(University.status == "active")
            .order_by(University.code)
        ).all()
    )


def import_managed_accounts(
    actor, *, university_id: int | None, login_name: str, role: str, password: str, nickname: str
) -> User:
    """导入管理员账号（公益管理员/校级管理员；BR-007、FR-A04）。

    - 平台管理员账号不在此创建（首版只预置 1 个，D-022）；
    - 校级管理员为预留身份，可导入账号但不开放管理功能；
    - 公益管理员仍需平台管理员另行授权站点。
    """
    if not actor.is_platform_admin:
        raise PermissionDeniedError("只有平台管理员可以导入管理员账号。")
    if role not in ("station_manager", "university_admin"):
        raise InputError("只能导入公益管理员或校级管理员（预留）账号。")
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
