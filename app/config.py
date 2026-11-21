"""应用配置：从环境变量加载，缺失必需项时快速失败。

环境变量只使用交接书第 10 节允许的 8 个名称；
值只放在 .env.local 或平台 Secret 中，不写入代码。
"""

from __future__ import annotations

import os
from pathlib import Path

# 允许的环境变量名称（交接书第 10 节）
ALLOWED_ENV_VARS = (
    "SECRET_KEY",
    "DATABASE_URL",
    "CLOUDFLARE_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET_NAME",
    "R2_ENDPOINT",
    "R2_PUBLIC_BASE_URL",
)

_REQUIRED = ("SECRET_KEY", "DATABASE_URL")

# 只允许 SQLAlchemy + psycopg 3 的连接串（postgresql:// 会被 SQLAlchemy 解析为 psycopg2）
_ALLOWED_DB_SCHEME = "postgresql+psycopg://"


def to_psycopg_dsn(url: str) -> str:
    """把 SQLAlchemy 风格连接串转为 psycopg 原生连接串。"""
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


def load_dotenv_file(path: Path) -> dict[str, str]:
    """读取 .env.local 之类的 KEY=VALUE 文件（不覆盖已存在的进程环境变量）。"""
    loaded: dict[str, str] = {}
    if not path.is_file():
        return loaded
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in ALLOWED_ENV_VARS and key not in os.environ and value:
            loaded[key] = value
            os.environ[key] = value
    return loaded


class Config:
    """集中配置；只保留允许的环境变量，未设置的保持 None。"""

    def __init__(self, project_root: Path | None = None) -> None:
        root = project_root or Path(__file__).resolve().parent.parent
        load_dotenv_file(root / ".env.local")

        self.secret_key: str | None = os.environ.get("SECRET_KEY")
        self.database_url: str | None = os.environ.get("DATABASE_URL")

        self.cloudflare_account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        self.r2_access_key_id = os.environ.get("R2_ACCESS_KEY_ID")
        self.r2_secret_access_key = os.environ.get("R2_SECRET_ACCESS_KEY")
        self.r2_bucket_name = os.environ.get("R2_BUCKET_NAME")
        self.r2_endpoint = os.environ.get("R2_ENDPOINT")
        self.r2_public_base_url = os.environ.get("R2_PUBLIC_BASE_URL")

        self.r2_configured = all(
            (
                self.r2_access_key_id,
                self.r2_secret_access_key,
                self.r2_bucket_name,
                self.r2_endpoint,
            )
        )

        self.testing = False

    def validate(self) -> None:
        """必需变量缺失时快速失败；不输出变量值。"""
        missing = [name for name in _REQUIRED if not getattr(self, name.lower())]
        if missing:
            raise RuntimeError(
                "缺少必需环境变量："
                + "、".join(missing)
                + "。请在 .env.local 或平台 Secret 中配置。"
            )
        if not self.database_url.startswith(_ALLOWED_DB_SCHEME):
            raise RuntimeError(
                "DATABASE_URL 必须使用 postgresql+psycopg:// 开头的 PostgreSQL 3 连接串。"
            )
        if len(self.secret_key) < 32:
            raise RuntimeError("SECRET_KEY 长度不足 32 字符，请更换更强的密钥。")


def flask_config_from(config: Config, *, testing: bool = False) -> dict:
    """生成 Flask/SQLAlchemy 所需的应用配置。"""
    values = {
        "SECRET_KEY": config.secret_key,
        "SQLALCHEMY_DATABASE_URI": config.database_url,
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        # 会话 Cookie：HttpOnly + SameSite + Secure（测试客户端除外）
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": not testing,
        "PERMANENT_SESSION_LIFETIME": 60 * 60 * 12,
        "TESTING": testing,
        # 工程标准第 5 节：生产环境关闭 debug 与自动重载；首版始终关闭
        "DEBUG": False,
        "PROPAGATE_EXCEPTIONS": False,
        # 默认时区显示（数据库存 UTC，页面按 Asia/Shanghai 显示）
        "DISPLAY_TIMEZONE": "Asia/Shanghai",
        # JSON 健康检查
        "JSON_AS_ASCII": False,
    }
    return values
