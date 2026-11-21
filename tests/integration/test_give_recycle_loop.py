"""集成测试：免费赠送与绿色回收闭环（G3）。

赠送链：发布 → 领取申请 → 接受 → 交接码 → 交接完成（无明细表）；
回收链：所有者提交回收 → 站点接受 → 送达交接（所有者出码、管理员确认）→ 站点验收；
异常链：未授权站点拒绝、验收不符合下架（D-036）、回收完成后不可重新上架（BR-015）。
"""

from __future__ import annotations

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
from app.models.circulation import CirculationRequest  # noqa: E402
from app.models.item import Item  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import circulation_service, handover_service, item_service  # noqa: E402


@pytest.fixture
def give_world(app):
    with app.app_context():
        uni = create_university()
        campus = create_campus(uni)
        owner = create_student_user(
            uni, campus, student_no="2024301", nickname="赠送者", phone="13900003001"
        )
        taker = create_student_user(
            uni, campus, student_no="2024302", nickname="领取人", phone="13900003002"
        )
        category = create_category(slug="daily", name="生活用品")
        db.session.commit()
        yield {
            "campus_id": campus.id,
            "owner_id": owner.id,
            "taker_id": taker.id,
            "category_id": category.id,
        }


@pytest.fixture
def recycle_world(app):
    """高校 + 物主 + 站点管理员（授权）+ 未授权管理员 + 回收站点。"""
    with app.app_context():
        uni = create_university()
        campus = create_campus(uni)
        owner = create_student_user(
            uni, campus, student_no="2024401", nickname="回收物主", phone="13900004001"
        )
        manager = create_station_manager_user(uni, login_name="mgr1")
        outsider = create_station_manager_user(uni, login_name="mgr2", nickname="其他站点管理员")
        station = create_station(uni, campus, station_type="recycle")
        assign_manager(station, manager)
        category = create_category(slug="recyclable", name="可回收物")
        admin, _ = create_platform_admin()
        db.session.commit()
        yield {
            "university_id": uni.id,
            "campus_id": campus.id,
            "owner_id": owner.id,
            "manager_id": manager.id,
            "outsider_id": outsider.id,
            "station_id": station.id,
            "category_id": category.id,
            "admin_id": admin.id,
        }


def _actor(app, user_id):
    with app.app_context():
        return to_current_user(db.session.get(User, user_id))


def _create_item(app, world, owner_id, mode, title):
    with app.app_context():
        owner = db.session.get(User, owner_id)
        item = create_item(
            owner, world["category_id"], world["campus_id"], mode=mode, title=title
        )
        return item.id


def _submit_recycle(app, world, item_id):
    """物主提交回收申请（requester=物主，owner=站点管理员）。"""
    with app.app_context():
        owner = _actor(app, world["owner_id"])
        start = datetime(2026, 12, 5, 10, 0, tzinfo=UTC)
        request = circulation_service.request_recycle(
            owner,
            item_id,
            station_id=world["station_id"],
            preferred_start_at=start,
            preferred_end_at=start + timedelta(hours=2),
            request_note="毕业清理",
        )
        return request.id


def _advance_recycle_to_inspection(app, world, item_id):
    """提交 → 站点接受 → 物主（交付方）出码 → 管理员（接收方）确认送达。"""
    request_id = _submit_recycle(app, world, item_id)
    with app.app_context():
        manager = _actor(app, world["manager_id"])
        request = circulation_service.decide_request(manager, request_id, decision="accept")
        assert request.status == "handover_pending"
    with app.app_context():
        owner = _actor(app, world["owner_id"])
        _, code = handover_service.issue_handover_code(owner, request_id)
    with app.app_context():
        manager = _actor(app, world["manager_id"])
        request = handover_service.confirm_handover(manager, request_id, code=code)
        assert request.status == "inspection_pending"
    return request_id


class TestGiveLoop:
    def test_full_give_loop(self, app, give_world):
        """领取 → 接受 → 交接码 → 交接完成（FR-G01、FR-G02）。"""
        item_id = _create_item(app, give_world, give_world["owner_id"], "give", "闲置台历")
        with app.app_context():
            taker = _actor(app, give_world["taker_id"])
            request = circulation_service.request_giveaway(taker, item_id, request_note="正好需要")
            request_id = request.id
            assert request.status == "pending"
            assert db.session.get(Item, item_id).status == "reserved"
        with app.app_context():
            owner = _actor(app, give_world["owner_id"])
            request = circulation_service.decide_request(owner, request_id, decision="accept")
            assert request.status == "handover_pending"
            _, code = handover_service.issue_handover_code(owner, request_id)
        with app.app_context():
            taker = _actor(app, give_world["taker_id"])
            request = handover_service.confirm_handover(taker, request_id, code=code)
            assert request.status == "completed"
            item = db.session.get(Item, item_id)
            assert item.status == "completed"
            # BR-015：赠送交接完成即转移所有权给领取人，领取人可重新上架
            assert item.owner_user_id == give_world["taker_id"]

        with app.app_context():
            taker = _actor(app, give_world["taker_id"])
            item = item_service.change_item_shelf_state(taker, item_id, action="relist")
            assert item.status == "active"

    def test_non_give_mode_rejected(self, app, give_world):
        item_id = _create_item(app, give_world, give_world["owner_id"], "borrow", "借用书")
        with app.app_context():
            taker = _actor(app, give_world["taker_id"])
            with pytest.raises(PermissionDeniedError):
                circulation_service.request_giveaway(taker, item_id)


