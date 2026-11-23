"""应用配置：从环境变量加载，缺失必需项时快速失败。

环境变量只使用交接书第 10 节及 G5 扩展允许的名称；
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
    "SMS_PROVIDER",
    "ALIBABA_CLOUD_ACCESS_KEY_ID",
    "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
    "ALIYUN_PNVS_SIGN_NAME",
    "ALIYUN_PNVS_TEMPLATE_CODE",
    "ALIYUN_PNVS_REGION_ID",
    "TRUST_CLOUDFLARE_IP_HEADER",
    "CLOUDFLARE_ORIGIN_SECRET",
    "TURNSTILE_SITE_KEY",
    "TURNSTILE_SECRET_KEY",
    "LOGIN_VERIFICATION_ENABLED",
    "PUBLIC_ALLOWED_HOSTS",
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

        self.sms_provider = os.environ.get("SMS_PROVIDER", "mock").strip().lower()
        self.alibaba_cloud_access_key_id = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID")
        self.alibaba_cloud_access_key_secret = os.environ.get(
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET"
        )
        self.aliyun_pnvs_sign_name = os.environ.get("ALIYUN_PNVS_SIGN_NAME")
        self.aliyun_pnvs_template_code = os.environ.get("ALIYUN_PNVS_TEMPLATE_CODE")
        self.aliyun_pnvs_region_id = (
            os.environ.get("ALIYUN_PNVS_REGION_ID") or "cn-hangzhou"
        )
        self.vercel_env = os.environ.get("VERCEL_ENV")
        self.trust_cloudflare_ip_header = (
            os.environ.get("TRUST_CLOUDFLARE_IP_HEADER", "").strip().lower()
            in ("1", "true", "yes")
        )
        self.cloudflare_origin_secret = os.environ.get("CLOUDFLARE_ORIGIN_SECRET")
        self.turnstile_site_key = os.environ.get("TURNSTILE_SITE_KEY")
        self.turnstile_secret_key = os.environ.get("TURNSTILE_SECRET_KEY")
        self.turnstile_configured = bool(
            self.turnstile_site_key and self.turnstile_secret_key
        )
        verification_override = os.environ.get("LOGIN_VERIFICATION_ENABLED", "").strip().lower()
        self.login_verification_enabled = (
            verification_override in ("1", "true", "yes")
            if verification_override
            else None
        )
        self.public_allowed_hosts = tuple(
            host.strip().rstrip(".").lower()
            for host in os.environ.get("PUBLIC_ALLOWED_HOSTS", "").split(",")
            if host.strip()
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
        if self.sms_provider not in ("mock", "aliyun_pnvs"):
            raise RuntimeError("SMS_PROVIDER 只能是 mock 或 aliyun_pnvs。")
        if self.vercel_env == "production" and self.sms_provider == "mock":
            raise RuntimeError("Production 环境禁止使用 Mock SMS Provider。")
        if self.sms_provider == "aliyun_pnvs":
            missing = [
                name
                for name, value in (
                    ("ALIBABA_CLOUD_ACCESS_KEY_ID", self.alibaba_cloud_access_key_id),
                    (
                        "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
                        self.alibaba_cloud_access_key_secret,
                    ),
                    ("ALIYUN_PNVS_SIGN_NAME", self.aliyun_pnvs_sign_name),
                    ("ALIYUN_PNVS_TEMPLATE_CODE", self.aliyun_pnvs_template_code),
                )
                if not value
            ]
            if missing:
                raise RuntimeError(
                    "阿里云短信认证配置缺失：" + "、".join(missing)
                )
        if self.trust_cloudflare_ip_header and not self.cloudflare_origin_secret:
            raise RuntimeError(
                "启用 Cloudflare IP Header 时必须配置 CLOUDFLARE_ORIGIN_SECRET。"
            )
        if bool(self.turnstile_site_key) != bool(self.turnstile_secret_key):
            raise RuntimeError(
                "Cloudflare Turnstile 必须同时配置 TURNSTILE_SITE_KEY 和 TURNSTILE_SECRET_KEY。"
            )
        if (
            self.vercel_env == "production"
            and self.public_allowed_hosts
            and not self.cloudflare_origin_secret
        ):
            raise RuntimeError(
                "Production 限制公共 Host 时必须配置 CLOUDFLARE_ORIGIN_SECRET。"
            )


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
        "LOGIN_VERIFICATION_ENABLED": (
            not testing
            if config.login_verification_enabled is None
            else config.login_verification_enabled
        ),
        # JSON 健康检查
        "JSON_AS_ASCII": False,
    }
    return values
