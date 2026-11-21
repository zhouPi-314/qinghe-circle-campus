"""单元测试：纯业务逻辑，不访问数据库。"""

import pytest

from app.core.auth import is_valid_phone, normalize_phone
from app.core.errors import AppError, InputError
from app.services.auth_service import validate_password_strength


class TestPhoneNormalization:
    def test_normalize_keeps_digits_only(self):
        assert normalize_phone(" 138-8000-1234 ") == "13880001234"

    def test_valid_mainland_mobile(self):
        assert is_valid_phone("13880001234")
        assert is_valid_phone("19912345678")

    def test_invalid_numbers_rejected(self):
        assert not is_valid_phone("12345678901")  # 不以 1[3-9] 开头以外的规则由位数+1 开头近似
        assert not is_valid_phone("1388000123")  # 10 位
        assert not is_valid_phone("abc")
        assert not is_valid_phone("")


class TestPasswordPolicy:
    def test_valid_password_passes(self):
        validate_password_strength("abcd1234")

    def test_too_short_rejected(self):
        with pytest.raises(InputError) as excinfo:
            validate_password_strength("ab1")
        assert "8" in excinfo.value.field_errors["password"]

    def test_missing_letter_rejected(self):
        with pytest.raises(InputError):
            validate_password_strength("12345678")

    def test_missing_digit_rejected(self):
        with pytest.raises(InputError):
            validate_password_strength("abcdefgh")


class TestErrorTypes:
    def test_app_error_carries_title_and_message(self):
        err = AppError("发生错误", title="测试标题")
        assert err.status_code == 400
        assert err.message == "发生错误"
        assert err.title == "测试标题"

    def test_input_error_field_errors_default_empty(self):
        err = InputError("请检查输入")
        assert err.field_errors == {}
