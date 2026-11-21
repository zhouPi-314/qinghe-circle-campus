"""集成测试：健康检查、错误页、CSRF 与 schema 初始化。"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text

pytestmark = pytest.mark.integration


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["checks"]["database"] == "ok"

    def test_favicon_is_available(self, client):
        resp = client.get("/favicon.ico")
        assert resp.status_code == 200
        assert resp.mimetype == "image/svg+xml"


class TestSchemaInit:
    def test_all_27_tables_exist(self, app):
        with app.app_context():
            inspector = inspect(app.extensions["sqlalchemy"].engine)
            tables = set(inspector.get_table_names())
        expected = {
            "universities",
            "campuses",
            "users",
            "stations",
            "station_manager_assignments",
            "student_import_batches",
            "student_registry_records",
            "registration_verification_requests",
            "security_events",
            "security_blocks",
            "application_events",
            "login_verification_codes",
            "item_categories",
            "items",
            "item_images",
            "circulation_requests",
            "borrow_details",
            "sale_details",
            "recycle_details",
            "handover_records",
            "status_history",
            "notifications",
            "disputes",
            "dispute_messages",
            "audit_logs",
            "charity_projects",
            "charity_project_needs",
            "charity_donations",
            "charity_donation_items",
            "charity_receipts",
            "charity_receipt_items",
        }
        assert len(expected) == 31
        missing = expected - tables
        assert missing == set(), f"缺少表：{missing}"

    def test_active_request_partial_index_exists(self, app):
        """活动申请互斥的部分唯一索引必须存在（交接书第 8 节）。"""
        with app.app_context():
            result = (
                app.extensions["sqlalchemy"]
                .engine.connect()
                .execute(
                    text(
                        "SELECT indexname FROM pg_indexes "
                        "WHERE tablename = 'circulation_requests' "
                        "AND indexname = 'uq_active_request_per_item'"
                    )
                )
                .fetchall()
            )
        assert len(result) == 1


class TestErrorPages:
    def test_404_page_is_chinese_with_next_step(self, client):
        resp = client.get("/definitely-not-exists")
        assert resp.status_code == 404
        html = resp.get_data(as_text=True)
        assert "没有找到页面" in html
        assert "下一步" in html
        assert "返回首页" in html

    def test_csrf_missing_token_rejected(self, client):
        resp = client.post("/auth/identity", data={"role": "student"})
        assert resp.status_code == 400
        html = resp.get_data(as_text=True)
        assert "安全校验失败" in html
