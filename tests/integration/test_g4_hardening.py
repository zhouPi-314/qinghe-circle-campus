"""集成测试：G4 前加固（D-039）——并发一致性、恶意值校验、公开文本 PII。

覆盖：
- 高校枚举与 schema 对齐（专科可建、非法枚举拒绝）；
- review_donation / decide_request / simulate_payment 恶意值拒绝（4xx 中文错误）；
- 两个并发申请同一物品只有一个成功（物品行锁，BR-012）；
- 两个并发确认同一交接码只有一个成功（申请行锁 + 交接记录行锁）；
- 两个并发回执累计不超过 accepted_quantity（明细行升序锁）；
- HTTP 提交含手机号/邮箱的公开文本返回可读 4xx。
"""

from __future__ import annotations

import threading
from datetime import date, datetime, timedelta

import pytest

from tests.fixtures.helpers import (
    assign_manager,
    create_campus,
    create_category,
    create_import_batch,
    create_platform_admin,
    create_registry_record,
    create_station,
    create_station_manager_user,
    create_student_user,
    create_university,
)

pytestmark = pytest.mark.integration

TODAY = date(2026, 12, 1)

from app import db  # noqa: E402
from app.core.errors import (  # noqa: E402
    AppError,
    ConflictError,
    InputError,
)
from app.core.permissions import to_current_user  # noqa: E402
from app.models.circulation import CirculationRequest  # noqa: E402
from app.models.governance import Notification, StatusHistory  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import (  # noqa: E402
    charity_service,
    circulation_service,
    handover_service,
    org_service,
)

# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------


def _actor(app, user_id):
    with app.app_context():
        return to_current_user(db.session.get(User, user_id))


def _race(app, callables):
    """同时运行两个并发操作（各自线程独立 app_context/数据库连接）。

    返回 [("ok", value) | ("error", AppError), ...]；意外异常标记为 "exception"。
    """
    results: list = [None] * len(callables)
    barrier = threading.Barrier(len(callables))

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=15)
            with app.app_context():
                results[index] = ("ok", callables[index]())
        except AppError as err:
            results[index] = ("error", err)
        except Exception as exc:  # pragma: no cover - 意外失败由断言暴露
            results[index] = ("exception", exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(callables))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return results


def _assert_one_success(results) -> None:
    kinds = [kind for kind, _ in results]
    assert "exception" not in kinds, f"并发测试出现未预期异常：{results}"
    assert kinds.count("ok") == 1, f"应恰好一个成功，实际：{kinds}"
    assert kinds.count("error") == 1, f"应恰好一个被拒绝，实际：{kinds}"


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


@pytest.fixture
def hardening_world(app):
    """一所高校：两名学生 + 公益管理员与站点 + 分类 + HTTP 登录名单。"""
    with app.app_context():
        uni = create_university()
        campus = create_campus(uni)
        owner = create_student_user(
            uni, campus, student_no="2024601", nickname="所有者", phone="13900006001"
        )
        bidder = create_student_user(
            uni, campus, student_no="2024602", nickname="申请人", phone="13900006002"
        )
        manager = create_station_manager_user(uni, login_name="g4mgr", nickname="站点管理员")
        recycle_station = create_station(uni, campus, station_type="recycle")
        charity_station = create_station(uni, campus, station_type="charity", name="青禾公益站")
        assign_manager(recycle_station, manager)
        assign_manager(charity_station, manager)
        category = create_category()
        admin, _ = create_platform_admin()
        batch = create_import_batch(uni, admin)
        for student, phone in ((owner, "13800006001"), (bidder, "13800006002")):
            record = create_registry_record(
                uni, campus, batch, student_no=student.student_no, phone=phone
            )
            record.registered_user_id = student.id
        db.session.commit()
        yield {
            "university_id": uni.id,
            "campus_id": campus.id,
            "owner_id": owner.id,
            "bidder_id": bidder.id,
            "manager_id": manager.id,
            "admin_id": admin.id,
            "category_id": category.id,
            "recycle_station_id": recycle_station.id,
            "charity_station_id": charity_station.id,
        }


