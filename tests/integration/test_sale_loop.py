"""集成测试：二手交易与模拟支付闭环（G3）。

正常链：发布 → 购买申请 → 卖家接受（进入待模拟支付）→ 支付成功 → 交接码 → 交接完成；
异常链：支付失败 / 取消（解除占用恢复可申请）、非买家支付、错误模式校验、跨校隔离。
"""

from __future__ import annotations

import pytest

from tests.fixtures.helpers import (
    create_campus,
    create_category,
    create_platform_admin,
    create_student_user,
    create_university,
)

pytestmark = pytest.mark.integration

from app import db  # noqa: E402
from app.core.errors import ConflictError, PermissionDeniedError  # noqa: E402
from app.core.permissions import to_current_user  # noqa: E402
from app.models.circulation import CirculationRequest, SaleDetails  # noqa: E402
from app.models.item import Item  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import circulation_service, handover_service, item_service  # noqa: E402


@pytest.fixture
def sale_world(app):
    """一所高校 + 卖家/买家 + 分类 + 平台管理员。"""
    with app.app_context():
        uni = create_university()
        campus = create_campus(uni)
        seller = create_student_user(
            uni, campus, student_no="2024201", nickname="卖家", phone="13900002001"
        )
        buyer = create_student_user(
            uni, campus, student_no="2024202", nickname="买家", phone="13900002002"
        )
        category = create_category(slug="electronics", name="数码电子")
        admin, _ = create_platform_admin()
        db.session.commit()
        yield {
            "university_id": uni.id,
            "campus_id": campus.id,
            "seller_id": seller.id,
            "buyer_id": buyer.id,
            "category_id": category.id,
            "admin_id": admin.id,
        }


def _actor(app, user_id):
    with app.app_context():
        return to_current_user(db.session.get(User, user_id))


def _create_sale_item(app, world, title="机械键盘", price_cents=8800):
    from tests.fixtures.helpers import create_item

    with app.app_context():
        seller = db.session.get(User, world["seller_id"])
        item = create_item(
            seller,
            world["category_id"],
            world["campus_id"],
            mode="sale",
            title=title,
            description="九成新，无维修",
            condition="good",
            sale_price_cents=price_cents,
        )
        return item.id


def _advance_to_payment(app, world, item_id):
    """购买 → 卖家接受，返回 request_id（状态 payment_pending）。"""
    with app.app_context():
        buyer = _actor(app, world["buyer_id"])
        request = circulation_service.request_purchase(buyer, item_id, request_note="想要很久了")
        request_id = request.id
    with app.app_context():
        seller = _actor(app, world["seller_id"])
        request = circulation_service.decide_request(seller, request_id, decision="accept")
        assert request.status == "payment_pending"
    return request_id


