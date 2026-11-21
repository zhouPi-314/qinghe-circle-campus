"""公开仓库静态数据安全检查。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_seed_does_not_publish_default_admin_credentials():
    seed = (PROJECT_ROOT / "sql" / "seed.sql").read_text(encoding="utf-8")
    generator = (PROJECT_ROOT / "tools" / "build_sichuan_university_data.py").read_text(
        encoding="utf-8"
    )

    assert "QingheAdmin2026" not in seed
    assert "QingheAdmin2026" not in generator
    assert "INSERT INTO users" not in seed
