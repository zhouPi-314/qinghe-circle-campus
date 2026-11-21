"""单元测试：文件与图片存储（交接书第 10 节）。

- validate_image：类型、大小与**文件签名**校验（不信任浏览器 MIME）；
- FakeStorage：测试假存储行为；
- R2Storage：mock boto3 客户端验证上传行为（不出网）。
"""

from __future__ import annotations

import pytest

from app.core.storage import (
    FakeStorage,
    R2Storage,
    StorageError,
    validate_image,
)

# 最小合法文件签名样本
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP_BYTES = b"RIFF\x24\x00\x00\x00WEBP" + b"\x00" * 16
FAKE_BYTES = b"this-is-not-an-image" * 4


class TestValidateImage:
    def test_valid_types_pass(self):
        for content, mime in (
            (PNG_BYTES, "image/png"),
            (JPEG_BYTES, "image/jpeg"),
            (WEBP_BYTES, "image/webp"),
        ):
            validate_image(content, mime)

    def test_disallowed_mime_rejected(self):
        with pytest.raises(StorageError):
            validate_image(PNG_BYTES, "image/gif")

    def test_empty_rejected(self):
        with pytest.raises(StorageError):
            validate_image(b"", "image/png")

    def test_oversize_rejected(self):
        with pytest.raises(StorageError):
            validate_image(PNG_BYTES + b"\x00" * (3 * 1024 * 1024), "image/png")

    def test_forged_mime_rejected(self):
        """任意内容伪装成 image/jpeg 必须被文件签名检查拒绝。"""
        with pytest.raises(StorageError):
            validate_image(FAKE_BYTES, "image/jpeg")
        with pytest.raises(StorageError):
            validate_image(b"GIF89a" + FAKE_BYTES, "image/png")
        with pytest.raises(StorageError):
            validate_image(b"%PDF-1.4 fake", "image/webp")

    def test_truncated_signature_rejected(self):
        """签名前缀不足或错位拒绝。"""
        with pytest.raises(StorageError):
            validate_image(b"\x89PNG", "image/png")  # 缺完整 PNG 头


class TestFakeStorage:
    def test_put_and_key_format(self):
        storage = FakeStorage()
        key = storage.put_image(PNG_BYTES, "image/png")
        assert key.startswith("fake/") and key.endswith(".png")
        assert storage.objects[key] == PNG_BYTES

    def test_put_validates_content(self):
        storage = FakeStorage()
        with pytest.raises(StorageError):
            storage.put_image(FAKE_BYTES, "image/jpeg")

    def test_fail_next(self):
        storage = FakeStorage()
        storage.fail_next = True
        with pytest.raises(StorageError):
            storage.put_image(PNG_BYTES, "image/png")


class _FakeBoto3Client:
    """记录 put_object 调用的假客户端。"""

    def __init__(self):
        self.calls: list[dict] = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)


class TestR2Storage:
    def _make_storage(self, monkeypatch) -> tuple[R2Storage, _FakeBoto3Client]:
        client = _FakeBoto3Client()

        class _FakeBoto3Module:
            @staticmethod
            def client(*args, **kwargs):
                return client

        import sys

        monkeypatch.setitem(sys.modules, "boto3", _FakeBoto3Module())
        storage = R2Storage(
            account_id="test-account",
            access_key_id="test-key",
            secret_access_key="test-secret",
            bucket_name="test-bucket",
        )
        return storage, client

    def test_put_uploads_with_uuid_key(self, monkeypatch):
        storage, client = self._make_storage(monkeypatch)
        key = storage.put_image(PNG_BYTES, "image/png")
        assert key.startswith("items/") and key.endswith(".png")
        assert len(client.calls) == 1
        call = client.calls[0]
        assert call["Bucket"] == "test-bucket"
        assert call["Key"] == key
        assert call["Body"] == PNG_BYTES
        assert call["ContentType"] == "image/png"

    def test_put_rejects_forged_content(self, monkeypatch):
        storage, _client = self._make_storage(monkeypatch)
        with pytest.raises(StorageError):
            storage.put_image(FAKE_BYTES, "image/jpeg")

    def test_put_translates_client_errors(self, monkeypatch):
        storage, client = self._make_storage(monkeypatch)

        def _boom(**kwargs):
            raise RuntimeError("connection reset")

        client.put_object = _boom
        with pytest.raises(StorageError):
            storage.put_image(PNG_BYTES, "image/png")
