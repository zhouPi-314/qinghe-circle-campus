"""单元测试：公开文本 PII 规则检测（G4 加固，D-039）。"""

from __future__ import annotations

import pytest

from app.core.errors import InputError
from app.core.privacy import detect_pii, ensure_public_text_safe, public_text_error


class TestDetectPii:
    def test_compact_phone_detected(self):
        assert "手机号" in detect_pii("有疑问请联系13880001234")

    def test_separated_phone_with_hyphens_detected(self):
        assert "手机号" in detect_pii("电话 138-8000-1234 随时联系")

    def test_separated_phone_with_spaces_detected(self):
        assert "手机号" in detect_pii("联系方式：138 8000 1234")

    def test_id_card_detected(self):
        assert "身份证号" in detect_pii("证件号51010120000101123X")
        assert "身份证号" in detect_pii("身份证 510101200001011230")

    def test_email_detected(self):
        kinds = detect_pii("邮箱 example.user@mail.example.com")
        assert "邮箱" in kinds

    def test_multiple_kinds_all_reported(self):
        kinds = detect_pii("手机13880001234，邮箱 a@b.com")
        assert set(kinds) == {"手机号", "邮箱"}

    def test_plain_text_not_flagged(self):
        """普通年份、数量、金额不得误报（任务约束）。"""
        text = "2024级软件工程，目标100件，金额88.00元"
        assert detect_pii(text) == []

    def test_common_campus_text_not_flagged(self):
        assert detect_pii("九成新高等数学教材，可借两周") == []
        assert detect_pii("冬衣捐赠计划：目标 500 件，截止 2026-12-30") == []

    def test_image_filename_and_internal_note_not_flagged(self):
        """图片文件名与内部捐赠备注不触发公开字段规则（不在过滤范围）。"""
        assert detect_pii("receipt_3.png") == []
        assert detect_pii("items/9f2c1a6b.png") == []
        assert public_text_error("希望有帮助，祝顺利") is None


class TestEnsurePublicTextSafe:
    def test_clean_text_passes(self):
        ensure_public_text_safe("高等数学教材，九成新", "title")

    def test_phone_rejected_with_field_error(self):
        with pytest.raises(InputError) as exc_info:
            ensure_public_text_safe("联系我：13880001234", "title")
        message = str(exc_info.value)
        assert "手机号" in message
        assert "请删除联系方式" in message
        assert "title" in exc_info.value.field_errors

    def test_rejects_instead_of_rewriting(self):
        """默认拒绝提交，不静默自动改写原文。"""
        original = "找我：138-8000-1234"
        with pytest.raises(InputError):
            ensure_public_text_safe(original, "description")
        assert original == "找我：138-8000-1234"
