"""集成测试夹具：真实 PostgreSQL（本地，符合 D-001）。

- 每次测试运行使用独立测试库（qinghe_circle_test_<pid>），
  避免多个 pytest 进程并发时互相删库或 schema 锁冲突；
- 每次会话重建 public schema 并执行 sql/schema.sql（唯一结构来源）；
- 每个测试结束后从 pg_tables 动态清空业务表（不复制表结构定义）；
- 会话结束后删除本次测试库，保持数据库环境干净。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app, db  # noqa: E402
from app.config import load_dotenv_file, to_psycopg_dsn  # noqa: E402

load_dotenv_file(PROJECT_ROOT / ".env.local")


def _split_database_url(url: str) -> tuple[str, str]:
    """把 URL 拆成 (不含库名的前缀, 库名)。"""
    marker = url.rfind("/")
    return url[: marker + 1], url[marker + 1 :]


def _drop_database(dev_url: str, db_name: str) -> None:
    """断开目标库连接后删除（尽力而为，失败不影响测试结论）。"""
    prefix, _ = _split_database_url(dev_url)
    dev_dsn = to_psycopg_dsn(f"{prefix}postgres")
    try:
        with psycopg.connect(dev_dsn, autocommit=True) as conn:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (db_name,),
            )
            conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
    except psycopg.Error:
        pass


@pytest.fixture(scope="session")
def app():
    dev_url = os.environ["DATABASE_URL"]
    prefix, _ = _split_database_url(dev_url)
    # 每次运行独立测试库：进程号后缀，避免并发运行互相破坏
    test_db_name = f"qinghe_circle_test_{os.getpid()}"
    test_url = f"{prefix}{test_db_name}"

    with psycopg.connect(to_psycopg_dsn(dev_url), autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{test_db_name}"')

    # Config 优先读取进程环境变量，确保应用连接本次测试库
    os.environ["DATABASE_URL"] = test_url
    application = create_app(testing=True)

    schema_path = PROJECT_ROOT / "sql" / "schema.sql"
    with application.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql("DROP SCHEMA public CASCADE")
            conn.exec_driver_sql("CREATE SCHEMA public")
        # schema.sql 自带 BEGIN/COMMIT，用 autocommit 连接执行
        raw = db.engine.raw_connection()
        try:
            raw.autocommit = True
            with raw.cursor() as cur:
                cur.execute(schema_path.read_text(encoding="utf-8"))
        finally:
            raw.close()

    try:
        yield application
    finally:
        try:
            with application.app_context():
                db.engine.dispose()
        except Exception:
            pass
        _drop_database(dev_url, test_db_name)
        # 恢复开发库连接串，避免影响同进程后续工具
        os.environ["DATABASE_URL"] = dev_url


@pytest.fixture(autouse=True)
def clean_tables(app):
    """每个测试结束后清空 public 下全部业务表（表名从数据库动态获取，不复制结构定义）。"""
    yield
    with app.app_context():
        from sqlalchemy import text

        with db.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).fetchall()
        tables = sorted(row[0] for row in rows)
        if not tables:
            return
        quoted = ", ".join(f'"{name}"' for name in tables)
        with db.engine.begin() as conn:
            conn.exec_driver_sql(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE")


@pytest.fixture
def client(app):
    return app.test_client()
