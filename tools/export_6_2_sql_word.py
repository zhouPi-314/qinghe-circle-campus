from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

from export_6_1_word import configure_document, set_run_font
from export_6_2_word import add_metadata_table


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "提交物" / "6.2" / "05-数据库建表脚本.docx"
TITLE = "青禾流转 6.2 数据库建表脚本"


def set_landscape(section) -> None:
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Inches(11)
    section.page_height = Inches(8.5)
    section.top_margin = Inches(0.45)
    section.bottom_margin = Inches(0.45)
    section.left_margin = Inches(0.60)
    section.right_margin = Inches(0.60)


def add_code_text(doc: Document, title: str, path: Path) -> None:
    doc.add_paragraph(title, style="Heading 1")
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 0.96
    p.paragraph_format.first_line_indent = Pt(0)
    lines = path.read_text(encoding="utf-8").splitlines()
    for line_idx, line in enumerate(lines):
        if line_idx:
            p.add_run().add_break()
        run = p.add_run(line)
        set_run_font(run, name="Consolas", size=7.2)


def add_summary(doc: Document, title: str, items: list[str]) -> None:
    doc.add_paragraph(title, style="Heading 1")
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.left_indent = Inches(0.28)
        p.paragraph_format.first_line_indent = Inches(-0.18)
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(item)
        set_run_font(run, name="宋体", size=10.2)


def main() -> None:
    doc = Document()
    configure_document(doc)
    doc.core_properties.title = TITLE
    doc.core_properties.subject = "课程提交物 6.2 概要设计"
    doc.core_properties.author = "Codex"

    title_p = doc.add_paragraph(TITLE, style="Title")
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle_p = doc.add_paragraph()
    subtitle_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle_p.paragraph_format.space_after = Pt(20)
    set_run_font(
        subtitle_p.add_run("课程提交物 6.2 概要设计"),
        name="微软雅黑",
        size=12,
        color="404040",
    )
    intro = doc.add_paragraph()
    intro.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    intro.paragraph_format.first_line_indent = Pt(0)
    intro.paragraph_format.space_after = Pt(12)
    set_run_font(
        intro.add_run(
            "本文档收录 PostgreSQL 18 的建表脚本和基础演示数据脚本。"
            "可执行源文件同时保存在开发仓库的 sql 目录。"
        ),
        name="宋体",
        size=10.5,
    )
    add_metadata_table(
        doc,
        ["项目", "内容"],
        [
            ["文档编号", "DES-SQL-001"],
            ["版本", "1.0"],
            ["日期", "2026-11-19"],
            ["状态", "已批准并冻结"],
            ["批准人", "用户"],
            ["批准日期", "2026-11-20"],
            ["AI 名称", "Codex"],
            ["数据库", "PostgreSQL 18"],
            ["脚本来源", "sql/schema.sql、sql/seed.sql"],
        ],
    )

    section = doc.add_section(WD_SECTION.NEW_PAGE)
    set_landscape(section)
    add_code_text(doc, "附录 A 数据库建表脚本", ROOT / "sql" / "schema.sql")

    add_summary(
        doc,
        "附录 B 基础演示数据说明",
        [
            "完整种子脚本保存在开发仓库 sql/seed.sql，高校源数据保存在 data/sichuan_universities_2025.csv。",
            "首批数据包含教育部 2025 年全国普通高等学校名单中的四川省普通高校 141 所。",
            "校区记录共 161 条；10 所多校区高校已按学校官网核验，其余暂以学校全称作为单校区名称并标记为 temporary。",
            "基础物品分类 7 个。",
            "公开版种子数据不预置管理员密码；首次部署使用 tools/create_platform_admin.py 交互创建管理员。",
            "公益管理员和校级管理员账号由平台管理员导入，不写入公开种子数据。",
        ],
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