class TestRecycleLoop:
    def test_full_recycle_loop(self, app, recycle_world):
        """回收申请 → 站点接受 → 送达 → 验收通过完成（FR-R01 ~ FR-R03）。"""
        from sqlalchemy import select

        from app.models.governance import Notification

        item_id = _create_item(
            app, recycle_world, recycle_world["owner_id"], "recycle", "旧羽绒服"
        )
        request_id = _advance_recycle_to_inspection(app, recycle_world, item_id)

        with app.app_context():
            request = db.session.get(CirculationRequest, request_id)
            assert request.status == "inspection_pending"
            assert db.session.get(Item, item_id).status == "in_progress"
            # 回收链：requester=物主、owner=站点管理员
            assert request.requester_user_id == recycle_world["owner_id"]
            assert request.owner_user_id == recycle_world["manager_id"]

        # 验收通过 → 完成
        with app.app_context():
            manager = _actor(app, recycle_world["manager_id"])
            request = circulation_service.inspect_recycle(
                manager, request_id, passed=True, note="完好可用"
            )
            assert request.status == "completed"
            assert db.session.get(Item, item_id).status == "completed"

            # 状态历史完整
            history = circulation_service.request_history(request)
            transitions = [(h.from_status, h.to_status) for h in history]
            assert ("pending", "handover_pending") in transitions
            assert ("handover_pending", "inspection_pending") in transitions
            assert ("inspection_pending", "completed") in transitions

            rows = db.session.scalars(select(Notification)).all()
            assert recycle_world["owner_id"] in {n.recipient_user_id for n in rows}

    def test_inspection_rejected_moves_item_off_shelf(self, app, recycle_world):
        """验收不符合：记录原因、申请 rejected、物品下架（BR-031、D-036）。"""
        item_id = _create_item(
            app, recycle_world, recycle_world["owner_id"], "recycle", "破损书包"
        )
        request_id = _advance_recycle_to_inspection(app, recycle_world, item_id)
        with app.app_context():
            manager = _actor(app, recycle_world["manager_id"])
            request = circulation_service.inspect_recycle(
                manager, request_id, passed=False, note="破损严重，无法再利用"
            )
            assert request.status == "rejected"
            assert db.session.get(Item, item_id).status == "off_shelf"

        # 不填原因被拒绝
        item_id2 = _create_item(
            app, recycle_world, recycle_world["owner_id"], "recycle", "旧台灯"
        )
        request_id2 = _advance_recycle_to_inspection(app, recycle_world, item_id2)
        with app.app_context():
            manager = _actor(app, recycle_world["manager_id"])
            with pytest.raises(InputError):
                circulation_service.inspect_recycle(manager, request_id2, passed=False, note="")

        # D-036：所有者可重新上架
        with app.app_context():
            owner = _actor(app, recycle_world["owner_id"])
            item = item_service.change_item_shelf_state(owner, item_id, action="relist")
            assert item.status == "active"

    def test_recycle_completed_item_cannot_relist(self, app, recycle_world):
        """回收完成不可重新上架（BR-015）。"""
        item_id = _create_item(
            app, recycle_world, recycle_world["owner_id"], "recycle", "旧教材"
        )
        request_id = _advance_recycle_to_inspection(app, recycle_world, item_id)
        with app.app_context():
            manager = _actor(app, recycle_world["manager_id"])
            circulation_service.inspect_recycle(manager, request_id, passed=True)
        with app.app_context():
            owner = _actor(app, recycle_world["owner_id"])
            with pytest.raises(PermissionDeniedError):
                item_service.change_item_shelf_state(owner, item_id, action="relist")

    def test_unauthorized_manager_cannot_accept(self, app, recycle_world):
        """未授权站点的管理员不能处理回收申请（FR-M03）。"""
        item_id = _create_item(
            app, recycle_world, recycle_world["owner_id"], "recycle", "旧水壶"
        )
        request_id = _submit_recycle(app, recycle_world, item_id)
        with app.app_context():
            outsider = _actor(app, recycle_world["outsider_id"])
            with pytest.raises(PermissionDeniedError):
                circulation_service.decide_request(outsider, request_id, decision="accept")

    def test_station_without_manager_rejects_request(self, app, recycle_world):
        """站点没有在职管理员时拒绝接单。"""
        from app.models.university import Campus
        from tests.fixtures.helpers import create_station

        item_id = _create_item(
            app, recycle_world, recycle_world["owner_id"], "recycle", "空瓶"
        )
        with app.app_context():
            campus = db.session.get(Campus, recycle_world["campus_id"])
            orphan_station = create_station(campus.university, campus, name="无管理员站点")
            station_id = orphan_station.id
        with app.app_context():
            owner = _actor(app, recycle_world["owner_id"])
            start = datetime(2026, 12, 5, 10, 0, tzinfo=UTC)
            with pytest.raises(ConflictError):
                circulation_service.request_recycle(
                    owner,
                    item_id,
                    station_id=station_id,
                    preferred_start_at=start,
                    preferred_end_at=start + timedelta(hours=1),
                )

    def test_only_owner_can_submit_recycle(self, app, recycle_world):
        item_id = _create_item(
            app, recycle_world, recycle_world["owner_id"], "recycle", "他人物品"
        )
        with app.app_context():
            manager = _actor(app, recycle_world["manager_id"])
            with pytest.raises(PermissionDeniedError):
                start = datetime(2026, 12, 5, 10, 0, tzinfo=UTC)
                circulation_service.request_recycle(
                    manager,
                    item_id,
                    station_id=recycle_world["station_id"],
                    preferred_start_at=start,
                    preferred_end_at=start + timedelta(hours=1),
                )