def _create_item(app, world, *, mode="borrow", title="高等数学教材"):
    from app.services import item_service

    with app.app_context():
        owner = _actor(app, world["owner_id"])
        item = item_service.create_item(
            owner,
            category_id=world["category_id"],
            mode=mode,
            title=title,
            description="九成新，仅供本校同学流转。",
            condition="like_new",
            campus_id=world["campus_id"],
            sale_price_cents=1000 if mode == "sale" else None,
        )
        return item.id


# ---------------------------------------------------------------------------
# 一、高校枚举
# ---------------------------------------------------------------------------


class TestUniversityEnum:
    def test_create_college_university(self, app, hardening_world):
        with app.app_context():
            admin = _actor(app, hardening_world["admin_id"])
            uni = org_service.create_university(
                admin,
                code="519901",
                name="测试专科院校",
                province="四川省",
                city="成都市",
                education_level="college",
                ownership="private",
            )
            assert uni.education_level == "college"

    def test_invalid_education_level_rejected(self, app, hardening_world):
        with app.app_context():
            admin = _actor(app, hardening_world["admin_id"])
            with pytest.raises(InputError):
                org_service.create_university(
                    admin,
                    code="519902",
                    name="枚举外高校",
                    province="四川省",
                    city="成都市",
                    education_level="vocational",  # schema 不支持该值
                    ownership="public",
                )

    def test_invalid_ownership_rejected(self, app, hardening_world):
        with app.app_context():
            admin = _actor(app, hardening_world["admin_id"])
            with pytest.raises(InputError):
                org_service.create_university(
                    admin,
                    code="519903",
                    name="枚举外高校",
                    province="四川省",
                    city="成都市",
                    education_level="undergraduate",
                    ownership="sino_foreign",  # schema 不支持该值
                )


# ---------------------------------------------------------------------------
# 二、恶意值校验（4xx 中文错误，不 500）
# ---------------------------------------------------------------------------


