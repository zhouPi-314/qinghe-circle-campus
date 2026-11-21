"""数据库初始化工具：对目标库执行 sql/schema.sql 与 sql/seed.sql。

用法：
    .venv/Scripts/python tools/init_database.py            # schema + seed
    .venv/Scripts/python tools/init_database.py --schema-only
    .venv/Scripts/python tools/init_database.py --reset    # 先清空 public schema

- 连接串从 DATABASE_URL 读取（.env.local 或环境变量），不打印任何密钥；
- sql/schema.sql 是首版唯一数据库结构来源（交接书第 8 节）；
- 初始化后输出高校、校区和管理员账号的核对数量；
- 种子数据不创建管理员，使用 tools/create_platform_admin.py 安全初始化。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Config, to_psycopg_dsn  # noqa: E402


def run_sql_file(conn: psycopg.Connection, path: Path) -> None:
    conn.execute(path.read_text(encoding="utf-8"))


def verify_counts(conn: psycopg.Connection) -> dict[str, int]:
    queries = {
        "universities": "SELECT count(*) FROM universities",
        "campuses": "SELECT count(*) FROM campuses",
        "platform_admins": "SELECT count(*) FROM users WHERE role = 'platform_admin'",
    }
    counts = {}
    for name, sql in queries.items():
        try:
            counts[name] = conn.execute(sql).fetchone()[0]
        except psycopg.errors.UndefinedTable:
            counts[name] = 0
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化青禾流转数据库")
    parser.add_argument("--schema-only", action="store_true", help="只执行 schema.sql，不导入 seed")
    parser.add_argument("--reset", action="store_true", help="先清空 public schema 再初始化")
    args = parser.parse_args()

    config = Config(project_root=PROJECT_ROOT)
    config.validate()
    dsn = to_psycopg_dsn(config.database_url)

    schema_path = PROJECT_ROOT / "sql" / "schema.sql"
    seed_path = PROJECT_ROOT / "sql" / "seed.sql"

    with psycopg.connect(dsn, autocommit=True) as conn:
        if args.reset:
            print("清空 public schema ...")
            conn.execute("DROP SCHEMA public CASCADE")
            conn.execute("CREATE SCHEMA public")
        print(f"执行 {schema_path.name} ...")
        run_sql_file(conn, schema_path)
        if not args.schema_only and seed_path.is_file():
            print(f"执行 {seed_path.name} ...")
            run_sql_file(conn, seed_path)
        counts = verify_counts(conn)

    print("初始化完成。核对数量：")
    for name, count in counts.items():
        print(f"  {name}: {count}")
    expected = {"universities": 141, "campuses": 161, "platform_admins": 0}
    if not args.schema_only:
        mismatched = [k for k, v in expected.items() if counts.get(k) != v]
        if mismatched:
            print(f"警告：以下数量与预期不符：{mismatched}")
            return 1
        print("与预期一致（141 所高校 / 161 条校区 / 0 个平台管理员）。")
        print("请运行 tools/create_platform_admin.py 创建首个平台管理员。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
