"""真实 Cloudflare R2 上传 smoke test（交接书第 10 节、工程标准第 6 节）。

- R2 凭据齐全时执行真实写入：上传 → 读回校验 → 删除清理；
- 未配置凭据（如 CI 无密钥）时 skip，不伪造通过结论。
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from app.config import load_dotenv_file
from app.core.storage import R2Storage, StorageError, validate_image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv_file(PROJECT_ROOT / ".env.local")

_R2_VARS = ("CLOUDFLARE_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME")
_HAS_R2 = all(os.environ.get(v) for v in _R2_VARS)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _HAS_R2, reason="R2 凭据未配置，跳过真实上传 smoke test"),
]

# 1x1 PNG（带合法签名），远小于 3MB
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffff3f0300050201ffc3cdd8550000000049454e44ae426082"
)


def test_r2_put_get_delete_roundtrip():
    validate_image(TINY_PNG, "image/png")
    storage = R2Storage(
        account_id=os.environ["CLOUDFLARE_ACCOUNT_ID"],
        access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        bucket_name=os.environ["R2_BUCKET_NAME"],
    )

    key = storage.put_image(TINY_PNG, "image/png")
    assert key.startswith("items/") and key.endswith(".png")

    # 读回校验：对象内容与上传一致
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['CLOUDFLARE_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    )
    try:
        obj = client.get_object(Bucket=os.environ["R2_BUCKET_NAME"], Key=key)
        assert obj["Body"].read() == TINY_PNG
    finally:
        client.delete_object(Bucket=os.environ["R2_BUCKET_NAME"], Key=key)

    # 删除后读回应失败（清理成功）
    from botocore.exceptions import ClientError

    with pytest.raises(ClientError):
        client.get_object(Bucket=os.environ["R2_BUCKET_NAME"], Key=key)

    # 附：伪造内容在真实存储入口同样被拒（不出网）
    with pytest.raises(StorageError):
        storage.put_image(b"not-an-image", "image/jpeg")


def test_r2_key_uniqueness():
    import boto3

    storage = R2Storage(
        account_id=os.environ["CLOUDFLARE_ACCOUNT_ID"],
        access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        bucket_name=os.environ["R2_BUCKET_NAME"],
    )
    # 校验 key 生成逻辑：两次上传得到不同 key（随机 UUID），不覆盖既有对象
    keys = set()
    try:
        for _ in range(2):
            keys.add(storage.put_image(TINY_PNG, "image/png"))
        assert len(keys) == 2
        assert len({uuid.UUID(k.split("/")[1].split(".")[0]) for k in keys}) == 2
    finally:
        # try/finally：断言失败也必须清理测试遗留对象（不输出密钥与连接串）
        client = boto3.client(
            "s3",
            endpoint_url=f"https://{os.environ['CLOUDFLARE_ACCOUNT_ID']}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        )
        for key in keys:
            try:
                client.delete_object(Bucket=os.environ["R2_BUCKET_NAME"], Key=key)
            except Exception:
                # 清理失败不掩盖测试结论；仅记录不含密钥的警告
                import logging

                logging.getLogger("qinghe.tests.r2").warning(
                    "R2 smoke 清理对象失败：key=%s", key
                )