class TestMaliciousValues:
    def _prepare_pending_borrow(self, app, world):
        item_id = _create_item(app, world)
        with app.app_context():
            bidder = _actor(app, world["bidder_id"])
            request = circulation_service.request_borrow(
                bidder, item_id, start_date=TODAY, due_date=TODAY + timedelta(days=7)
            )
            return request.id

    def test_negative_accepted_quantity_rejected(self, app, hardening_world):
        """核验确认数量为负数直接 InputError，不允许负累加（G4 加固）。"""
        from datetime import UTC as _UTC

        with app.app_context():
            manager = _actor(app, hardening_world["manager_id"])
            project = charity_service.create_project(
                manager,
                title="冬衣捐赠计划",
                description="募集过冬衣物",
                recipient_org="青禾公益合作组织",
                public_summary="物资统一消毒后发放",
                deadline=datetime.now(_UTC) + timedelta(days=30),
                needs=[
                    {
                        "item_category_id": hardening_world["category_id"],
                        "item_name": "冬季外套",
                        "target_quantity": 10,
                    }
                ],
            )
            project_id, need_id = project.id, project.needs[0].id
        with app.app_context():
            donor = _actor(app, hardening_world["owner_id"])
            donation = charity_service.submit_donation(
                donor,
                project_id,
                station_id=hardening_world["charity_station_id"],
                items=[{"need_id": need_id, "quantity": 3, "condition": "good"}],
            )
            donation_id, donation_item_id = donation.id, donation.items[0].id
        with app.app_context():
            manager = _actor(app, hardening_world["manager_id"])
            with pytest.raises(InputError):
                charity_service.review_donation(
                    manager,
                    donation_id,
                    accept=True,
                    accepted_quantities={donation_item_id: -2},
                )
            # 未写入任何进度
            from app.models.charity import CharityProjectNeed

            need = db.session.get(CharityProjectNeed, need_id)
            assert need.accepted_quantity == 0

    def test_invalid_decision_input_error(self, app, hardening_world):
        request_id = self._prepare_pending_borrow(app, hardening_world)
        with app.app_context():
            owner = _actor(app, hardening_world["owner_id"])
            with pytest.raises(InputError):
                circulation_service.decide_request(owner, request_id, decision="hack")

    def test_invalid_payment_outcome_input_error(self, app, hardening_world):
        request_id = self._prepare_pending_borrow(app, hardening_world)
        with app.app_context():
            owner = _actor(app, hardening_world["owner_id"])
            circulation_service.decide_request(owner, request_id, decision="accept")
        with app.app_context():
            bidder = _actor(app, hardening_world["bidder_id"])
            with pytest.raises(InputError):
                circulation_service.simulate_payment(bidder, request_id, outcome="refund")

    def test_http_invalid_decision_returns_400(self, client, app, hardening_world):
        """HTTP 提交恶意 decision：可读 400 中文错误页，不是 500。"""
        from tests.integration.test_register_and_login import get_csrf_token

        request_id = self._prepare_pending_borrow(app, hardening_world)
        _login_student(client, hardening_world)
        page = client.get(f"/requests/{request_id}").get_data(as_text=True)
        resp = client.post(
            f"/requests/{request_id}/decide",
            data={"csrf_token": get_csrf_token(page), "decision": "hack"},
        )
        assert resp.status_code == 400
        assert "无效" in resp.get_data(as_text=True)
        assert resp.status_code != 500

    def test_http_invalid_payment_outcome_returns_400(self, client, app, hardening_world):
        from tests.integration.test_register_and_login import get_csrf_token

        request_id = self._prepare_pending_borrow(app, hardening_world)
        with app.app_context():
            owner = _actor(app, hardening_world["owner_id"])
            circulation_service.decide_request(owner, request_id, decision="accept")
        _login_student(client, hardening_world)
        page = client.get(f"/requests/{request_id}").get_data(as_text=True)
        resp = client.post(
            f"/requests/{request_id}/pay",
            data={"csrf_token": get_csrf_token(page), "outcome": "steal"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 三、并发加固
# ---------------------------------------------------------------------------


class TestConcurrentItemRequest:
    def test_two_concurrent_borrow_requests_only_one_succeeds(self, app, hardening_world):
        """两个并发借用申请：一个成功，另一个得到 ConflictError（BR-012）。"""
        item_id = _create_item(app, hardening_world)

        def apply():
            bidder = _actor(app, hardening_world["bidder_id"])
            request = circulation_service.request_borrow(
                bidder, item_id, start_date=TODAY, due_date=TODAY + timedelta(days=7)
            )
            return request.id

        results = _race(app, [apply, apply])
        _assert_one_success(results)
        loser = next(err for kind, err in results if kind == "error")
        assert isinstance(loser, ConflictError)
        assert "已被其他人申请" in str(loser)
        with app.app_context():
            count = db.session.scalar(
                db.select(db.func.count()).select_from(CirculationRequest)
            )
            assert count == 1

    def test_concurrent_mixed_mode_requests_only_one_succeeds(self, app, hardening_world):
        """不同模式的两个并发申请同样互斥（借用 + 购买竞争同一物品）。"""
        item_id = _create_item(app, hardening_world, mode="sale")

        def apply_borrow():
            bidder = _actor(app, hardening_world["bidder_id"])
            request = circulation_service.request_borrow(
                bidder, item_id, start_date=TODAY, due_date=TODAY + timedelta(days=7)
            )
            return request.id

        def apply_purchase():
            bidder = _actor(app, hardening_world["bidder_id"])
            request = circulation_service.request_purchase(bidder, item_id)
            return request.id

        results = _race(app, [apply_borrow, apply_purchase])
        _assert_one_success(results)
        with app.app_context():
            count = db.session.scalar(
                db.select(db.func.count()).select_from(CirculationRequest)
            )
            assert count == 1


class TestConcurrentHandoverConfirm:
    def test_two_concurrent_confirms_only_one_succeeds(self, app, hardening_world):
        """两个并发确认同一交接码：一个成功；历史与通知只增加一次（BR-018）。"""
        item_id = _create_item(app, hardening_world)
        with app.app_context():
            bidder = _actor(app, hardening_world["bidder_id"])
            request = circulation_service.request_borrow(
                bidder, item_id, start_date=TODAY, due_date=TODAY + timedelta(days=7)
            )
            request_id = request.id
        with app.app_context():
            owner = _actor(app, hardening_world["owner_id"])
            circulation_service.decide_request(owner, request_id, decision="accept")
        with app.app_context():
            owner = _actor(app, hardening_world["owner_id"])
            _, code = handover_service.issue_handover_code(owner, request_id)

        def confirm():
            bidder = _actor(app, hardening_world["bidder_id"])
            return handover_service.confirm_handover(bidder, request_id, code=code)

        results = _race(app, [confirm, confirm])
        _assert_one_success(results)
        loser = next(err for kind, err in results if kind == "error")
        assert isinstance(loser, ConflictError)

        with app.app_context():
            # 状态历史：交接成功记录只写一次
            handover_history = db.session.scalars(
                db.select(StatusHistory).where(
                    StatusHistory.entity_type == "circulation_request",
                    StatusHistory.entity_id == request_id,
                    StatusHistory.to_status == "in_progress",
                )
            ).all()
            assert len(handover_history) == 1
            # 成功交接通知只发送一次
            notifications = db.session.scalars(
                db.select(Notification).where(
                    Notification.category == "handover",
                    Notification.title == "物品已交接",
                    Notification.related_entity_id == request_id,
                )
            ).all()
            assert len(notifications) == 1


class TestConcurrentReceipt:
    def test_concurrent_receipts_never_exceed_accepted(self, app, hardening_world):
        """两个并发回执累计同一明细：总量不超过 accepted_quantity（BR-038）。"""
        from datetime import UTC as _UTC

        with app.app_context():
            manager = _actor(app, hardening_world["manager_id"])
            project = charity_service.create_project(
                manager,
                title="图书捐赠计划",
                description="募集课外读物",
                recipient_org="青禾公益合作组织",
                public_summary="图书将送往受助学校图书角",
                deadline=datetime.now(_UTC) + timedelta(days=30),
                needs=[
                    {
                        "item_category_id": hardening_world["category_id"],
                        "item_name": "课外读物",
                        "target_quantity": 10,
                    }
                ],
            )
            project_id, need_id = project.id, project.needs[0].id
        with app.app_context():
            donor = _actor(app, hardening_world["owner_id"])
            donation = charity_service.submit_donation(
                donor,
                project_id,
                station_id=hardening_world["charity_station_id"],
                items=[{"need_id": need_id, "quantity": 3, "condition": "good"}],
            )
            donation_id, donation_item_id = donation.id, donation.items[0].id
        with app.app_context():
            manager = _actor(app, hardening_world["manager_id"])
            charity_service.review_donation(manager, donation_id, accept=True)

        common = dict(
            project_id=project_id,
            station_id=hardening_world["charity_station_id"],
            recipient_org="青禾公益合作组织",
            received_at=datetime.now(_UTC),
        )

        def publish(batch_title):
            manager = _actor(app, hardening_world["manager_id"])
            receipt = charity_service.publish_receipt(
                manager,
                title=batch_title,
                public_note="物资已消毒并分批发放。",
                items=[{"donation_item_id": donation_item_id, "quantity": 2}],
                **common,
            )
            return receipt.id

        results = _race(app, [lambda: publish("第一批回执"), lambda: publish("第二批回执")])
        _assert_one_success(results)
        with app.app_context():
            from app.models.charity import CharityReceiptItem

            total = db.session.scalar(
                db.select(db.func.coalesce(db.func.sum(CharityReceiptItem.quantity), 0)).where(
                    CharityReceiptItem.donation_item_id == donation_item_id
                )
            )
            assert total <= 3


# ---------------------------------------------------------------------------
# 四、公开文本 PII（HTTP 层）
# ---------------------------------------------------------------------------


def _login_student(client, world) -> None:
    """学生身份 HTTP 登录（名单记录已在夹具中挂到既有账号）。"""
    from tests.integration.test_register_and_login import get_csrf_token

    page = client.get("/auth/identity").get_data(as_text=True)
    client.post(
        "/auth/identity",
        data={"csrf_token": get_csrf_token(page), "role": "student"},
        follow_redirects=True,
    )
    page = client.get("/auth/student-context").get_data(as_text=True)
    client.post(
        "/auth/student-context",
        data={
            "csrf_token": get_csrf_token(page),
            "university_id": str(world["university_id"]),
            "campus_id": str(world["campus_id"]),
        },
        follow_redirects=True,
    )
    page = client.get("/auth/login").get_data(as_text=True)
    client.post(
        "/auth/login",
        data={
            "csrf_token": get_csrf_token(page),
            "identifier": "2024601",
            "password": "student1",
        },
        follow_redirects=True,
    )


def _login_manager(client, world) -> None:
    """公益管理员（回收）HTTP 登录。"""
    from tests.integration.test_register_and_login import get_csrf_token

    page = client.get("/auth/identity").get_data(as_text=True)
    client.post(
        "/auth/identity",
        data={"csrf_token": get_csrf_token(page), "role": "station_manager"},
        follow_redirects=True,
    )
    page = client.get("/auth/login").get_data(as_text=True)
    client.post(
        "/auth/login",
        data={
            "csrf_token": get_csrf_token(page),
            "identifier": "g4mgr",
            "password": "station1",
        },
        follow_redirects=True,
    )


class TestPublicTextPiiHttp:
    def test_item_title_with_phone_rejected_400(self, client, app, hardening_world):
        """发布物品名称含手机号：可读 400 中文错误（D-039）。"""
        from tests.integration.test_register_and_login import get_csrf_token

        _login_student(client, hardening_world)
        page = client.get("/items/new").get_data(as_text=True)
        resp = client.post(
            "/items/new",
            data={
                "csrf_token": get_csrf_token(page),
                "title": "九成新自行车，联系我13880001234",
                "description": "车况良好，欢迎自取。",
                "mode": "borrow",
                "condition": "good",
                "category_id": str(hardening_world["category_id"]),
                "campus_id": str(hardening_world["campus_id"]),
            },
        )
        body = resp.get_data(as_text=True)
        assert resp.status_code == 400
        assert "手机号" in body
        assert "请删除联系方式" in body

    def test_project_summary_with_email_rejected_400(self, client, app, hardening_world):
        """公益项目公开说明含邮箱：可读 400 中文错误。"""
        from tests.integration.test_register_and_login import get_csrf_token

        _login_manager(client, hardening_world)
        page = client.get("/charity/projects/new").get_data(as_text=True)
        resp = client.post(
            "/charity/projects/new",
            data={
                "csrf_token": get_csrf_token(page),
                "title": "图书募集计划",
                "description": "募集课外读物",
                "recipient_org": "青禾公益合作组织",
                "public_summary": "有问题邮件联系 donate@example.com",
                "deadline": "2026-12-31T23:59",
            },
        )
        body = resp.get_data(as_text=True)
        assert resp.status_code == 400
        assert "邮箱" in body

    def test_receipt_note_with_phone_rejected_400(self, client, app, hardening_world):
        """回执说明含手机号：可读 400 中文错误（BR-039）。"""
        from datetime import UTC as _UTC

        # 服务层准备：项目 + 已接收捐赠
        with app.app_context():
            manager = _actor(app, hardening_world["manager_id"])
            project = charity_service.create_project(
                manager,
                title="冬衣捐赠计划",
                description="募集过冬衣物",
                recipient_org="青禾公益合作组织",
                public_summary="物资统一消毒后发放",
                deadline=datetime.now(_UTC) + timedelta(days=30),
                needs=[
                    {
                        "item_category_id": hardening_world["category_id"],
                        "item_name": "冬季外套",
                        "target_quantity": 10,
                    }
                ],
            )
            project_id, need_id = project.id, project.needs[0].id
        with app.app_context():
            donor = _actor(app, hardening_world["owner_id"])
            donation = charity_service.submit_donation(
                donor,
                project_id,
                station_id=hardening_world["charity_station_id"],
                items=[{"need_id": need_id, "quantity": 2, "condition": "good"}],
            )
            donation_id, donation_item_id = donation.id, donation.items[0].id
        with app.app_context():
            manager = _actor(app, hardening_world["manager_id"])
            charity_service.review_donation(manager, donation_id, accept=True)

        _login_manager(client, hardening_world)
        page = client.get(
            f"/station/receipts/new?project_id={project_id}"
        ).get_data(as_text=True)
        from tests.integration.test_register_and_login import get_csrf_token

        resp = client.post(
            "/station/receipts/new",
            data={
                "csrf_token": get_csrf_token(page),
                "project_id": str(project_id),
                "station_id": str(hardening_world["charity_station_id"]),
                "title": "第一批回执",
                "recipient_org": "青禾公益合作组织",
                "received_at": "2026-12-01T10:00",
                "public_note": "收货请联系 13880001234",
                f"receipt_{donation_item_id}": "2",
            },
        )
        body = resp.get_data(as_text=True)
        assert resp.status_code == 400
        assert "手机号" in body
