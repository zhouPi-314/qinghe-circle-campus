"""集成测试数据工厂：构造高校、校区、名单与账号。

仅在测试内使用；生产代码不引用本模块。
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.auth import phone_hash, phone_last4
from app.models.university import (
    Campus,
    StudentImportBatch,
    StudentRegistryRecord,
    University,
)
from app.models.user import User
from app.services.auth_service import hash_password


def now_utc() -> datetime:
    return datetime.now(UTC)


def create_university(code: str = "510001", name: str = "测试大学") -> University:
    uni = University(
        code=code,
        name=name,
        province="四川省",
        city="成都市",
        education_level="undergraduate",
        ownership="public",
        status="active",
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    db_add(uni)
    return uni


def create_campus(
    university: University, code: str = "MAIN", name: str = "主校区", is_primary: bool = True
) -> Campus:
    campus = Campus(
        university_id=university.id,
        code=code,
        name=name,
        is_primary=is_primary,
        verification_status="temporary",
        status="active",
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    db_add(campus)
    return campus


def create_platform_admin(login_name: str = "admin", password: str = "admin12345") -> User:
    user = User(
        login_name=login_name,
        password_hash=hash_password(password),
        nickname="平台管理员",
        role="platform_admin",
        status="active",
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    db_add(user)
    return user, password


def create_import_batch(university: University, uploader: User) -> StudentImportBatch:
    batch = StudentImportBatch(
        university_id=university.id,
        uploaded_by_user_id=uploader.id,
        original_filename="test-roster.csv",
        file_sha256="a" * 64,
        total_rows=1,
        success_rows=1,
        failed_rows=0,
        status="completed",
        created_at=now_utc(),
        completed_at=now_utc(),
    )
    db_add(batch)
    return batch


def create_registry_record(
    university: University,
    campus: Campus,
    batch: StudentImportBatch,
    *,
    student_no: str = "2024001",
    full_name: str = "张测试",
    phone: str = "13880001234",
    registered: bool = False,
) -> StudentRegistryRecord:
    record = StudentRegistryRecord(
        university_id=university.id,
        campus_id=campus.id,
        latest_import_batch_id=batch.id,
        student_no=student_no,
        full_name=full_name,
        phone_hash=phone_hash(phone),
        phone_last4=phone_last4(phone),
        grade="2024级",
        class_name="软件工程1班",
        major="软件工程",
        college="计算机学院",
        status="active",
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    db_add(record)
    if registered:
        user = User(
            university_id=university.id,
            campus_id=campus.id,
            student_no=student_no,
            phone_hash=record.phone_hash,
            password_hash=hash_password("already1"),
            nickname=full_name,
            role="student",
            status="active",
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        db_add(user)
        record.registered_user_id = user.id
    return record


def db_add(obj):
    from app import db

    db.session.add(obj)
    db.session.commit()
    return obj


def create_student_user(
    university: University,
    campus: Campus,
    *,
    student_no: str = "2024100",
    phone: str = "13900001111",
    password: str = "student1",
    nickname: str = "测试学生",
) -> User:
    """直接构造在校学生账号（测试用；真实注册走 auth_service）。"""
    user = User(
        university_id=university.id,
        campus_id=campus.id,
        student_no=student_no,
        phone_hash=phone_hash(phone),
        password_hash=hash_password(password),
        nickname=nickname,
        role="student",
        status="active",
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    db_add(user)
    return user


def create_category(slug: str = "books", name: str = "书籍教材"):
    from app.models.item import ItemCategory

    category = ItemCategory(
        slug=slug, name=name, display_order=10, is_active=True, created_at=now_utc()
    )
    db_add(category)
    return category


def create_station_manager_user(
    university: University,
    *,
    login_name: str = "station1",
    password: str = "station1",
    nickname: str = "站点管理员",
) -> User:
    """公益管理员账号（测试用；真实账号走 auth_service 导入）。"""
    user = User(
        university_id=university.id,
        login_name=login_name,
        password_hash=hash_password(password),
        nickname=nickname,
        role="station_manager",
        status="active",
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    db_add(user)
    return user


def create_station(
    university: University,
    campus: Campus,
    *,
    station_type: str = "mixed",
    name: str = "青禾回收站",
):
    from app.models.university import Station

    station = Station(
        university_id=university.id,
        campus_id=campus.id,
        name=name,
        station_type=station_type,
        address="学生活动中心西侧",
        status="active",
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    db_add(station)
    return station


def assign_manager(station, manager: User):
    from app.models.university import StationManagerAssignment

    assignment = StationManagerAssignment(
        university_id=station.university_id,
        station_id=station.id,
        user_id=manager.id,
        started_on=now_utc().date(),
        status="active",
        created_at=now_utc(),
    )
    db_add(assignment)
    return assignment


def create_item(
    owner: User,
    category_id: int,
    campus_id: int,
    *,
    mode: str = "borrow",
    title: str = "测试物品",
    description: str = "九成新",
    condition: str = "like_new",
    sale_price_cents: int | None = None,
):
    from app.models.item import Item

    item = Item(
        university_id=owner.university_id,
        campus_id=campus_id,
        owner_user_id=owner.id,
        category_id=category_id,
        mode=mode,
        title=title,
        description=description,
        condition=condition,
        sale_price_cents=sale_price_cents,
        status="active",
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    db_add(item)
    return item
