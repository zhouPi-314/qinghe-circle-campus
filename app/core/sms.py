"""SMS provider seam for registration verification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

MOCK_SMS_CODE = "123456"


class SmsProviderError(RuntimeError):
    """Safe provider failure whose message never contains provider details."""


@dataclass(frozen=True)
class SmsSendResult:
    provider: str
    message_id: str | None


class SmsSender(Protocol):
    display_code: str | None

    def send_register_code(self, phone: str, out_id: str) -> SmsSendResult: ...

    def verify_register_code(self, phone: str, code: str, out_id: str) -> bool: ...


class MockSmsSender:
    """Deterministic local sender used by tests and non-Production demos."""

    display_code = MOCK_SMS_CODE

    def __init__(self) -> None:
        self._challenges: dict[str, str] = {}

    def send_register_code(self, phone: str, out_id: str) -> SmsSendResult:
        self._challenges[out_id] = phone
        return SmsSendResult(provider="mock", message_id=f"mock-{out_id}")

    def verify_register_code(self, phone: str, code: str, out_id: str) -> bool:
        expected_phone = self._challenges.get(out_id)
        return expected_phone == phone and code == MOCK_SMS_CODE


class AliyunPnvsSmsSender:
    """Aliyun Phone Number Verification SMS Authentication provider."""

    display_code = None

    def __init__(self, config, *, client=None) -> None:
        self._config = config
        if client is not None:
            self._client = client
            return

        from alibabacloud_dypnsapi20170525.client import Client
        from alibabacloud_tea_openapi import models as open_api_models

        client_config = open_api_models.Config(
            access_key_id=config.alibaba_cloud_access_key_id,
            access_key_secret=config.alibaba_cloud_access_key_secret,
            region_id=config.aliyun_pnvs_region_id,
        )
        client_config.endpoint = "dypnsapi.aliyuncs.com"
        self._client = Client(client_config)

    def send_register_code(self, phone: str, out_id: str) -> SmsSendResult:
        from alibabacloud_dypnsapi20170525 import models

        request = models.SendSmsVerifyCodeRequest(
            country_code="86",
            phone_number=phone,
            sign_name=self._config.aliyun_pnvs_sign_name,
            template_code=self._config.aliyun_pnvs_template_code,
            template_param='{"code":"##code##","min":"5"}',
            out_id=out_id,
            code_length=6,
            code_type=1,
            interval=60,
            valid_time=300,
            duplicate_policy=1,
            return_verify_code=False,
            auto_retry=1,
        )
        try:
            response = self._client.send_sms_verify_code(request)
        except Exception:
            raise SmsProviderError("短信服务暂时不可用，请稍后重试。") from None

        body = response.body
        if body is None or body.code != "OK" or not body.success:
            raise SmsProviderError("短信发送失败，请稍后重试。")
        message_id = body.model.biz_id if body.model is not None else None
        return SmsSendResult(provider="aliyun_pnvs", message_id=message_id)

    def verify_register_code(self, phone: str, code: str, out_id: str) -> bool:
        from alibabacloud_dypnsapi20170525 import models

        request = models.CheckSmsVerifyCodeRequest(
            country_code="86",
            phone_number=phone,
            out_id=out_id,
            verify_code=code,
            case_auth_policy=1,
        )
        try:
            response = self._client.check_sms_verify_code(request)
        except Exception as error:
            if getattr(error, "code", None) == "isv.ValidateFail":
                return False
            raise SmsProviderError("短信核验服务暂时不可用，请稍后重试。") from None

        body = response.body
        if body is None or body.code != "OK" or not body.success:
            raise SmsProviderError("短信核验失败，请稍后重试。")
        return bool(body.model is not None and body.model.verify_result == "PASS")


def sms_sender_from_config(config) -> SmsSender:
    if config.testing or config.sms_provider == "mock":
        return MockSmsSender()
    if config.sms_provider == "aliyun_pnvs":
        return AliyunPnvsSmsSender(config)
    raise RuntimeError("SMS_PROVIDER 配置无效。")
