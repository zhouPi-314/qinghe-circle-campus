from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / ".qa" / "university-research" / "moe-2025.xlsx"
MOE_SOURCE_URL = (
    "http://www.moe.gov.cn/jyb_xxgk/s5743/s5744/202506/"
    "W020250627301230138068.xls"
)

CAMPUS_OVERRIDES = {
    "四川大学": {
        "source_url": "https://www.scu.edu.cn/index/syxx/xxjt.htm",
        "campuses": [
            ("WANGJIANG", "望江校区"),
            ("HUAXI", "华西校区"),
            ("JIANGAN", "江安校区"),
        ],
    },
    "西南交通大学": {
        "source_url": "https://www.swjtu.edu.cn/xxgk/xydt.htm",
        "campuses": [
            ("XIPU", "犀浦校区"),
            ("JIULI", "九里校区"),
            ("EASTERN", "东部（国际）校区"),
            ("EMEI", "峨眉校区"),
        ],
    },
    "电子科技大学": {
        "source_url": "https://www.uestc.edu.cn/",
        "campuses": [
            ("QINGSHUIHE", "清水河校区"),
            ("SHAHE", "沙河校区"),
            ("JIULIDI", "九里堤校区"),
        ],
    },
    "西南财经大学": {
        "source_url": "https://www.swufe.edu.cn/",
        "campuses": [
            ("LIULIN", "柳林校区"),
            ("GUANGHUA", "光华校区"),
        ],
    },
    "四川农业大学": {
        "source_url": "https://www.sicau.edu.cn/",
        "campuses": [
            ("YAAN", "雅安校区"),
            ("CHENGDU", "成都校区"),
            ("DUJIANGYAN", "都江堰校区"),
        ],
    },
    "西南石油大学": {
        "source_url": "https://xy.swpu.edu.cn/alumnus/back",
        "campuses": [
            ("CHENGDU", "成都校区"),
            ("NANCHONG", "南充校区"),
        ],
    },
    "成都理工大学": {
        "source_url": "https://zsdata.cdut.edu.cn/zsdata/lqxx/",
        "campuses": [
            ("CHENGDU", "成都校区"),
            ("YIBIN", "宜宾校区"),
        ],
    },
    "四川轻化工大学": {
        "source_url": "https://jxzy.suse.edu.cn/",
        "campuses": [
            ("HUIDONG", "汇东校区"),
            ("LIBAIHE", "李白河校区"),
            ("YIBIN", "宜宾校区"),
            ("HUANGLING", "黄岭校区"),
        ],
    },
    "西南科技大学": {
        "source_url": "https://www.swust.edu.cn/11127/list.htm",
        "campuses": [
            ("QINGYI", "青义校区"),
            ("XISHAN", "西山校区"),
        ],
    },
    "西华大学": {
        "source_url": "https://www.xhu.edu.cn/_t1159/24/list.htm",
        "campuses": [
            ("PIDU", "郫都校区"),
            ("YIBIN", "宜宾校区"),
            ("PENGZHOU", "彭州校区"),
            ("RENNAN", "人南校区"),
            ("ASSUMPTION", "易三仓（泰国）校区"),
        ],
    },
}

def sql_quote(value: str | None) -> str:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def build_records(source: Path) -> list[dict[str, object]]:
    df = pd.read_excel(source, header=None)
    start = df.index[df[0].astype(str).eq("四川省（141所）")][0]
    next_section = df.index[
        (df.index > start) & df[0].astype(str).str.contains("所）", regex=False)
    ][0]
    rows = df.iloc[start + 1 : next_section]
    records: list[dict[str, object]] = []
    for _, row in rows.iterrows():
        name = str(row[1]).strip()
        code = str(row[2]).strip()
        level = "undergraduate" if str(row[5]).strip() == "本科" else "college"
        ownership = "private" if "民办" in str(row[6]) else "public"
        city = str(row[4]).strip()
        authority = str(row[3]).strip()
        override = CAMPUS_OVERRIDES.get(name)
        if override:
            campuses = override["campuses"]
            verification_status = "official"
            source_url = override["source_url"]
        else:
            campuses = [("MAIN", name)]
            verification_status = "temporary"
            source_url = MOE_SOURCE_URL
        for index, (campus_code, campus_name) in enumerate(campuses):
            records.append(
                {
                    "school_code": code,
                    "university_name": name,
                    "province": "四川省",
                    "city": city,
                    "education_level": level,
                    "ownership": ownership,
                    "authority_name": authority,
                    "campus_code": campus_code,
                    "campus_name": campus_name,
                    "is_primary": index == 0,
                    "verification_status": verification_status,
                    "source_url": source_url,
                    "source_updated_on": (
                        "2025-06-20"
                        if verification_status == "temporary"
                        else "2026-11-19"
                    ),
                }
            )
    return records


