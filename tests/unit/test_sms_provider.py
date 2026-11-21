"""Mock and Aliyun PNVS SMS provider contracts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app import create_app
from app.config import Config
from app.core import sms


def _config(monkeypatch, root: Path, provider: str) -> Config:
    monkeypatch.setattr("app.config.load_dotenv_file", lambda _path: {})
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-with-at-least-32-chars")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/qinghe_test"
    )
    monkeypatch.setenv("SMS_PROVIDER", provider)
    monkeypatch.setenv("VERCEL_ENV", "development")
    return Config(project_root=root)


def _clear_aliyun_env(monkeypatch):
    for name in (
        "ALIBABA_CLOUD_ACCESS_KEY_ID",
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
        "ALIYUN_PNVS_SIGN_NAME",
        "ALIYUN_PNVS_TEMPLATE_CODE",
        "ALIYUN_PNVS_REGION_ID",
    ):
        monkeypatch.delenv(name, raising=False)


def test_mock_provider_sends_and_verifies_without_network():
    sender = sms.MockSmsSender()

    result = sender.send_register_code("13880001234", "request-1")

    assert result == sms.SmsSendResult(provider="mock", message_id="mock-request-1")
    assert sender.verify_register_code("13880001234", sms.MOCK_SMS_CODE, "request-1")
    assert not sender.verify_register_code("13880001234", "000000", "request-1")
    assert sender.display_code == sms.MOCK_SMS_CODE


def test_mock_provider_does_not_verify_other_phone():
    sender = sms.MockSmsSender()
    sender.send_register_code("13880001234", "request-1")

    assert not sender.verify_register_code("13900000000", sms.MOCK_SMS_CODE, "request-1")


def test_configuration_returns_mock_for_tests(monkeypatch, tmp_path):
    config = _config(monkeypatch, tmp_path, "mock")
    config.testing = True

    assert isinstance(sms.sms_sender_from_config(config), sms.MockSmsSender)


def test_app_factory_registers_mock_sender_in_testing():
    app = create_app(testing=True)

    assert isinstance(app.extensions["sms_sender"], sms.MockSmsSender)


def test_production_rejects_mock_provider(monkeypatch, tmp_path):
    config = _config(monkeypatch, tmp_path, "mock")
    monkeypatch.setenv("VERCEL_ENV", "production")
    config = Config(project_root=tmp_path)

    with pytest.raises(RuntimeError, match="Production"):
        config.validate()


def test_aliyun_provider_requires_complete_configuration(monkeypatch, tmp_path):
    _clear_aliyun_env(monkeypatch)
    config = _config(monkeypatch, tmp_path, "aliyun_pnvs")

    with pytest.raises(RuntimeError, match="ALIBABA_CLOUD"):
        config.validate()


class _FakePnvsClient:
    def __init__(self):
        self.send_request = None
        self.verify_request = None
        self.verify_result = "PASS"

    def send_sms_verify_code(self, request):
        self.send_request = request
        return SimpleNamespace(
            body=SimpleNamespace(
                success=True,
                code="OK",
                message="OK",
                model=SimpleNamespace(biz_id="biz-1"),
            )
        )

    def check_sms_verify_code(self, request):
        self.verify_request = request
        return SimpleNamespace(
            body=SimpleNamespace(
                success=True,
                code="OK",
                message="OK",
                model=SimpleNamespace(verify_result=self.verify_result),
            )
        )


def test_aliyun_pnvs_send_uses_system_generated_code(monkeypatch, tmp_path):
    config = _config(monkeypatch, tmp_path, "aliyun_pnvs")
    monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "test-id")
    monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "test-secret")
    monkeypatch.setenv("ALIYUN_PNVS_SIGN_NAME", "test-sign")
    monkeypatch.setenv("ALIYUN_PNVS_TEMPLATE_CODE", "100001")
    config = Config(project_root=tmp_path)
    client = _FakePnvsClient()
    sender = sms.AliyunPnvsSmsSender(config, client=client)

    result = sender.send_register_code("13880001234", "request-1")

    request = client.send_request
    assert result == sms.SmsSendResult(provider="aliyun_pnvs", message_id="biz-1")
    assert request.phone_number == "13880001234"
    assert request.template_param == '{"code":"##code##","min":"5"}'
    assert request.code_length == 6
    assert request.code_type == 1
    assert request.interval == 60
    assert request.valid_time == 300
    assert request.duplicate_policy == 1
    assert request.return_verify_code is False
    assert request.auto_retry == 1


def test_aliyun_pnvs_verification_passes_only_on_pass(monkeypatch, tmp_path):
    config = _config(monkeypatch, tmp_path, "aliyun_pnvs")
    monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "test-id")
    monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "test-secret")
    monkeypatch.setenv("ALIYUN_PNVS_SIGN_NAME", "test-sign")
    monkeypatch.setenv("ALIYUN_PNVS_TEMPLATE_CODE", "100001")
    config = Config(project_root=tmp_path)
    client = _FakePnvsClient()
    sender = sms.AliyunPnvsSmsSender(config, client=client)

    assert sender.verify_register_code("13880001234", "123456", "request-1") is True
    assert client.verify_request.out_id == "request-1"

    client.verify_result = "UNKNOWN"
    assert sender.verify_register_code("13880001234", "000000", "request-1") is False


def test_aliyun_validate_fail_is_a_wrong_code_not_outage(monkeypatch, tmp_path):
    config = _config(monkeypatch, tmp_path, "aliyun_pnvs")
    monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "test-id")
    monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "test-secret")
    monkeypatch.setenv("ALIYUN_PNVS_SIGN_NAME", "test-sign")
    monkeypatch.setenv("ALIYUN_PNVS_TEMPLATE_CODE", "100001")
    config = Config(project_root=tmp_path)

    class InvalidCodeClient:
        def check_sms_verify_code(self, _request):
            error = RuntimeError("provider detail")
            error.code = "isv.ValidateFail"
            raise error

    sender = sms.AliyunPnvsSmsSender(config, client=InvalidCodeClient())
    assert sender.verify_register_code("13880001234", "000000", "request-1") is False


def test_provider_failure_does_not_expose_phone_or_secret():
    class FailingClient:
        def send_sms_verify_code(self, _request):
            raise RuntimeError("sensitive upstream detail")

    sender = sms.AliyunPnvsSmsSender(
        SimpleNamespace(
            aliyun_pnvs_region_id="cn-hangzhou",
            aliyun_pnvs_sign_name="test-sign",
            aliyun_pnvs_template_code="100001",
        ),
        client=FailingClient(),
    )

    with pytest.raises(sms.SmsProviderError) as raised:
        sender.send_register_code("13880001234", "request-1")

    message = str(raised.value)
    assert "13880001234" not in message
    assert "sensitive upstream detail" not in message
