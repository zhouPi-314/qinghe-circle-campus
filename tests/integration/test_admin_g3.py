"""集成测试：G3 退回修复项验证。

- 平台管理员高校维护（FR-U02）+ 写操作审计；
- 学生名单导入兼容中文表头（与页面提示一致）；
- 强制下架按 BR-043：有进行中业务 → 异常冻结，无业务 → 真正下架，历史如实；
- 站点类型校验：回收物资不能进纯公益站点，捐赠不能进纯回收站点。
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest

from tests.fixtures.helpers import (
    assign_manager,
    create_campus,
    create_category,
    create_item,
    create_platform_admin,
    create_station,
    create_station_manager_user,
    create_student_user,
    create_university,
)

pytestmark = pytest.mark.integration

from app import db  # noqa: E402
from app.core.errors import ConflictError, InputError, PermissionDeniedError  # noqa: E402
from app.core.permissions import to_current_user  # noqa: E402
from app.models.governance import AuditLog  # noqa: E402
from app.models.university import Campus, University  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import (  # noqa: E402
    auth_service,
    charity_service,
    circulation_service,
    item_service,
    org_service,  # noqa: E402
)


@pytest.fixture
def admin_world(app):
    with app.app_context():
        uni = create_university()
        campus = create_campus(uni)
        admin, _ = create_platform_admin()
        student = create_student_user(
            uni, campus, student_no="2024601", nickname="普通学生", phone="13900006001"
        )
        category = create_category(slug="misc", name="其他")
        db.session.commit()
        yield {
            "university_id": uni.id,
            "campus_id": campus.id,
            "admin_id": admin.id,
            "student_id": student.id,
            "category_id": category.id,
        }


def _actor(app, user_id):
    with app.app_context():
        return to_current_user(db.session.get(User, user_id))


class TestUniversityManagement:
    def test_create_university_writes_audit(self, app, admin_world):
        with app.app_context():
            admin = _actor(app, admin_world["admin_id"])
            uni = org_service.create_university(
                admin,
                code="590001",
                name="新建测试大学",
                province="四川省",
                city="绵阳市",
                education_level="undergraduate",
                ownership="public",
            )
            assert uni.status == "active"
            audit = db.session.query(AuditLog).filter_by(action="org.university.create").one()
            assert audit.entity_id == uni.id

        # 新高校可被选中（启用状态）
        with app.app_context():
            uni = db.session.get(University, uni.id)
            assert uni.status == "active"

    def test_duplicate_code_rejected(self, app, admin_world):
        with app.app_context():
            admin = _actor(app, admin_world["admin_id"])
            with pytest.raises(ConflictError):
                org_service.create_university(
                    admin,
                    code="510001",  # world 里已用
                    name="重复代码大学",
                    province="四川省",
                    city="成都市",
                    education_level="undergraduate",
                    ownership="public",
                )

    def test_student_cannot_manage_university(self, app, admin_world):
        with app.app_context():
            student = _actor(app, admin_world["student_id"])
            with pytest.raises(PermissionDeniedError):
                org_service.create_university(
                    student,
                    code="590002",
                    name="越权大学",
                    province="四川省",
                    city="成都市",
                    education_level="undergraduate",
                    ownership="public",
                )

    def test_update_university_fields(self, app, admin_world):
        with app.app_context():
            admin = _actor(app, admin_world["admin_id"])
            uni = org_service.update_university(
                admin, admin_world["university_id"], fields={"city": "宜宾市", "status": "active"}
            )
            assert uni.city == "宜宾市"
            db.session.query(AuditLog).filter_by(action="org.university.update").one()


class TestRosterImportChineseHeader:
    def test_import_with_chinese_headers(self, app, admin_world):
        """页面提示的中文表头可以直接导入（修复：服务端曾只认英文表头）。"""
        campus = None
        with app.app_context():
            from app.models.university import Campus

            campus = db.session.get(Campus, admin_world["campus_id"])
            campus_code = campus.code
            csv_text = (
                "学号,姓名,手机号,校区代码,年级,班级,专业,学院\n"
                f"2024711,陈测试,13800007111,{campus_code},2024级,软工1班,软件工程,计算机学院\n"
                f"2024712,周测试,13800007122,{campus_code},2024级,软工1班,软件工程,计算机学院\n"
            )
            admin = _actor(app, admin_world["admin_id"])
            batch = auth_service.import_students(
                admin,
                university_id=admin_world["university_id"],
                csv_bytes=csv_text.encode("utf-8"),
            )
            assert batch.status == "completed"
            assert batch.total_rows == 2
            assert batch.success_rows == 2
            assert batch.failed_rows == 0

        # 英文表头依然兼容
        with app.app_context():
            csv_text = (
                "student_no,full_name,phone,campus_code,grade,class_name,major,college\n"
                f"2024713,吴测试,13800007133,{campus_code},2024级,软工1班,软件工程,计算机学院\n"
            )
            admin = _actor(app, admin_world["admin_id"])
            batch = auth_service.import_students(
                admin,
                university_id=admin_world["university_id"],
                csv_bytes=csv_text.encode("utf-8"),
            )
            assert batch.success_rows == 1

    def test_import_writes_audit(self, app, admin_world):
        with app.app_context():
            from app.models.university import Campus

            campus = db.session.get(Campus, admin_world["campus_id"])
            csv_text = (
                "学号,姓名,手机号,校区代码,年级,班级,专业,学院\n"
                f"2024721,郑测试,13800007211,{campus.code},2024级,软工1班,软件工程,计算机学院\n"
            )
            admin = _actor(app, admin_world["admin_id"])
            batch = auth_service.import_students(
                admin,
                university_id=admin_world["university_id"],
                csv_bytes=csv_text.encode("utf-8"),
            )
            audit = db.session.query(AuditLog).filter_by(action="admin.student_import").one()
            assert audit.entity_id == batch.id


class TestForceOffShelf:
    def test_force_off_shelf_without_active_request(self, app, admin_world):
        """无进行中业务：真正下架（BR-043）。"""
        with app.app_context():
            student = db.session.get(User, admin_world["student_id"])
            item = create_item(student, admin_world["category_id"], admin_world["campus_id"])
            item_id = item.id
        with app.app_context():
            admin = _actor(app, admin_world["admin_id"])
            updated = item_service.change_item_shelf_state(
                admin, item_id, action="force_off_shelf", reason="描述违规"
            )
            assert updated.status == "off_shelf"
            assert updated.moderation_status == "hidden"
            history = item_service.item_history(updated)
            assert history[0].from_status == "active"
            assert history[0].to_status == "off_shelf"

    def test_force_freeze_with_active_request(self, app, admin_world):
        """存在进行中业务：进入异常冻结 on_hold（BR-043），历史不伪造。"""
        from datetime import date

        from tests.fixtures.helpers import create_student_user

        with app.app_context():
            uni = db.session.get(University, admin_world["university_id"])
            borrower = create_student_user(
                uni, uni.campuses[0], student_no="2024602", phone="13900006002"
            )
            borrower_id = borrower.id
        with app.app_context():
            student = db.session.get(User, admin_world["student_id"])
            item = create_item(student, admin_world["category_id"], admin_world["campus_id"])
            item_id = item.id
        with app.app_context():
            borrower = _actor(app, borrower_id)
            circulation_service.request_borrow(
                borrower,
                item_id,
                start_date=date(2026, 12, 1),
                due_date=date(2026, 12, 8),
            )
        with app.app_context():
            admin = _actor(app, admin_world["admin_id"])
            updated = item_service.change_item_shelf_state(
                admin, item_id, action="force_off_shelf", reason="交易异常"
            )
            assert updated.status == "on_hold"
            history = item_service.item_history(updated)
            assert history[0].from_status == "reserved"
            assert history[0].to_status == "on_hold"
            assert "异常冻结" in history[0].reason


class TestStationTypeGuards:
    @pytest.fixture
    def station_world(self, app, admin_world):
        from app.models.university import Campus

        with app.app_context():
            uni = db.session.get(University, admin_world["university_id"])
            campus = db.session.get(Campus, admin_world["campus_id"])
            recycle_station = create_station(uni, campus, station_type="recycle", name="纯回收站")
            charity_station = create_station(uni, campus, station_type="charity", name="纯公益站")
            manager = create_station_manager_user(uni, login_name="mgrt1")
            assign_manager(charity_station, manager)
            assign_manager(recycle_station, manager)
            db.session.commit()
            yield {
                **admin_world,
                "recycle_station_id": recycle_station.id,
                "charity_station_id": charity_station.id,
                "manager_id": manager.id,
            }

    def test_recycle_cannot_use_charity_only_station(self, app, station_world):
        """回收物资不能进入纯公益站点（BR-029）。"""
        with app.app_context():
            student = db.session.get(User, station_world["student_id"])
            item = create_item(
                student,
                station_world["category_id"],
                station_world["campus_id"],
                mode="recycle",
            )
            item_id = item.id
        with app.app_context():
            owner = _actor(app, station_world["student_id"])
            start = datetime(2026, 12, 5, 10, 0, tzinfo=UTC)
            with pytest.raises(InputError):
                circulation_service.request_recycle(
                    owner,
                    item_id,
                    station_id=station_world["charity_station_id"],
                    preferred_start_at=start,
                    preferred_end_at=start + timedelta(hours=1),
                )

    def test_donation_cannot_use_recycle_only_station(self, app, station_world):
        """捐赠物资不能进入纯回收站点（FR-C02）。"""
        with app.app_context():
            manager = _actor(app, station_world["manager_id"])
            project = charity_service.create_project(
                manager,
                title="站点类型测试项目",
                description="x",
                recipient_org="x",
                public_summary="x",
                deadline=datetime.now(UTC) + timedelta(days=7),
                needs=[
                    {
                        "item_category_id": station_world["category_id"],
                        "item_name": "测试物资",
                        "target_quantity": 10,
                    }
                ],
            )
            project_id = project.id
            need_id = project.needs[0].id
        with app.app_context():
            donor = _actor(app, station_world["student_id"])
            with pytest.raises(InputError):
                charity_service.submit_donation(
                    donor,
                    project_id,
                    station_id=station_world["recycle_station_id"],
                    items=[{"need_id": need_id, "quantity": 1, "condition": "good"}],
                )

    def test_recycle_accepts_recycle_station(self, app, station_world):
        """回收进入 recycle 站点正常创建。"""
        item_id = _recycle_item(app, station_world)
        with app.app_context():
            owner = _actor(app, station_world["student_id"])
            start = datetime(2026, 12, 5, 10, 0, tzinfo=UTC)
            request = circulation_service.request_recycle(
                owner,
                item_id,
                station_id=station_world["recycle_station_id"],
                preferred_start_at=start,
                preferred_end_at=start + timedelta(hours=1),
            )
            assert request.status == "pending"


def _recycle_item(app, world) -> int:
    with app.app_context():
        student = db.session.get(User, world["student_id"])
        item = create_item(
            student, world["category_id"], world["campus_id"], mode="recycle", title="待回收物"
        )
        return item.id


class TestHttpRenderSmoke:
    """新增页面/模板 HTTP 冒烟：模板缺失或变量未传会直接 500。"""

    def _login(self, client, role, identifier, password):
        from tests.integration.test_register_and_login import get_csrf_token

        page = client.get("/auth/identity").get_data(as_text=True)
        client.post(
            "/auth/identity",
            data={"csrf_token": get_csrf_token(page), "role": role},
            follow_redirects=True,
        )
        if role == "student":
            # 学生登录前必须选择学校与校区（测试库一所高校，取第一组选项）
            page = client.get("/auth/student-context").get_data(as_text=True)
            uni_id = re.search(r'name="university_id".*?value="(\d+)"', page, re.DOTALL).group(1)
            campus_id = re.search(r'name="campus_id".*?value="(\d+)"', page, re.DOTALL).group(1)
            client.post(
                "/auth/student-context",
                data={
                    "csrf_token": get_csrf_token(page),
                    "university_id": uni_id,
                    "campus_id": campus_id,
                },
                follow_redirects=True,
            )
        page = client.get("/auth/login").get_data(as_text=True)
        client.post(
            "/auth/login",
            data={
                "csrf_token": get_csrf_token(page),
                "identifier": identifier,
                "password": password,
            },
            follow_redirects=True,
        )

    def test_admin_organizations_renders(self, client, app, admin_world):
        self._login(client, "platform_admin", "admin", "admin12345")
        resp = client.get("/admin/organizations")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "新增高校" in html and "创建校区" in html

    def test_new_project_page_renders(self, client, app, admin_world):
        with app.app_context():
            uni = db.session.get(University, admin_world["university_id"])
            from tests.fixtures.helpers import (
                assign_manager,
                create_station,
                create_station_manager_user,
            )

            manager = create_station_manager_user(uni, login_name="mgrsmoke")
            station = create_station(
                uni, db.session.get(Campus, admin_world["campus_id"]), name="冒烟站点"
            )
            assign_manager(station, manager)
        from tests.integration.test_register_and_login import get_csrf_token

        page = client.get("/", follow_redirects=True).get_data(as_text=True)
        client.post(
            "/auth/logout",
            data={"csrf_token": get_csrf_token(page)},
            follow_redirects=True,
        )
        self._login(client, "station_manager", "mgrsmoke", "station1")
        resp = client.get("/charity/projects/new")
        assert resp.status_code == 200
        assert "创建公益项目" in resp.get_data(as_text=True)

    def test_donate_page_renders_with_form(self, client, app, admin_world):
        with app.app_context():
            uni = db.session.get(University, admin_world["university_id"])
            campus = db.session.get(Campus, admin_world["campus_id"])
            from tests.fixtures.helpers import (
                assign_manager,
                create_station,
                create_station_manager_user,
            )

            manager = create_station_manager_user(uni, login_name="mgrsmoke2")
            station = create_station(uni, campus, station_type="charity", name="冒烟公益站")
            assign_manager(station, manager)
            project = charity_service.create_project(
                _actor(app, manager.id),
                title="冒烟测试项目",
                description="d",
                recipient_org="o",
                public_summary="s",
                deadline=datetime.now(UTC) + timedelta(days=7),
                needs=[
                    {
                        "item_category_id": admin_world["category_id"],
                        "item_name": "旧书",
                        "target_quantity": 5,
                    }
                ],
            )
            project_id = project.id
        # 学生登录后访问捐赠页（此前模板缺失会 500）
        self._login(client, "student", "2024601", "student1")
        resp = client.get(f"/charity/{project_id}/donate")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "提交实物捐赠" in html and "旧书" in html

    def test_recycle_owner_sees_submission_form(self, client, app, admin_world):
        """物主发起回收时，详情页必须显示站点与送达时段表单。"""
        with app.app_context():
            student = db.session.get(User, admin_world["student_id"])
            item = create_item(
                student,
                admin_world["category_id"],
                admin_world["campus_id"],
                mode="recycle",
                title="待回收台灯",
            )
            item_id = item.id

        self._login(client, "student", "2024601", "student1")
        resp = client.get(f"/items/{item_id}")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "提交回收申请" in html
        assert 'name="station_id"' in html

    def test_recycle_owner_sees_handover_code_action(self, client, app, admin_world):
        """回收由物主出码：进入待交接后，物主页面必须显示生成交接码按钮。"""
        with app.app_context():
            from tests.fixtures.helpers import (
                assign_manager,
                create_station,
                create_station_manager_user,
            )

            uni = db.session.get(University, admin_world["university_id"])
            campus = db.session.get(Campus, admin_world["campus_id"])
            manager = create_station_manager_user(uni, login_name="g4route")
            station = create_station(uni, campus, station_type="recycle")
            assign_manager(station, manager)
            student = db.session.get(User, admin_world["student_id"])
            item = create_item(
                student,
                admin_world["category_id"],
                admin_world["campus_id"],
                mode="recycle",
                title="待交接回收物品",
            )
            start = datetime.now(UTC) + timedelta(days=1)
            request = circulation_service.request_recycle(
                _actor(app, student.id),
                item.id,
                station_id=station.id,
                preferred_start_at=start,
                preferred_end_at=start + timedelta(hours=1),
            )
            request_id = request.id
            manager_id = manager.id
        with app.app_context():
            circulation_service.decide_request(
                _actor(app, manager_id),
                request_id,
                decision="accept",
            )

        self._login(client, "student", "2024601", "student1")
        resp = client.get(f"/requests/{request_id}")
        assert resp.status_code == 200
        assert "生成交接码" in resp.get_data(as_text=True)
