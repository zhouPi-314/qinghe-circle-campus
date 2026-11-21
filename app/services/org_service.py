"""校园组织 Service（G1 最小范围）。

交接书第 7 节接口 get_organization_tree() 的首版实现；
组织维护接口（list_universities / create_university 等）随 G2 增量实现。

权限规则（工程标准第 5 节）：本模块接口在 service 层再次校验角色；
平台管理员（university_id 为空）可跨高校查看基础组织数据。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app import db
from app.core.errors import ConflictError, InputError, PermissionDeniedError
from app.core.permissions import ensure_actor_university, is_university_manager
from app.models.university import (
    Campus,
    Station,
    StationManagerAssignment,
    University,
)
from app.models.user import User
from app.services.notification_service import record_audit

if TYPE_CHECKING:
    from app.core.permissions import CurrentUser


def get_organization_tree(actor: CurrentUser | None) -> dict:
    """管理员概览：平台管理员全局，校级管理员仅本校（FR-M01）。

    actor 必须是平台管理员或校级管理员；其他角色或未登录调用一律拒绝。
    """
    if not is_university_manager(actor):
        raise PermissionDeniedError("当前身份无法查看管理概览。")
    university_scope = _scope_university_id(actor)

    from app.models.charity import CharityProject
    from app.models.circulation import CirculationRequest
    from app.models.item import Item

    def scoped_count(model) -> int:
        stmt = select(func.count()).select_from(model)
        if university_scope is not None:
            stmt = stmt.where(model.university_id == university_scope)
        return db.session.scalar(stmt) or 0

    counts = {
        "universities": 1
        if university_scope is not None
        else db.session.scalar(select(func.count()).select_from(University)) or 0,
        "campuses": scoped_count(Campus),
        "users": scoped_count(User),
        "stations": scoped_count(Station),
        "items": scoped_count(Item),
        "requests": scoped_count(CirculationRequest),
        "projects": scoped_count(CharityProject),
    }

    university_stmt = select(University)
    campus_stmt = select(Campus)
    if university_scope is not None:
        university_stmt = university_stmt.where(University.id == university_scope)
        campus_stmt = campus_stmt.where(Campus.university_id == university_scope)
    universities = db.session.scalars(university_stmt.order_by(University.code)).all()
    campuses = db.session.execute(
        campus_stmt.order_by(Campus.university_id, Campus.is_primary.desc(), Campus.id)
    ).all()

    campuses_by_university: dict[int, list[str]] = {}
    for (campus,) in campuses:
        campuses_by_university.setdefault(campus.university_id, []).append(campus.name)

    tree = [
        {
            "code": uni.code,
            "name": uni.name,
            "city": uni.city,
            "campuses": campuses_by_university.get(uni.id, []),
        }
        for uni in universities
    ]
    return {"counts": counts, "universities": tree}


# ---------------------------------------------------------------------------
# 站点与授权（G3：FR-U02、FR-M03 的组织部分）
# ---------------------------------------------------------------------------


def create_campus(
    actor,
    *,
    university_id: int,
    code: str,
    name: str,
    address: str | None = None,
    is_primary: bool = False,
) -> Campus:
    """平台管理员或本校校级管理员维护校区（FR-U02）。"""
    ensure_actor_university(actor, university_id)
    code = (code or "").strip()
    name = (name or "").strip()
    if not code or not name:
        raise InputError("校区代码与名称不能为空。")
    existing = db.session.scalar(
        select(Campus).where(Campus.university_id == university_id, Campus.code == code)
    )
    if existing is not None:
        raise ConflictError("该校已存在同代码校区。")
    now = datetime.now(UTC)
    campus = Campus(
        university_id=university_id,
        code=code,
        name=name,
        address=address,
        is_primary=is_primary,
        verification_status="official",
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.session.add(campus)
    db.session.flush()  # 先取 Identity 主键，审计记录才有效
    record_audit(
        actor_user_id=actor.id,
        university_id=university_id,
        action="org.campus.create",
        entity_type="campus",
        entity_id=campus.id,
        detail={"code": code, "name": name},
    )
    db.session.commit()
    return campus


def create_station(
    actor,
    *,
    campus_id: int,
    name: str,
    station_type: str,
    address: str,
    service_hours: str | None = None,
) -> Station:
    """平台管理员或本校校级管理员创建回收/公益站点（FR-U02）。"""
    campus = db.session.get(Campus, campus_id)
    if campus is None or campus.status != "active":
        raise InputError("所选校区无效。")
    university_id = ensure_actor_university(actor, campus.university_id)
    name = (name or "").strip()
    address = (address or "").strip()
    if not name or not address:
        raise InputError("站点名称与地址不能为空。")
    if station_type not in ("recycle", "charity", "mixed"):
        raise InputError("站点类型无效。")
    now = datetime.now(UTC)
    station = Station(
        university_id=university_id,
        campus_id=campus_id,
        name=name,
        station_type=station_type,
        address=address,
        service_hours=service_hours,
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.session.add(station)
    db.session.flush()  # 先取 Identity 主键，审计记录才有效
    record_audit(
        actor_user_id=actor.id,
        university_id=university_id,
        action="org.station.create",
        entity_type="station",
        entity_id=station.id,
        detail={"name": name, "station_type": station_type},
    )
    db.session.commit()
    return station


def assign_station_manager(
    actor, *, station_id: int, user_id: int, started_on
) -> StationManagerAssignment:
    """平台管理员或本校校级管理员授权公益管理员站点（BR-007、FR-M03）。

    同一账号同一站点只能有一条有效授权（数据库唯一索引兜底）。
    """
    station = db.session.get(Station, station_id)
    if station is None or station.status != "active":
        raise InputError("站点不存在或已停用。")
    ensure_actor_university(actor, station.university_id)
    user = db.session.get(User, user_id)
    if user is None or user.status != "active":
        raise InputError("账号不存在或已停用。")
    if user.university_id != station.university_id:
        raise ConflictError("不能把站点授权给其他学校的账号（BR-002）。")
    if user.role != "station_manager":
        raise ConflictError("只能授权公益管理员角色账号。")
    existing = db.session.scalar(
        select(StationManagerAssignment).where(
            StationManagerAssignment.station_id == station_id,
            StationManagerAssignment.user_id == user_id,
            StationManagerAssignment.status == "active",
        )
    )
    if existing is not None:
        raise ConflictError("该账号已在此站点持有有效授权。")
    assignment = StationManagerAssignment(
        university_id=station.university_id,
        station_id=station_id,
        user_id=user_id,
        started_on=started_on,
        status="active",
        created_at=datetime.now(UTC),
    )
    db.session.add(assignment)
    db.session.flush()
    record_audit(
        actor_user_id=actor.id,
        university_id=station.university_id,
        action="org.station.assign_manager",
        entity_type="station",
        entity_id=station_id,
        detail={"user_id": user_id},
    )
    db.session.commit()
    return assignment


def manager_scope(actor) -> list[Station]:
    """公益管理员被授权的站点（BR-007、FR-M03）。"""
    if actor.role != "station_manager":
        return []
    stmt = (
        select(Station)
        .join(StationManagerAssignment, StationManagerAssignment.station_id == Station.id)
        .where(
            StationManagerAssignment.user_id == actor.id,
            StationManagerAssignment.status == "active",
            Station.status == "active",
        )
        .order_by(Station.id)
    )
    return list(db.session.scalars(stmt).all())


def list_all_universities(actor) -> list[University]:
    """平台管理员查看全部高校；校级管理员只查看本校。"""
    university_scope = _scope_university_id(actor)
    stmt = select(University)
    if university_scope is not None:
        stmt = stmt.where(University.id == university_scope)
    return list(db.session.scalars(stmt.order_by(University.code)).all())


def list_all_stations(actor) -> list[Station]:
    """平台管理员查看全部站点；校级管理员只查看本校。"""
    university_scope = _scope_university_id(actor)
    stmt = select(Station)
    if university_scope is not None:
        stmt = stmt.where(Station.university_id == university_scope)
    return list(db.session.scalars(stmt.order_by(Station.university_id, Station.id)).all())


def list_campuses(actor) -> list[Campus]:
    """平台管理员查看全部校区；校级管理员只查看本校。"""
    university_scope = _scope_university_id(actor)
    stmt = select(Campus)
    if university_scope is not None:
        stmt = stmt.where(Campus.university_id == university_scope)
    return list(db.session.scalars(stmt.order_by(Campus.university_id, Campus.id)).all())


def list_station_managers(actor) -> list[User]:
    """平台管理员查看全部公益管理员；校级管理员只查看本校。"""
    university_scope = _scope_university_id(actor)
    stmt = select(User).where(User.role == "station_manager")
    if university_scope is not None:
        stmt = stmt.where(User.university_id == university_scope)
    return list(db.session.scalars(stmt.order_by(User.login_name)).all())


def list_stations_for(actor, *, station_types: tuple[str, ...]) -> list[Station]:
    """本校启用站点（按类型过滤）：回收申请、捐赠与回执表单下拉。"""
    stmt = select(Station).where(
        Station.university_id == actor.university_id,
        Station.status == "active",
        Station.station_type.in_(station_types),
    )
    return list(db.session.scalars(stmt.order_by(Station.id)).all())


def create_university(
    actor,
    *,
    code: str,
    name: str,
    province: str,
    city: str,
    education_level: str,
    ownership: str,
) -> University:
    """平台管理员新增高校（FR-U02）。"""
    _require_platform_admin(actor)
    code = (code or "").strip()
    name = (name or "").strip()
    if not code or not name:
        raise InputError("高校代码与名称不能为空。")
    # 与 sql/schema.sql CHECK 约束一致：education_level/ownership 枚举不新增值（G4 加固）
    if education_level not in ("undergraduate", "college"):
        raise InputError("办学层次无效。")
    if ownership not in ("public", "private"):
        raise InputError("办学性质无效。")
    existing = db.session.scalar(select(University).where(University.code == code))
    if existing is not None:
        raise ConflictError("已存在同代码高校。")
    now = datetime.now(UTC)
    university = University(
        code=code,
        name=name,
        province=(province or "").strip() or "四川省",
        city=(city or "").strip() or "未知城市",
        education_level=education_level,
        ownership=ownership,
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.session.add(university)
    db.session.flush()  # 先取 Identity 主键，审计记录才有效
    record_audit(
        actor_user_id=actor.id,
        university_id=None,
        action="org.university.create",
        entity_type="university",
        entity_id=university.id,
        detail={"code": code, "name": name},
    )
    db.session.commit()
    return university


def update_university(actor, university_id: int, *, fields: dict) -> University:
    """平台管理员维护高校基础信息（FR-U02）：名称、城市、状态。"""
    _require_platform_admin(actor)
    university = db.session.get(University, university_id)
    if university is None:
        raise InputError("高校不存在。")
    allowed = {"name", "city", "status"}
    unknown = set(fields) - allowed
    if unknown:
        raise InputError("包含不可修改的字段。")
    if "name" in fields:
        name = fields["name"].strip()
        if not name:
            raise InputError("高校名称不能为空。")
        university.name = name
    if "city" in fields and fields["city"].strip():
        university.city = fields["city"].strip()
    if "status" in fields:
        if fields["status"] not in ("active", "inactive"):
            raise InputError("状态无效。")
        university.status = fields["status"]
    university.updated_at = datetime.now(UTC)
    record_audit(
        actor_user_id=actor.id,
        university_id=university.id,
        action="org.university.update",
        entity_type="university",
        entity_id=university.id,
        detail={k: str(v) for k, v in fields.items() if k in allowed},
    )
    db.session.commit()
    return university


def _require_platform_admin(actor) -> None:
    if actor is None or not actor.is_platform_admin:
        raise PermissionDeniedError("只有平台管理员可以执行该操作。")


def _scope_university_id(actor) -> int | None:
    """返回校级管理员的本校 ID；平台管理员返回 None 表示全局。"""
    if not is_university_manager(actor):
        raise PermissionDeniedError("当前身份无法管理学校数据。")
    if actor.is_platform_admin:
        return None
    if actor.university_id is None:
        raise PermissionDeniedError("校级管理员未绑定有效高校。")
    return ensure_actor_university(actor, actor.university_id)