def write_csv(records: list[dict[str, object]]) -> None:
    path = ROOT / "data" / "sichuan_universities_2025.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def write_prototype_data(records: list[dict[str, object]]) -> None:
    universities: dict[str, dict[str, object]] = {}
    for record in records:
        code = str(record["school_code"])
        university = universities.setdefault(
            code,
            {
                "schoolCode": code,
                "name": record["university_name"],
                "province": record["province"],
                "city": record["city"],
                "educationLevel": record["education_level"],
                "ownership": record["ownership"],
                "campuses": [],
            },
        )
        university["campuses"].append(
            {
                "code": record["campus_code"],
                "name": record["campus_name"],
                "isPrimary": record["is_primary"],
                "verificationStatus": record["verification_status"],
            }
        )
    path = ROOT / "docs" / "6.2-design" / "prototype" / "university-data.js"
    path.write_text(
        "window.QINGHE_UNIVERSITIES = "
        + json.dumps(list(universities.values()), ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )


def write_seed_sql(records: list[dict[str, object]]) -> None:
    lines = ["BEGIN;", ""]
    universities = {}
    for record in records:
        universities[str(record["school_code"])] = record
    for code, record in universities.items():
        lines.append(
            "INSERT INTO universities "
            "(code, name, province, city, education_level, ownership, "
            "authority_name, source_url, source_updated_on) VALUES ("
            f"{sql_quote(code)}, {sql_quote(record['university_name'])}, "
            f"{sql_quote(record['province'])}, {sql_quote(record['city'])}, "
            f"{sql_quote(record['education_level'])}, {sql_quote(record['ownership'])}, "
            f"{sql_quote(record['authority_name'])}, {sql_quote(record['source_url'])}, "
            f"{sql_quote(record['source_updated_on'])}"
            ") ON CONFLICT (code) DO UPDATE SET "
            "name = EXCLUDED.name, province = EXCLUDED.province, "
            "city = EXCLUDED.city, education_level = EXCLUDED.education_level, "
            "ownership = EXCLUDED.ownership, authority_name = EXCLUDED.authority_name, "
            "source_url = EXCLUDED.source_url, "
            "source_updated_on = EXCLUDED.source_updated_on;"
        )
    lines.append("")
    for record in records:
        lines.append(
            "INSERT INTO campuses "
            "(university_id, code, name, is_primary, verification_status, "
            "source_url, source_updated_on) "
            "SELECT id, "
            f"{sql_quote(record['campus_code'])}, {sql_quote(record['campus_name'])}, "
            f"{'true' if record['is_primary'] else 'false'}, "
            f"{sql_quote(record['verification_status'])}, "
            f"{sql_quote(record['source_url'])}, "
            f"{sql_quote(record['source_updated_on'])} "
            "FROM universities "
            f"WHERE code = {sql_quote(record['school_code'])} "
            "ON CONFLICT (university_id, code) DO UPDATE SET "
            "name = EXCLUDED.name, is_primary = EXCLUDED.is_primary, "
            "verification_status = EXCLUDED.verification_status, "
            "source_url = EXCLUDED.source_url, "
            "source_updated_on = EXCLUDED.source_updated_on;"
        )
    lines.extend(
        [
            "",
            "INSERT INTO item_categories (slug, name, display_order)",
            "VALUES",
            "    ('books', '书籍教材', 10),",
            "    ('stationery', '文具用品', 20),",
            "    ('digital', '数码产品', 30),",
            "    ('sports', '运动器材', 40),",
            "    ('daily', '生活用品', 50),",
            "    ('clothing', '衣物配饰', 60),",
            "    ('other', '其他物品', 99)",
            "ON CONFLICT (slug) DO UPDATE",
            "SET name = EXCLUDED.name, display_order = EXCLUDED.display_order, is_active = true;",
            "",
            "COMMIT;",
            "",
        ]
    )
    path = ROOT / "sql" / "seed.sql"
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    source = DEFAULT_SOURCE
    records = build_records(source)
    if len({record["school_code"] for record in records}) != 141:
        raise RuntimeError("Expected 141 Sichuan higher-education institutions")
    write_csv(records)
    write_prototype_data(records)
    write_seed_sql(records)
    print(f"universities=141 campuses={len(records)}")


if __name__ == "__main__":
    main()
