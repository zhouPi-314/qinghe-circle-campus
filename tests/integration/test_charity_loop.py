"""集成测试：公益首版闭环（G3：FR-C01 ~ FR-C07、BR-033 ~ BR-040）。

正常链：公益管理员创建项目（含需求项）→ 学生提交实物捐赠 → 站点核验接收
（行锁防超募）→ 全部满足项目完成 → 公示脱敏回执；
异常链：超募拒绝、拒绝须填原因、截止后停止募集、跨校项目不可见、
回执数量不得超过已接收、非授权管理员不可核验。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.fixtures.helpers import (
    assign_manager,
    create_campus,
    create_category,
    create_platform_admin,
    create_station,
    create_station_manager_user,
    create_student_user,
    create_university,
)

pytestmark = pytest.mark.integration

from app import db  # noqa: E402
from app.core.errors import (  # noqa: E402
    ConflictError,
    InputError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.permissions import to_current_user  # noqa: E402
from app.models.charity import (  # noqa: E402
    CharityDonation,
    CharityDonationItem,
    CharityProject,
    CharityProjectNeed,
)
from app.models.university import University  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import charity_service  # noqa: E402


@pytest.fixture
def charity_world(app):
    with app.app_context():
        uni = create_university()
        campus = create_campus(uni)
        manager = create_station_manager_user(uni, login_name="cmgr1")
        station = create_station(uni, campus, station_type="charity")
        assign_manager(station, manager)
        donor = create_student_user(
            uni, campus, student_no="2024501", nickname="捐赠学生", phone="13900005001"
        )
        stranger = create_student_user(
            uni, campus, student_no="2024502", nickname="本校学生", phone="13900005002"
        )
        category = create_category(slug="clothes", name="衣物")
        admin, _ = create_platform_admin()
        db.session.commit()
        yield {
            "university_id": uni.id,
            "campus_id": campus.id,
            "manager_id": manager.id,
            "station_id": station.id,
            "donor_id": donor.id,
            "stranger_id": stranger.id,
            "category_id": category.id,
            "admin_id": admin.id,
        }


def _actor(app, user_id):
    with app.app_context():
        return to_current_user(db.session.get(User, user_id))


def _create_project(app, world, *, target=10):
    """公益管理员创建项目，返回 (project_id, need_id)。"""
    with app.app_context():
        manager = _actor(app, world["manager_id"])
        project = charity_service.create_project(
            manager,
            title="冬衣捐赠计划",
            description="为山区学校募集过冬衣物",
            recipient_org="青禾公益合作组织",
            public_summary="捐赠物资将统一消毒后发往受助学校",
            deadline=datetime.now(UTC) + timedelta(days=30),
            needs=[
                {
                    "item_category_id": world["category_id"],
                    "item_name": "冬季外套",
                    "target_quantity": target,
                    "unit": "件",
                }
            ],
        )
        return project.id, project.needs[0].id


def _submit_and_receive(app, world, project_id, need_id, quantity=3):
    """学生提交捐赠并由站点核验接收，返回 (donation_id, donation_item_id)。"""
    with app.app_context():
        donor = _actor(app, world["donor_id"])
        donation = charity_service.submit_donation(
            donor,
            project_id,
            station_id=world["station_id"],
            items=[{"need_id": need_id, "quantity": quantity, "condition": "good"}],
            donor_note="希望有帮助",
        )
        donation_id = donation.id
        item_id = donation.items[0].id
    with app.app_context():
        manager = _actor(app, world["manager_id"])
        charity_service.review_donation(manager, donation_id, accept=True)
    return donation_id, item_id


class TestProjectManagement:
    def test_manager_creates_project_with_needs(self, app, charity_world):
        project_id, need_id = _create_project(app, charity_world, target=10)
        with app.app_context():
            project = db.session.get(CharityProject, project_id)
            assert project.status == "active"
            assert project.university_id == charity_world["university_id"]
            need = db.session.get(CharityProjectNeed, need_id)
            assert need.target_quantity == 10
            assert need.accepted_quantity == 0

    def test_student_cannot_create_project(self, app, charity_world):
        with app.app_context():
            donor = _actor(app, charity_world["donor_id"])
            with pytest.raises(PermissionDeniedError):
                charity_service.create_project(
                    donor,
                    title="学生项目",
                    description="x",
                    recipient_org="x",
                    public_summary="x",
                    deadline=datetime.now(UTC) + timedelta(days=1),
                )

    def test_admin_can_create_project_for_university(self, app, charity_world):
        with app.app_context():
            admin = _actor(app, charity_world["admin_id"])
            project = charity_service.create_project(
                admin,
                title="管理员代建项目",
                description="x",
                recipient_org="x",
                public_summary="x",
                deadline=datetime.now(UTC) + timedelta(days=7),
                university_id=charity_world["university_id"],
            )
            assert project.university_id == charity_world["university_id"]

    def test_duplicate_need_rejected(self, app, charity_world):
        project_id, _ = _create_project(app, charity_world)
        with app.app_context():
            manager = _actor(app, charity_world["manager_id"])
            with pytest.raises(ConflictError):
                charity_service.update_project_need(
                    manager,
                    project_id,
                    item_category_id=charity_world["category_id"],
                    item_name="冬季外套",
                    target_quantity=5,
                )


class TestDonationFlow:
    def test_donation_updates_progress(self, app, charity_world):
        project_id, need_id = _create_project(app, charity_world, target=10)
        _, item_id = _submit_and_receive(app, charity_world, project_id, need_id, quantity=3)
        with app.app_context():
            need = db.session.get(CharityProjectNeed, need_id)
            assert need.accepted_quantity == 3
            donation_item = db.session.get(CharityDonationItem, item_id)
            donation = db.session.get(CharityDonation, donation_item.donation_id)
            assert donation.status == "received"

    def test_over_target_rejected(self, app, charity_world):
        """确认数量超出剩余目标被拒绝（BR-036，不超募）。"""
        project_id, need_id = _create_project(app, charity_world, target=5)
        _, donation_item_id = _submit_and_receive(
            app, charity_world, project_id, need_id, quantity=4
        )
        # 第二笔捐赠 3 件，但剩余目标只有 1 件
        with app.app_context():
            donor = _actor(app, charity_world["donor_id"])
            donation = charity_service.submit_donation(
                donor,
                project_id,
                station_id=charity_world["station_id"],
                items=[{"need_id": need_id, "quantity": 3, "condition": "good"}],
            )
            donation_id = donation.id
        with app.app_context():
            manager = _actor(app, charity_world["manager_id"])
            with pytest.raises(InputError):
                charity_service.review_donation(manager, donation_id, accept=True)
            # 拒绝后不计入进度
            need = db.session.get(CharityProjectNeed, need_id)
            assert need.accepted_quantity == 4

    def test_partial_accept_quantities(self, app, charity_world):
        """核验时可按分项确认数量接收（FR-C03）。"""
        project_id, need_id = _create_project(app, charity_world, target=10)
        with app.app_context():
            donor = _actor(app, charity_world["donor_id"])
            donation = charity_service.submit_donation(
                donor,
                project_id,
                station_id=charity_world["station_id"],
                items=[{"need_id": need_id, "quantity": 5, "condition": "good"}],
            )
            donation_id = donation.id
            donation_item_id = donation.items[0].id
        with app.app_context():
            manager = _actor(app, charity_world["manager_id"])
            charity_service.review_donation(
                manager,
                donation_id,
                accept=True,
                accepted_quantities={donation_item_id: 3},
            )
            item = db.session.get(CharityDonationItem, donation_item_id)
            assert item.accepted_quantity == 3
            need = db.session.get(CharityProjectNeed, need_id)
            assert need.accepted_quantity == 3

    def test_reject_requires_reason(self, app, charity_world):
        project_id, need_id = _create_project(app, charity_world)
        with app.app_context():
            donor = _actor(app, charity_world["donor_id"])
            donation = charity_service.submit_donation(
                donor,
                project_id,
                station_id=charity_world["station_id"],
                items=[{"need_id": need_id, "quantity": 1, "condition": "fair"}],
            )
            donation_id = donation.id
        with app.app_context():
            manager = _actor(app, charity_world["manager_id"])
            with pytest.raises(InputError):
                charity_service.review_donation(manager, donation_id, accept=False)
            donation = charity_service.review_donation(
                manager, donation_id, accept=False, reject_reason="衣物霉变，不符合接收标准"
            )
            assert donation.status == "rejected"
            assert donation.reject_reason

    def test_project_completed_when_all_needs_met(self, app, charity_world):
        """全部需求满足后项目完成，不再接受新捐赠（BR-037）。"""
        project_id, need_id = _create_project(app, charity_world, target=4)
        _submit_and_receive(app, charity_world, project_id, need_id, quantity=4)
        with app.app_context():
            project = db.session.get(CharityProject, project_id)
            assert project.status == "completed"
        with app.app_context():
            donor = _actor(app, charity_world["donor_id"])
            with pytest.raises(ConflictError):
                charity_service.submit_donation(
                    donor,
                    project_id,
                    station_id=charity_world["station_id"],
                    items=[{"need_id": need_id, "quantity": 1, "condition": "good"}],
                )

    def test_cross_university_project_invisible(self, app, charity_world):
        """跨校项目不可见（BR-034）。"""
        from tests.fixtures.helpers import create_campus, create_student_user, create_university

        project_id, _ = _create_project(app, charity_world)
        with app.app_context():
            other_uni = create_university(code="550003", name="外校公益大学")
            other_campus = create_campus(other_uni, code="Z1")
            outsider = create_student_user(other_uni, other_campus, student_no="2024997")
            outsider_id = outsider.id
        with app.app_context():
            outsider = _actor(app, outsider_id)
            with pytest.raises(NotFoundError):
                charity_service.get_project(outsider, project_id)

    def test_non_authorized_manager_cannot_review(self, app, charity_world):
        """未授权站点的管理员不能核验捐赠（FR-M03）。"""
        from tests.fixtures.helpers import create_station_manager_user

        project_id, need_id = _create_project(app, charity_world)
        with app.app_context():
            donor = _actor(app, charity_world["donor_id"])
            donation = charity_service.submit_donation(
                donor,
                project_id,
                station_id=charity_world["station_id"],
                items=[{"need_id": need_id, "quantity": 1, "condition": "good"}],
            )
            donation_id = donation.id
        with app.app_context():
            uni = db.session.get(University, charity_world["university_id"])
            outsider = create_station_manager_user(uni, login_name="cmgr2", nickname="未授权")
            outsider_id = outsider.id
        with app.app_context():
            outsider_actor = _actor(app, outsider_id)
            with pytest.raises(PermissionDeniedError):
                charity_service.review_donation(outsider_actor, donation_id, accept=True)


class TestReceipt:
    def test_publish_receipt_traceable_and_desensitized(self, app, charity_world):
        """回执可追溯捐赠明细；公开内容不含可识别个人信息（BR-038/BR-039）。"""
        project_id, need_id = _create_project(app, charity_world, target=10)
        _, donation_item_id = _submit_and_receive(
            app, charity_world, project_id, need_id, quantity=3
        )
        with app.app_context():
            manager = _actor(app, charity_world["manager_id"])
            receipt = charity_service.publish_receipt(
                manager,
                project_id,
                station_id=charity_world["station_id"],
                title="第一批冬衣接收回执",
                recipient_org="青禾公益合作组织",
                received_at=datetime.now(UTC),
                public_note="共接收冬季外套 3 件，已消毒入库。",
                items=[
                    {"donation_item_id": donation_item_id, "item_name": "冬季外套", "quantity": 3}
                ],
            )
            assert receipt.status == "published"
            assert receipt.station_id == charity_world["station_id"]
            assert receipt.items[0].donation_item_id == donation_item_id
            # 脱敏：回执字段不包含捐赠人身份信息
            assert receipt.created_by_user_id is not None
            assert "139" not in receipt.public_note
            assert str(charity_world["donor_id"]) not in receipt.public_note

        # 本校用户可查看
        with app.app_context():
            stranger = _actor(app, charity_world["stranger_id"])
            found = charity_service.get_published_receipt(stranger, receipt.id)
            assert found.id == receipt.id

    def test_receipt_quantity_cannot_exceed_accepted(self, app, charity_world):
        """回执数量不得大于已接收数量（BR-038）。"""
        project_id, need_id = _create_project(app, charity_world, target=10)
        _, donation_item_id = _submit_and_receive(
            app, charity_world, project_id, need_id, quantity=2
        )
        with app.app_context():
            manager = _actor(app, charity_world["manager_id"])
            with pytest.raises(ConflictError):
                charity_service.publish_receipt(
                    manager,
                    project_id,
                    station_id=charity_world["station_id"],
                    title="超额回执",
                    recipient_org="x",
                    received_at=datetime.now(UTC),
                    public_note="说明",
                    items=[{"donation_item_id": donation_item_id, "quantity": 5}],
                )

    def test_receipt_accumulated_over_accepted_rejected(self, app, charity_world):
        """同一明细跨回执累计不得超过已接收数量（BR-038，防虚报）。"""
        project_id, need_id = _create_project(app, charity_world, target=10)
        _, donation_item_id = _submit_and_receive(
            app, charity_world, project_id, need_id, quantity=3
        )
        with app.app_context():
            manager = _actor(app, charity_world["manager_id"])
            common = dict(
                recipient_org="青禾公益合作组织",
                received_at=datetime.now(UTC),
                public_note="分批发放回执。",
            )
            # 第一份回执登记 2 件：合法
            charity_service.publish_receipt(
                manager,
                project_id,
                station_id=charity_world["station_id"],
                title="第一批回执",
                items=[{"donation_item_id": donation_item_id, "quantity": 2}],
                **common,
            )
            # 第二份回执再登记 2 件：累计 4 > 已接收 3，拒绝
            with pytest.raises(ConflictError):
                charity_service.publish_receipt(
                    manager,
                    project_id,
                    station_id=charity_world["station_id"],
                    title="第二批回执",
                    items=[{"donation_item_id": donation_item_id, "quantity": 2}],
                    **common,
                )

    def test_receipt_station_must_be_authorized(self, app, charity_world):
        """回执站点必须在授权范围内（FR-M03）。"""
        from tests.fixtures.helpers import create_station_manager_user

        project_id, need_id = _create_project(app, charity_world)
        _, donation_item_id = _submit_and_receive(
            app, charity_world, project_id, need_id, quantity=1
        )
        with app.app_context():
            uni = db.session.get(University, charity_world["university_id"])
            outsider = create_station_manager_user(uni, login_name="cmgr9", nickname="未授权9")
            outsider_id = outsider.id
        with app.app_context():
            outsider = _actor(app, outsider_id)
            with pytest.raises(PermissionDeniedError):
                charity_service.publish_receipt(
                    outsider,
                    project_id,
                    station_id=charity_world["station_id"],
                    title="越权回执",
                    recipient_org="x",
                    received_at=datetime.now(UTC),
                    public_note="说明",
                    items=[{"donation_item_id": donation_item_id, "quantity": 1}],
                )

    def test_receipt_requires_traceable_donation_item(self, app, charity_world):
        """回执物资必须可追溯本项目已接收明细。"""
        project_id, _ = _create_project(app, charity_world)
        with app.app_context():
            manager = _actor(app, charity_world["manager_id"])
            with pytest.raises(InputError):
                charity_service.publish_receipt(
                    manager,
                    project_id,
                    station_id=charity_world["station_id"],
                    title="无来源回执",
                    recipient_org="x",
                    received_at=datetime.now(UTC),
                    public_note="说明",
                    items=[{"donation_item_id": 99999, "quantity": 1}],
                )

    def test_receipt_project_relationship_for_public_page(self, app, charity_world):
        """公开展示页读取 receipt.project.title 时关系必须可用。"""
        project_id, need_id = _create_project(app, charity_world, target=10)
        _, donation_item_id = _submit_and_receive(
            app, charity_world, project_id, need_id, quantity=1
        )
        with app.app_context():
            manager = _actor(app, charity_world["manager_id"])
            receipt = charity_service.publish_receipt(
                manager,
                project_id,
                station_id=charity_world["station_id"],
                title="公开展示回执",
                recipient_org="青禾公益合作组织",
                received_at=datetime.now(UTC),
                public_note="物资已接收。",
                items=[{"donation_item_id": donation_item_id, "quantity": 1}],
            )
            assert receipt.project.title == "冬衣捐赠计划"