class TestSaleHappyPath:
    def test_full_sale_loop(self, app, sale_world):
        """购买 → 接受 → 模拟支付成功 → 交接码 → 交接完成（FR-S01、FR-S02）。"""
        from sqlalchemy import select

        from app.models.governance import Notification

        item_id = _create_sale_item(app, sale_world)
        request_id = _advance_to_payment(app, sale_world, item_id)

        with app.app_context():
            request = db.session.get(CirculationRequest, request_id)
            assert request.status == "payment_pending"
            assert db.session.get(Item, item_id).status == "reserved"
            details = db.session.get(SaleDetails, request_id)
            assert details.agreed_price_cents == 8800

        # 支付前不能交接
        with app.app_context():
            seller = _actor(app, sale_world["seller_id"])
            with pytest.raises(ConflictError):
                handover_service.issue_handover_code(seller, request_id)

        # 模拟支付成功
        with app.app_context():
            buyer = _actor(app, sale_world["buyer_id"])
            request = circulation_service.simulate_payment(buyer, request_id, outcome="success")
            assert request.status == "handover_pending"
            details = db.session.get(SaleDetails, request_id)
            assert details.payment_status == "paid"
            assert details.payment_reference.startswith("SIM-")
            assert details.paid_at is not None

        # 卖家生成交接码 → 买家确认 → 完成
        with app.app_context():
            seller = _actor(app, sale_world["seller_id"])
            _, code = handover_service.issue_handover_code(seller, request_id)
        with app.app_context():
            buyer = _actor(app, sale_world["buyer_id"])
            request = handover_service.confirm_handover(buyer, request_id, code=code)
            assert request.status == "completed"
            assert request.completed_at is not None
            item = db.session.get(Item, item_id)
            assert item.status == "completed"
            # BR-015：出售交接完成即转移所有权给买家，买家可重新上架
            assert item.owner_user_id == sale_world["buyer_id"]

        with app.app_context():
            buyer = _actor(app, sale_world["buyer_id"])
            item = item_service.change_item_shelf_state(buyer, item_id, action="relist")
            assert item.status == "active"

            # 状态历史完整
            history = circulation_service.request_history(request)
            transitions = [(h.from_status, h.to_status) for h in history]
            assert ("pending", "payment_pending") in transitions
            assert ("payment_pending", "handover_pending") in transitions
            assert ("handover_pending", "completed") in transitions

            # 双方收到通知
            rows = db.session.scalars(select(Notification)).all()
            assert {sale_world["seller_id"], sale_world["buyer_id"]} <= {
                n.recipient_user_id for n in rows
            }

    def test_payment_failure_cancels_and_releases_item(self, app, sale_world):
        """支付失败：申请取消、物品恢复可申请（BR-026）。"""
        item_id = _create_sale_item(app, sale_world, title="蓝牙耳机", price_cents=5000)
        request_id = _advance_to_payment(app, sale_world, item_id)
        with app.app_context():
            buyer = _actor(app, sale_world["buyer_id"])
            request = circulation_service.simulate_payment(buyer, request_id, outcome="fail")
            assert request.status == "cancelled"
            details = db.session.get(SaleDetails, request_id)
            assert details.payment_status == "failed"
            assert db.session.get(Item, item_id).status == "active"

    def test_payment_cancel_releases_item(self, app, sale_world):
        """买家取消支付：申请取消、物品恢复可申请（BR-026）。"""
        item_id = _create_sale_item(app, sale_world, title="台灯", price_cents=3000)
        request_id = _advance_to_payment(app, sale_world, item_id)
        with app.app_context():
            buyer = _actor(app, sale_world["buyer_id"])
            request = circulation_service.simulate_payment(buyer, request_id, outcome="cancel")
            assert request.status == "cancelled"
            assert db.session.get(Item, item_id).status == "active"


class TestSaleGuards:
    def test_only_buyer_can_pay(self, app, sale_world):
        """只有买家可以执行模拟支付。"""
        item_id = _create_sale_item(app, sale_world)
        request_id = _advance_to_payment(app, sale_world, item_id)
        with app.app_context():
            seller = _actor(app, sale_world["seller_id"])
            with pytest.raises(PermissionDeniedError):
                circulation_service.simulate_payment(seller, request_id, outcome="success")

    def test_cannot_buy_own_item(self, app, sale_world):
        item_id = _create_sale_item(app, sale_world)
        with app.app_context():
            seller = _actor(app, sale_world["seller_id"])
            with pytest.raises(PermissionDeniedError):
                circulation_service.request_purchase(seller, item_id)

    def test_non_sale_mode_rejected(self, app, sale_world):
        from tests.fixtures.helpers import create_item

        with app.app_context():
            seller = db.session.get(User, sale_world["seller_id"])
            item = create_item(
                seller, sale_world["category_id"], sale_world["campus_id"], mode="borrow"
            )
            item_id = item.id
        with app.app_context():
            buyer = _actor(app, sale_world["buyer_id"])
            with pytest.raises(PermissionDeniedError):
                circulation_service.request_purchase(buyer, item_id)

    def test_cross_university_invisible(self, app, sale_world):
        from app.core.errors import NotFoundError
        from tests.fixtures.helpers import create_campus, create_student_user, create_university

        item_id = _create_sale_item(app, sale_world)
        with app.app_context():
            other_uni = create_university(code="540002", name="外校大学")
            other_campus = create_campus(other_uni, code="Y1")
            stranger = create_student_user(other_uni, other_campus, student_no="2024998")
            stranger_id = stranger.id
        with app.app_context():
            stranger = _actor(app, stranger_id)
            with pytest.raises(NotFoundError):
                circulation_service.request_purchase(stranger, item_id)

    def test_non_student_cannot_purchase(self, app, sale_world):
        item_id = _create_sale_item(app, sale_world)
        with app.app_context():
            admin = _actor(app, sale_world["admin_id"])
            with pytest.raises(PermissionDeniedError):
                circulation_service.request_purchase(admin, item_id)
