"""公开文本 PII 规则检测（G4 加固，D-039）。

范围（课堂可演示）：
- 识别中国大陆手机号（连续 11 位或 138-8000-1234 / 138 8000 1234 分隔形式）、
  18 位身份证号（含末位 X）、电子邮箱；
- 公开字段检测到 PII 时抛 InputError（默认拒绝提交，不静默改写原文）；
- 图片不做 OCR 或人脸识别，保留管理员人工核验（D-039）。

非目标：
- donor_note、request_note、争议 reason/message、内部审计说明等
  仅参与方或管理员可见的字段不做强制过滤；
- 避免把普通年份、数量、金额（如"2024级""100件""88.00元"）误判为 PII。
"""

from __future__ import annotations

import re

from app.core.errors import InputError

# 手机号：1[3-9] 开头共 11 位，兼容空格/连字符分隔（3-4-4 分组）
_PHONE_PATTERN = re.compile(r"(?<![\d-])1[3-9]\d[- ]?\d{4}[- ]?\d{4}(?![\d-])")

# 18 位身份证号：17 位数字 + 数字或 X（大小写均可），前后不能是数字
_ID_CARD_PATTERN = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")

# 电子邮箱
_EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+", re.IGNORECASE
)

_KIND_LABELS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("手机号", _PHONE_PATTERN),
    ("身份证号", _ID_CARD_PATTERN),
    ("邮箱", _EMAIL_PATTERN),
)

PII_REJECT_MESSAGE = "公开内容疑似包含{detail}，请删除联系方式或证件信息后再提交。"


def detect_pii(text: str) -> list[str]:
    """识别文本中的 PII 类型（如 ["手机号", "邮箱"]）；无命中返回空列表。"""
    if not text:
        return []
    value = str(text)
    return [label for label, pattern in _KIND_LABELS if pattern.search(value)]


def public_text_error(text: str) -> str | None:
    """公开文本检测：命中时返回用户可读的中文错误提示，未命中返回 None。"""
    kinds = detect_pii(text)
    if not kinds:
        return None
    return PII_REJECT_MESSAGE.format(detail="、".join(kinds))


def ensure_public_text_safe(text: str, field_name: str) -> None:
    """公开文本安全检查：检测到 PII 直接抛 InputError（默认拒绝，不自动改写）。"""
    error = public_text_error(text or "")
    if error:
        raise InputError(error, field_errors={field_name: error})
