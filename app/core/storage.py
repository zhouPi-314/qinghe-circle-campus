"""文件与图片存储适配器（交接书第 10 节）。

- 生产：Cloudflare R2（S3-compatible，boto3），对象 key 使用随机 UUID；
- 测试：FakeStorage（字典实现，不出网）；
- 数据库只保存对象 key、类型、大小，不保存临时路径、URL 或密钥。
"""

from __future__ import annotations

import uuid
from typing import Protocol

ALLOWED_IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")
MAX_IMAGE_BYTES = 3 * 1024 * 1024  # 3 MB

_CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


class StorageError(Exception):
    """外部存储失败（保留表单允许重试，见全局错误分类）。"""


# 文件签名（magic bytes）：不信任浏览器提交的 MIME，按内容判型
_SIGNATURES: tuple[tuple[bytes, ...], ...] = (
    (b"\xff\xd8\xff",),  # JPEG
    (b"\x89PNG\r\n\x1a\n",),  # PNG
    (b"RIFF", b"WEBP"),  # WebP（RIFF....WEBP）
)


def _matches_signature(content: bytes) -> bool:
    for sig in _SIGNATURES:
        if content.startswith(sig[0]) and (len(sig) == 1 or content[8:12] == sig[1]):
            return True
    return False


class StorageAdapter(Protocol):
    def put_image(self, content: bytes, content_type: str) -> str:
        """写入图片并返回对象 key。"""
        ...


def validate_image(content: bytes, content_type: str) -> None:
    """图片校验（NFR-04）：类型与大小。

    content_type 只做入口粗筛；真实类型按文件签名（magic bytes）判断，
    任意内容伪装成 image/jpeg 会被拒绝。
    """
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise StorageError("图片只允许 JPEG、PNG 或 WebP 格式。")
    if not content:
        raise StorageError("图片内容为空。")
    if len(content) > MAX_IMAGE_BYTES:
        raise StorageError("单张图片不能超过 3 MB。")
    if not _matches_signature(content):
        raise StorageError("文件内容不是有效的 JPEG、PNG 或 WebP 图片。")


class R2Storage:
    """Cloudflare R2 存储适配器。"""

    def __init__(
        self, *, account_id: str, access_key_id: str, secret_access_key: str, bucket_name: str
    ) -> None:
        import boto3

        self._bucket = bucket_name
        endpoint = f"https://{account_id}.r2.cloudflarestorage.com" if account_id else None
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

    def put_image(self, content: bytes, content_type: str) -> str:
        validate_image(content, content_type)
        extension = _CONTENT_TYPE_EXTENSIONS[content_type]
        key = f"items/{uuid.uuid4().hex}.{extension}"
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
            )
        except Exception as exc:  # boto3 异常统一转译，不向外泄露凭据
            raise StorageError("图片上传到对象存储失败，请稍后重试。") from exc
        return key

    def delete_image(self, object_key: str) -> None:
        """删除对象（数据库提交失败时尽力清理；异常向上抛由调用方记录）。"""
        try:
            self._client.delete_object(Bucket=self._bucket, Key=object_key)
        except Exception as exc:  # 不向外泄露凭据
            raise StorageError("图片清理失败。") from exc


class FakeStorage:
    """单元测试用假存储（不出网、可注入、可断言）。"""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_next = False

    def put_image(self, content: bytes, content_type: str) -> str:
        validate_image(content, content_type)
        if self.fail_next:
            self.fail_next = False
            raise StorageError("模拟上传失败。")
        extension = _CONTENT_TYPE_EXTENSIONS[content_type]
        key = f"fake/{uuid.uuid4().hex}.{extension}"
        self.objects[key] = content
        return key

    def delete_image(self, object_key: str) -> None:
        self.objects.pop(object_key, None)


def storage_from_config(config) -> StorageAdapter:
    """按配置构建存储适配器；R2 未配置时抛出可读错误。"""
    if not getattr(config, "r2_configured", False):
        raise StorageError("对象存储未配置（缺少 R2 环境变量），暂不能上传图片。")
    return R2Storage(
        account_id=config.cloudflare_account_id,
        access_key_id=config.r2_access_key_id,
        secret_access_key=config.r2_secret_access_key,
        bucket_name=config.r2_bucket_name,
    )


def image_public_url(config, object_key: str) -> str | None:
    """受控公开读取地址（R2_PUBLIC_BASE_URL/key）；未配置时返回 None。"""
    base = getattr(config, "r2_public_base_url", None)
    if not base:
        return None
    return f"{base.rstrip('/')}/{object_key}"
