"""集成测试：共享借还完整闭环（G2 第一条业务穿线）。

正常链：发布 → 申请 → 接受 → 交接码 → 取件 → 归还 → 完成；
异常链：拒绝、取消、错误/过期/旧版码、二次申请、借期重叠、跨校隔离、逾期、争议；
HTTP 穿线：通过路由与表单验证整条链路（service/route/model/template 齐全）。
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import pytest

from tests.fixtures.helpers import (
    create_campus,
    create_category,
    create_import_batch,
    create_platform_admin,
    create_registry_record,
    create_student_user,
    create_university,
)

pytestmark = pytest.mark.integration

TODAY = date(2026, 12, 1)

# 多个用例在 app 上下文中复用这些名称；统一在模块级导入
from app import db  # noqa: E402
from app.core.permissions import to_current_user  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import circulation_service, handover_service  # noqa: E402


@pytest.fixture
def borrow_world(app):
    """一所高校 + 两名学生（所有者/借用人）+ 分类 + 名单（供 HTTP 登录）。"""
    with app.app_context():
        uni = create_university()
        campus = create_campus(uni)
        owner = create_student_user(
            uni, campus, student_no="2024101", nickname="出借人", phone="13900001001"
        )
        borrower = create_student_user(
            uni, campus, student_no="2024102", nickname="借用人", phone="13900001002"
        )
        category = create_category()
        admin, _ = create_platform_admin()
        # HTTP 登录用名单记录（挂到既有账号）
        batch = create_import_batch(uni, admin)
        for student, phone in ((owner, "13800001001"), (borrower, "13800001002")):
            record = create_registry_record(
                uni, campus, batch, student_no=student.student_no, phone=phone
            )
            record.registered_user_id = student.id

        db.session.commit()
        yield {
            "university_id": uni.id,
            "campus_id": campus.id,
            "owner_id": owner.id,
            "borrower_id": borrower.id,
            "category_id": category.id,
            "admin_id": admin.id,
        }


def _actor(app, user_id):
    """构造 CurrentUser actor（service 层统一接收 CurrentUser）。"""

    with app.app_context():
        return to_current_user(db.session.get(User, user_id))


def _create_item(app, owner_id, title="高等数学教材"):
    from app.services import item_service

    with app.app_context():
        owner = _actor(app, owner_id)
        item = item_service.create_item(
            owner,
            category_id=_category_id(app),
            mode="borrow",
            title=title,
            description="九成新",
            condition="like_new",
            campus_id=_campus_id(app, owner),
        )
        return item.id


def _category_id(app):
    from app.models.item import ItemCategory

    with app.app_context():
        from sqlalchemy import select

        return db.session.scalar(select(ItemCategory).where(ItemCategory.slug == "books")).id


def _campus_id(app, owner):
    return owner.campus_id


def _request_borrow(app, borrower_id, item_id, start=TODAY, due=TODAY + timedelta(days=7)):
    with app.app_context():
        borrower = _actor(app, borrower_id)
        request = circulation_service.request_borrow(
            borrower, item_id, start_date=start, due_date=due, request_note="想借用一周"
        )
        return request.id


def _advance_to_in_progress(app, world, item_id):
    """辅助：申请 → 接受 → 生成交接码 → 取件，返回 (request_id, code)。"""

    request_id = _request_borrow(app, world["borrower_id"], item_id)
    with app.app_context():
        owner = _actor(app, world["owner_id"])
        circulation_service.decide_request(owner, request_id, decision="accept")
        _, code = handover_service.issue_handover_code(owner, request_id)
    with app.app_context():
        borrower = _actor(app, world["borrower_id"])
        handover_service.confirm_handover(borrower, request_id, code=code)
    return request_id, code


class TestBorrowHappyPath:
    def test_full_borrow_loop(self, app, borrow_world):
        """发布 → 申请 → 接受 → 交接码 → 取件 → 归还 → 完成（FR-B01 ~ B07）。"""
        from sqlalchemy import select

        from app.models.governance import Notification

        item_id = _create_item(app, borrow_world["owner_id"])

        with app.app_context():
            from app.models.item import Item

            item = db.session.get(Item, item_id)
            assert item.status == "active"

        request_id = _request_borrow(app, borrow_world["borrower_id"], item_id)
        with app.app_context():
            from app.models.circulation import CirculationRequest
            from app.models.item import Item

            request = db.session.get(CirculationRequest, request_id)
            assert request.status == "pending"
            assert db.session.get(Item, item_id).status == "reserved"

        # 接受 -> 待交接
        with app.app_context():
            owner = _actor(app, borrow_world["owner_id"])
            request = circulation_service.decide_request(owner, request_id, decision="accept")
            assert request.status == "handover_pending"

        # 生成交接码
        with app.app_context():
            owner = _actor(app, borrow_world["owner_id"])
            _, code = handover_code(owner, request_id)
            assert len(code) == 6 and code.isdigit()

        # 错误码不推进状态
        with app.app_context():
            borrower = _actor(app, borrow_world["borrower_id"])
            from app.core.errors import InputError

            wrong = "000000" if code != "000000" else "111111"
            with pytest.raises(InputError):
                circulation_confirm_handover(borrower, request_id, wrong)
            from app.models.circulation import CirculationRequest

            assert db.session.get(CirculationRequest, request_id).status == "handover_pending"

        # 正确码完成取件
        with app.app_context():
            borrower = _actor(app, borrow_world["borrower_id"])
            request = circulation_confirm_handover(borrower, request_id, code)
            assert request.status == "in_progress"
            from app.models.item import Item

            assert db.session.get(Item, item_id).status == "in_progress"

        # 提交归还
        with app.app_context():
            borrower = _actor(app, borrow_world["borrower_id"])
            request = circulation_service.submit_return(
                borrower, request_id, return_note="已完好归还"
            )
            assert request.status == "return_pending"

        # 确认归还 -> 完成
        with app.app_context():
            owner = _actor(app, borrow_world["owner_id"])
            request = circulation_service.confirm_return(owner, request_id, condition_ok=True)
            assert request.status == "completed"
            from app.models.item import Item

            assert db.session.get(Item, item_id).status == "completed"

            # 状态历史完整（FR-H03）
            history = circulation_service.request_history(request)
            transitions = [(h.from_status, h.to_status) for h in history]
            assert (None, "pending") in transitions
            assert ("pending", "handover_pending") in transitions
            assert ("handover_pending", "in_progress") in transitions
            assert ("in_progress", "return_pending") in transitions
            assert ("return_pending", "completed") in transitions

            # 双方都收到通知（FR-H06）
            notifications = db.session.scalars(select(Notification)).all()
            recipients = {n.recipient_user_id for n in notifications}
            assert borrow_world["owner_id"] in recipients
            assert borrow_world["borrower_id"] in recipients


def handover_code(owner, request_id):
    return handover_service.issue_handover_code(owner, request_id)


def circulation_confirm_handover(borrower, request_id, code):
    return handover_service.confirm_handover(borrower, request_id, code=code)


class TestBorrowExceptions:
    def test_reject_restores_item(self, app, borrow_world):
        item_id = _create_item(app, borrow_world["owner_id"])
        request_id = _request_borrow(app, borrow_world["borrower_id"], item_id)
        with app.app_context():
            from app.core.states import ITEM_ACTIVE
            from app.models.item import Item

            owner = _actor(app, borrow_world["owner_id"])
            request = circulation_service.decide_request(owner, request_id, decision="reject")
            assert request.status == "rejected"
            assert db.session.get(Item, item_id).status == ITEM_ACTIVE

    def test_cancel_by_requester_restores_item(self, app, borrow_world):
        item_id = _create_item(app, borrow_world["owner_id"])
        request_id = _request_borrow(app, borrow_world["borrower_id"], item_id)
        with app.app_context():
            from app.core.states import ITEM_ACTIVE
            from app.models.item import Item

            borrower = _actor(app, borrow_world["borrower_id"])
            request = handover_service.cancel_request(borrower, request_id, reason="计划有变")
            assert request.status == "cancelled"
            assert db.session.get(Item, item_id).status == ITEM_ACTIVE

    def test_cancel_after_handover_forbidden(self, app, borrow_world):
        """交接后不能取消，只能走归还或争议（BR-028）。"""
        from app.core.errors import ConflictError

        item_id = _create_item(app, borrow_world["owner_id"])
        request_id, code = _advance_to_in_progress(app, borrow_world, item_id)
        with app.app_context():
            borrower = _actor(app, borrow_world["borrower_id"])
            with pytest.raises(ConflictError):
                handover_service.cancel_request(borrower, request_id, reason="反悔了")

    def test_second_active_request_blocked(self, app, borrow_world):
        """同一物品不能有两条活动申请（BR-012）。"""
        from app.core.errors import ConflictError

        item_id = _create_item(app, borrow_world["owner_id"])
        _request_borrow(app, borrow_world["borrower_id"], item_id)
        with app.app_context():
            borrower = _actor(app, borrow_world["borrower_id"])
            with pytest.raises(ConflictError):
                circulation_service.request_borrow(
                    borrower, item_id, start_date=TODAY, due_date=TODAY + timedelta(days=3)
                )

    def test_overlapping_dates_rejected_at_acceptance(self, app, borrow_world):
        """BR-022：批准前校验相同物品借期不重叠。

        受 BR-012（同一物品仅一条活动申请）限制，公开流程无法构造两条
        并行申请；此处直接验证 accept 使用的借期冲突守卫。
        """
        from app.core.errors import ConflictError
        from app.models.circulation import BorrowDetails, CirculationRequest

        item_id = _create_item(app, borrow_world["owner_id"])
        first_id, code = _advance_to_pending_code(app, borrow_world, item_id)
        with app.app_context():
            borrower = _actor(app, borrow_world["borrower_id"])
            circulation_confirm_handover(borrower, first_id, code)

        # 第一条借用占用 12-01 ~ 12-07；构造与它重叠/不重叠的待校验申请
        with app.app_context():
            details = db.session.get(BorrowDetails, first_id)
            request = db.session.get(CirculationRequest, first_id)
            overlapping = CirculationRequest(
                id=0,
                university_id=request.university_id,
                item_id=item_id,
                requester_user_id=request.requester_user_id,
                owner_user_id=request.owner_user_id,
                mode="borrow",
            )
            guard = circulation_service._ensure_no_date_conflict
            with pytest.raises(ConflictError):
                guard(overlapping, details.start_date, details.due_date)
            guard(
                overlapping,
                details.due_date + timedelta(days=1),
                details.due_date + timedelta(days=5),
            )

    def test_cross_university_item_invisible(self, app, borrow_world):
        """跨校对象不可见（BR-002）：返回 404 不泄露存在性。"""
        from app.core.errors import NotFoundError
        from app.services import circulation_service, item_service

        item_id = _create_item(app, borrow_world["owner_id"])
        with app.app_context():
            other_uni = create_university(code="530003", name="外校学院")
            other_campus = create_campus(other_uni, code="X1")
            stranger = create_student_user(other_uni, other_campus, student_no="2024999")
            stranger_id = stranger.id

        with app.app_context():
            stranger = _actor(app, stranger_id)
            with pytest.raises(NotFoundError):
                item_service.get_visible_item(stranger, item_id)
            with pytest.raises(NotFoundError):
                circulation_service.get_request_detail(stranger, 1)

    def test_self_request_rejected(self, app, borrow_world):
        from app.core.errors import PermissionDeniedError

        item_id = _create_item(app, borrow_world["owner_id"])
        with app.app_context():
            owner = _actor(app, borrow_world["owner_id"])
            with pytest.raises(PermissionDeniedError):
                circulation_service.request_borrow(
                    owner, item_id, start_date=TODAY, due_date=TODAY + timedelta(days=1)
                )

    def test_expired_code_rejected(self, app, borrow_world):
        """交接码 10 分钟过期后不能使用（BR-017）。"""
        from app.core.errors import InputError

        item_id = _create_item(app, borrow_world["owner_id"])
        request_id, code = _advance_to_pending_code(app, borrow_world, item_id)
        with app.app_context():
            from app.models.circulation import HandoverRecord

            record = db.session.query(HandoverRecord).filter_by(request_id=request_id).one()
            # 平移整段有效期到过去，保持 expires_at > generated_at 的 CHECK 约束
            shift = timedelta(minutes=20)
            record.generated_at = record.generated_at - shift
            record.expires_at = record.expires_at - shift
            db.session.commit()
        with app.app_context():
            borrower = _actor(app, borrow_world["borrower_id"])
            with pytest.raises(InputError):
                handover_service.confirm_handover(borrower, request_id, code=code)

    def test_regenerated_code_invalidates_old(self, app, borrow_world):
        """重新生成后旧码失效（BR-017）。"""
        from app.core.errors import InputError

        item_id = _create_item(app, borrow_world["owner_id"])
        request_id = _request_borrow(app, borrow_world["borrower_id"], item_id)
        with app.app_context():
            owner = _actor(app, borrow_world["owner_id"])
            circulation_service.decide_request(owner, request_id, decision="accept")
            _, old_code = handover_service.issue_handover_code(owner, request_id)
            _, new_code = handover_service.issue_handover_code(owner, request_id)
            assert old_code != new_code
        with app.app_context():
            borrower = _actor(app, borrow_world["borrower_id"])
            with pytest.raises(InputError):
                handover_service.confirm_handover(borrower, request_id, code=old_code)
            request = handover_service.confirm_handover(borrower, request_id, code=new_code)
            assert request.status == "in_progress"


def _advance_to_pending_code(app, world, item_id):
    """申请 → 接受 → 生成交接码（未取件）。"""

    request_id = _request_borrow(app, world["borrower_id"], item_id)
    with app.app_context():
        owner = _actor(app, world["owner_id"])
        circulation_service.decide_request(owner, request_id, decision="accept")
        _, code = handover_service.issue_handover_code(owner, request_id)
    return request_id, code


class TestOverdueAndDispute:
    def test_overdue_detected_dynamically(self, app, borrow_world):
        """BR-024：逾期动态计算；逾期仍允许归还。"""
        from app.models.circulation import BorrowDetails

        item_id = _create_item(app, borrow_world["owner_id"])
        request_id, code = _advance_to_pending_code(app, borrow_world, item_id)
        with app.app_context():
            borrower = _actor(app, borrow_world["borrower_id"])
            circulation_confirm_handover(borrower, request_id, code)
        with app.app_context():
            details = db.session.get(BorrowDetails, request_id)
            # 平移整个借期到过去（保持 due_date >= start_date 约束），使 due 早于今天
            shift = details.due_date - date.today() + timedelta(days=2)
            details.start_date = details.start_date - shift
            details.due_date = details.due_date - shift
            db.session.commit()
        with app.app_context():
            from app.models.circulation import CirculationRequest

            request = db.session.get(CirculationRequest, request_id)
            assert circulation_service.is_overdue(request)
            borrower = _actor(app, borrow_world["borrower_id"])
            circulation_service.submit_return(borrower, request_id, return_note="晚归还了两天")
            owner = _actor(app, borrow_world["owner_id"])
            request = circulation_service.confirm_return(owner, request_id, condition_ok=True)
            assert request.status == "completed"

    def test_return_damage_dispute_and_resolution(self, app, borrow_world):
        """BR-023/BR-041/BR-042：损坏转争议 → 管理员处理关闭 + 审计。"""
        from sqlalchemy import select

        from app.models.circulation import CirculationRequest
        from app.models.governance import AuditLog, Dispute
        from app.models.item import Item

        item_id = _create_item(app, borrow_world["owner_id"])
        request_id, code = _advance_to_pending_code(app, borrow_world, item_id)
        with app.app_context():
            borrower = _actor(app, borrow_world["borrower_id"])
            circulation_confirm_handover(borrower, request_id, code)
            circulation_service.submit_return(borrower, request_id, return_note="已归还")
        with app.app_context():
            owner = _actor(app, borrow_world["owner_id"])
            request = circulation_service.confirm_return(
                owner, request_id, condition_ok=False, note="书脊开裂，与描述不符"
            )
            assert request.status == "disputed"
            assert db.session.get(Item, item_id).status == "on_hold"

        with app.app_context():
            dispute = db.session.scalar(
                select(Dispute).where(Dispute.circulation_request_id == request_id)
            )
            admin = _actor(app, borrow_world["admin_id"])
            borrower = _actor(app, borrow_world["borrower_id"])
            from app.core.errors import PermissionDeniedError

            with pytest.raises(PermissionDeniedError):
                handover_service.resolve_dispute(borrower, dispute.id, resolution="测试")
            dispute = handover_service.resolve_dispute(
                admin, dispute.id, resolution="双方协商一致，业务关闭"
            )
            assert dispute.status == "resolved"
            assert db.session.get(CirculationRequest, request_id).status == "completed"
            assert db.session.get(Item, item_id).status == "completed"
            audit = db.session.scalar(select(AuditLog).where(AuditLog.action == "dispute.resolve"))
            assert audit is not None


def _login_student(client, student_no):
    """以预置名单学生登录（密码 student1）：身份 → 学校校区 → 登录。"""
    from tests.integration.test_register_and_login import get_csrf_token

    page = client.get("/auth/identity").get_data(as_text=True)
    client.post(
        "/auth/identity",
        data={"csrf_token": get_csrf_token(page), "role": "student"},
        follow_redirects=True,
    )


class TestBorrowViaHttp:
    def test_borrow_loop_through_routes(self, client, app, borrow_world):
        """HTTP 表单走完整链路：路由、模板、CSRF 与 flash 提示齐全。"""
        from app.models.university import Campus
        from tests.integration.test_register_and_login import get_csrf_token

        owner_no, borrower_no = "2024101", "2024102"

        # 所有者登录（学校校区上下文在服务端从会话获得——HTTP 登录需先选校区）
        _http_login(client, owner_no)
        page = client.get("/items/new").get_data(as_text=True)
        assert "发布物品" in page

        with app.app_context():
            campus_id = db.session.get(Campus, borrow_world["campus_id"]).id
        resp = client.post(
            "/items/new",
            data={
                "csrf_token": get_csrf_token(page),
                "title": "羽毛球拍",
                "description": "单打训练拍",
                "mode": "borrow",
                "condition": "good",
                "category_id": str(borrow_world["category_id"]),
                "campus_id": str(campus_id),
            },
            follow_redirects=True,
        )
        assert "发布成功" in resp.get_data(as_text=True)

        html = client.get("/items").get_data(as_text=True)
        match = re.search(r"/items/(\d+)", html)
        assert match, "发现页应包含新物品链接"
        item_id = int(match.group(1))

        # 切换借用人：退出 → 登录 → 申请
        page = client.get("/").get_data(as_text=True)
        client.post(
            "/auth/logout",
            data={"csrf_token": get_csrf_token(page)},
            follow_redirects=True,
        )
        _http_login(client, borrower_no)
        page = client.get(f"/items/{item_id}").get_data(as_text=True)
        resp = client.post(
            f"/items/{item_id}/borrow",
            data={
                "csrf_token": get_csrf_token(page),
                "start_date": "2026-12-05",
                "due_date": "2026-12-12",
                "request_note": "周末打球用",
            },
            follow_redirects=True,
        )
        assert "借用申请已提交" in resp.get_data(as_text=True)

        page = client.get("/me/requests").get_data(as_text=True)
        request_match = re.search(r"/requests/(\d+)", page)
        assert request_match, "我的申请页应包含申请链接"
        request_id = int(request_match.group(1))

        # 所有者：接受 → 生成交接码
        client.post(
            "/auth/logout",
            data={"csrf_token": get_csrf_token(page)},
            follow_redirects=True,
        )
        _http_login(client, owner_no)
        page = client.get(f"/requests/{request_id}").get_data(as_text=True)
        resp = client.post(
            f"/requests/{request_id}/decide",
            data={"csrf_token": get_csrf_token(page), "decision": "accept"},
            follow_redirects=True,
        )
        assert "已接受申请" in resp.get_data(as_text=True)

        page = client.get(f"/requests/{request_id}").get_data(as_text=True)
        resp = client.post(
            f"/requests/{request_id}/issue-code",
            data={"csrf_token": get_csrf_token(page)},
            follow_redirects=True,
        )
        code_match = re.search(
            r"交接码已生成（10 分钟内有效）：(\d{6})", resp.get_data(as_text=True)
        )
        assert code_match, "交接码明文应一次性展示"
        code = code_match.group(1)

        # 借用人取件
        client.post(
            "/auth/logout",
            data={"csrf_token": get_csrf_token(page)},
            follow_redirects=True,
        )
        _http_login(client, borrower_no)
        page = client.get(f"/requests/{request_id}").get_data(as_text=True)
        resp = client.post(
            f"/requests/{request_id}/confirm-handover",
            data={"csrf_token": get_csrf_token(page), "code": code},
            follow_redirects=True,
        )
        assert "借用中" in resp.get_data(as_text=True)

        # 归还 + 确认
        page = client.get(f"/requests/{request_id}").get_data(as_text=True)
        client.post(
            f"/requests/{request_id}/return",
            data={"csrf_token": get_csrf_token(page), "return_note": "已归还"},
            follow_redirects=True,
        )
        client.post(
            "/auth/logout",
            data={"csrf_token": get_csrf_token(page)},
            follow_redirects=True,
        )
        _http_login(client, owner_no)
        page = client.get(f"/requests/{request_id}").get_data(as_text=True)
        resp = client.post(
            f"/requests/{request_id}/confirm-return",
            data={"csrf_token": get_csrf_token(page), "condition_ok": "ok"},
            follow_redirects=True,
        )
        assert "借用已完成" in resp.get_data(as_text=True)


def _http_login(client, student_no):
    """登录三步：身份选择 → 学校校区选择 → 登录（名单已预注册）。"""
    from tests.integration.test_register_and_login import get_csrf_token

    page = client.get("/auth/identity").get_data(as_text=True)
    client.post(
        "/auth/identity",
        data={"csrf_token": get_csrf_token(page), "role": "student"},
        follow_redirects=True,
    )
    # 测试库仅一所高校两个校区（主校区在前）；提交第一组学校/校区选项
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
        data={"csrf_token": get_csrf_token(page), "identifier": student_no, "password": "student1"},
        follow_redirects=True,
    )
