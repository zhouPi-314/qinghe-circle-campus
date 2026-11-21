from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from PIL import Image

from export_6_1_word import (
    BLACK,
    BORDER_GRAY,
    HEADER_BLUE,
    HEADING_FONT,
    LABEL_BLUE,
    ROW_BLUE,
    WHITE,
    add_inline_runs,
    add_page_field,
    configure_document,
    prevent_row_split,
    set_cell_margins,
    set_cell_shading,
    set_fixed_layout,
    set_repeat_table_header,
    set_run_font,
    set_table_borders,
    split_table_row,
    is_separator_row,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "docs" / "6.2-design"
OUTPUT_DIR = ROOT / "提交物" / "6.2"

DOCUMENTS = [
    {
        "sources": ["01-data-model-and-er.md", "02-database-design.md"],
        "output": "01-数据库设计与ER表核对.docx",
        "title": "青禾流转 6.2 数据库设计与 ER 表核对",
        "subtitle": "课程提交物 6.2 概要设计",
        "intro": (
            "本文档将已冻结的需求转换为实体、关系、数据表和数据库约束，"
            "用于核对每项业务是否拥有明确、可持久化的数据职责。"
        ),
    },
    {
        "sources": ["03-architecture-design.md"],
        "output": "02-系统架构与模块设计.docx",
        "title": "青禾流转 6.2 系统架构与模块设计",
        "subtitle": "课程提交物 6.2 概要设计",
        "intro": (
            "本文档说明系统分层、业务模块、模块穿线卡、service 接口和关键数据流，"
            "作为 6.3 实现和验收的统一架构依据。"
        ),
    },
    {
        "sources": ["04-global-conventions.md"],
        "output": "03-全局约定与权限矩阵.docx",
        "title": "青禾流转 6.2 全局约定与权限矩阵",
        "subtitle": "课程提交物 6.2 概要设计",
        "intro": (
            "本文档统一角色权限、物品和流转状态、中文状态名称、路由和错误行为，"
            "避免页面、业务服务和数据库各自形成不同标准。"
        ),
    },
    {
        "sources": ["05-ui-design-and-prototypes.md"],
        "output": "04-UI规范与页面原型.docx",
        "title": "青禾流转 6.2 UI 规范与页面原型",
        "subtitle": "课程提交物 6.2 概要设计",
        "intro": (
            "本文档固定品牌文案、视觉令牌、页面骨架、响应式规则和关键原型，"
            "用于在编码前核对界面风格、信息层级和状态反馈。"
        ),
    },
]

BODY_FONT = "宋体"
CODE_FONT = "Consolas"

COLUMN_WIDTHS = {
    ("项目", "内容"): (1.30, 5.60),
    ("分组", "表"): (1.45, 5.45),
    ("分组", "表数", "表"): (1.05, 0.55, 5.30),
    ("编号", "表", "职责", "核心字段", "关系与约束"): (
        0.38,
        1.58,
        1.55,
        2.10,
        1.29,
    ),
    ("关系", "基数", "说明"): (1.85, 0.75, 4.30),
    ("对象", "处理方式", "理由"): (1.55, 2.25, 3.10),
    ("字段", "规则"): (1.25, 5.65),
    ("索引", "目的"): (2.25, 4.65),
    ("数据", "存储方式", "使用方式"): (1.25, 2.75, 2.90),
    ("SRS 范围", "对应表"): (2.15, 4.75),
    ("模块", "主要使用角色", "主要业务", "维护表"): (1.35, 1.45, 2.10, 2.00),
    ("检查项", "验收标准"): (1.90, 5.00),
    ("模块", "接口"): (1.70, 5.20),
    ("层", "课程本地", "公网演示"): (1.05, 2.75, 3.10),
    ("中文", "数据库值", "可见标签", "标签色"): (1.20, 1.45, 2.15, 2.10),
    ("能力", "游客", "在校学生", "公益管理员", "平台管理员", "校级管理员"): (
        2.20,
        0.55,
        0.90,
        1.05,
        1.05,
        1.15,
    ),
    ("代码", "中文", "含义"): (1.35, 1.45, 4.10),
    ("起点", "事件", "终点", "责任角色"): (1.45, 2.30, 1.55, 1.60),
    ("当前状态", "操作", "下一状态", "操作者"): (1.65, 1.65, 1.65, 1.95),
    ("模式", "正常主链", "专属异常"): (0.85, 3.45, 2.60),
    ("代码", "中文", "允许操作"): (1.10, 1.40, 4.40),
    ("代码", "中文", "计数规则"): (1.10, 1.45, 4.35),
    ("代码", "中文", "可见性"): (1.10, 1.35, 4.45),
    ("代码", "中文", "责任角色"): (1.10, 1.45, 4.35),
    ("路径", "页面", "权限"): (2.15, 2.55, 2.20),
    ("类型", "页面行为", "示例"): (1.25, 2.50, 3.15),
    ("页面", "路径", "核心内容", "空态", "错误态"): (
        1.25,
        1.10,
        2.25,
        1.15,
        1.15,
    ),
    ("维度", "本设计的选择", "代价与控制"): (1.25, 2.80, 2.85),
    ("项目", "规范"): (1.30, 5.60),
}

CENTER_HEADERS = {
    "编号",
    "表数",
    "基数",
    "游客",
    "在校学生",
    "公益管理员",
    "平台管理员",
    "校级管理员",
    "代码",
}


def set_paragraph_shading(paragraph, fill: str) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    old = ppr.find(qn("w:shd"))
    if old is not None:
        ppr.remove(old)
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    ppr.append(shading)


def add_code_block(doc: Document, code: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.0
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.left_indent = Inches(0.16)
    p.paragraph_format.right_indent = Inches(0.16)
    set_paragraph_shading(p, "F4F1E8")
    for line_idx, line in enumerate(code.splitlines() or [""]):
        if line_idx:
            p.add_run().add_break()
        run = p.add_run(line)
        set_run_font(run, name=CODE_FONT, size=8.2)


def add_picture(doc: Document, image_path: Path, caption: str) -> None:
    if not image_path.is_file():
        raise FileNotFoundError(image_path)
    with Image.open(image_path) as image:
        px_w, px_h = image.size
    max_width = 6.75
    max_height = 7.10
    width = max_width
    height = width * px_h / px_w
    if height > max_height:
        height = max_height
        width = height * px_w / px_h
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    shape = p.add_run().add_picture(
        str(image_path),
        width=Inches(width),
        height=Inches(height),
    )
    shape._inline.docPr.set("descr", caption)
    shape._inline.docPr.set("title", caption)
    caption_p = doc.add_paragraph()
    caption_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption_p.paragraph_format.first_line_indent = Pt(0)
    caption_p.paragraph_format.space_after = Pt(8)
    run = caption_p.add_run(caption)
    set_run_font(run, name=BODY_FONT, size=9, color="555555")


def parse_source(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    first_heading = next(i for i, line in enumerate(lines) if line.startswith("# "))
    title = lines[first_heading][2:].strip()
    first_section = next(i for i, line in enumerate(lines) if line.startswith("## "))
    front = lines[first_heading + 1 : first_section]
    metadata_headers: list[str] = []
    metadata_rows: list[list[str]] = []
    i = 0
    while i < len(front):
        if front[i].startswith("|"):
            table_lines = []
            while i < len(front) and front[i].startswith("|"):
                table_lines.append(front[i])
                i += 1
            rows = [split_table_row(line) for line in table_lines]
            metadata_headers = rows[0]
            metadata_rows = [row for row in rows[1:] if not is_separator_row(row)]
        else:
            i += 1
    return title, metadata_headers, metadata_rows, lines[first_section:]


def add_metadata_table(doc: Document, headers: list[str], rows: list[list[str]]) -> None:
    if not headers or not rows:
        return
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_ALIGN_PARAGRAPH.CENTER
    table.autofit = False
    set_fixed_layout(table)
    set_table_borders(table)
    widths = COLUMN_WIDTHS.get(tuple(headers), tuple(6.9 / len(headers) for _ in headers))
    for col, header in enumerate(headers):
        cell = table.rows[0].cells[col]
        cell.width = Inches(widths[col])
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        set_cell_margins(cell)
        set_cell_shading(cell, HEADER_BLUE)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.first_line_indent = Pt(0)
        add_inline_runs(p, header, font_name=HEADING_FONT, size=9.2, color=WHITE)
        for run in p.runs:
            run.font.bold = True
    set_repeat_table_header(table.rows[0])
    prevent_row_split(table.rows[0])
    for idx, values in enumerate(rows):
        row = table.add_row()
        for col, value in enumerate(values):
            cell = row.cells[col]
            cell.width = Inches(widths[col])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_margins(cell)
            set_cell_shading(cell, LABEL_BLUE if col == 0 else WHITE)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.0
            p.paragraph_format.first_line_indent = Pt(0)
            add_inline_runs(
                p,
                value,
                font_name=HEADING_FONT if col == 0 else BODY_FONT,
                size=9.2,
            )
            if col == 0:
                for run in p.runs:
                    run.font.bold = True
        prevent_row_split(row)


def add_markdown_table(doc: Document, table_lines: list[str]) -> None:
    rows = [split_table_row(line) for line in table_lines]
    headers = rows[0]
    data = [row for row in rows[1:] if not is_separator_row(row)]
    widths = COLUMN_WIDTHS.get(tuple(headers), tuple(6.9 / len(headers) for _ in headers))
    font_size = 8.5 if len(headers) >= 5 else 8.9

    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_ALIGN_PARAGRAPH.CENTER
    table.autofit = False
    set_fixed_layout(table)
    set_table_borders(table)

    for col, header in enumerate(headers):
        cell = table.rows[0].cells[col]
        cell.width = Inches(widths[col])
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        set_cell_margins(cell)
        set_cell_shading(cell, HEADER_BLUE)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.first_line_indent = Pt(0)
        add_inline_runs(p, header, font_name=HEADING_FONT, size=font_size, color=WHITE)
        for run in p.runs:
            run.font.bold = True
    set_repeat_table_header(table.rows[0])
    prevent_row_split(table.rows[0])

    for row_idx, values in enumerate(data):
        row = table.add_row()
        fill = ROW_BLUE if row_idx % 2 else WHITE
        for col, value in enumerate(values):
            cell = row.cells[col]
            cell.width = Inches(widths[col])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_margins(cell, top=35, start=75, bottom=35, end=75)
            set_cell_shading(cell, fill)
            p = cell.paragraphs[0]
            p.alignment = (
                WD_ALIGN_PARAGRAPH.CENTER
                if headers[col] in CENTER_HEADERS
                else WD_ALIGN_PARAGRAPH.LEFT
            )
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.0
            p.paragraph_format.first_line_indent = Pt(0)
            add_inline_runs(p, value, font_name=BODY_FONT, size=font_size)
        prevent_row_split(row)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def add_body(doc: Document, lines: list[str], base_dir: Path) -> None:
    i = 0
    pending_image: Path | None = None
    while i < len(lines):
        line = lines[i].rstrip()
        if not line:
            i += 1
            continue
        if line.strip() == "<!-- docx-page-break -->":
            doc.add_page_break()
            i += 1
            continue
        comment_match = re.fullmatch(r"<!--\s*docx-image:\s*(.+?)\s*-->", line)
        if comment_match:
            pending_image = (base_dir / comment_match.group(1)).resolve()
            i += 1
            continue
        if line.startswith("```"):
            language = line[3:].strip().lower()
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1
            if language == "mermaid" and pending_image is not None:
                add_picture(doc, pending_image, "设计图")
                pending_image = None
            else:
                add_code_block(doc, "\n".join(code_lines))
            continue
        image_match = re.fullmatch(r"!\[(.*?)\]\((.+?)\)", line)
        if image_match:
            caption, relative_path = image_match.groups()
            add_picture(doc, (base_dir / relative_path).resolve(), caption)
            i += 1
            continue
        if line.startswith("### "):
            p = doc.add_paragraph(style="Heading 2")
            add_inline_runs(p, line[4:].strip(), font_name=HEADING_FONT, size=12)
            i += 1
            continue
        if line.startswith("## "):
            p = doc.add_paragraph(style="Heading 1")
            add_inline_runs(p, line[3:].strip(), font_name=HEADING_FONT, size=15)
            i += 1
            continue
        if line.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].startswith("|"):
                table_lines.append(lines[i])
                i += 1
            add_markdown_table(doc, table_lines)
            continue
        if line.startswith("- "):
            bullets = []
            while i < len(lines) and lines[i].startswith("- "):
                bullets.append(lines[i][2:].strip())
                i += 1
            for bullet in bullets:
                p = doc.add_paragraph(style="List Bullet")
                p.paragraph_format.left_indent = Inches(0.28)
                p.paragraph_format.first_line_indent = Inches(-0.18)
                p.paragraph_format.space_after = Pt(3)
                add_inline_runs(p, bullet, font_name=BODY_FONT, size=10.2)
            continue
        ordered_match = re.match(r"^(\d+)\.\s+(.*)$", line)
        if ordered_match:
            while i < len(lines):
                current = re.match(r"^(\d+)\.\s+(.*)$", lines[i].rstrip())
                if not current:
                    break
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Inches(0.28)
                p.paragraph_format.first_line_indent = Inches(-0.18)
                p.paragraph_format.space_after = Pt(3)
                add_inline_runs(
                    p,
                    f"{current.group(1)}. {current.group(2)}",
                    font_name=BODY_FONT,
                    size=10.2,
                )
                i += 1
            continue
        if line.startswith("> "):
            quote_lines = []
            while i < len(lines) and lines[i].startswith("> "):
                quote_lines.append(lines[i][2:].strip())
                i += 1
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.24)
            p.paragraph_format.first_line_indent = Pt(0)
            p.paragraph_format.space_before = Pt(3)
            p.paragraph_format.space_after = Pt(8)
            set_paragraph_shading(p, "F3F0E7")
            add_inline_runs(p, "".join(quote_lines), font_name=BODY_FONT, size=10, color="404040")
            continue

        paragraph_lines = []
        while i < len(lines):
            candidate = lines[i].rstrip()
            if (
                not candidate
                or candidate.startswith("#")
                or candidate.startswith("|")
                or candidate.startswith("- ")
                or candidate.startswith("> ")
                or candidate.startswith("```")
                or re.fullmatch(r"!\[(.*?)\]\((.+?)\)", candidate)
                or re.fullmatch(r"<!--\s*docx-image:\s*(.+?)\s*-->", candidate)
            ):
                break
            paragraph_lines.append(candidate.strip())
            i += 1
        p = doc.add_paragraph()
        p.paragraph_format.first_line_indent = Pt(21)
        p.paragraph_format.space_after = Pt(6)
        add_inline_runs(p, "".join(paragraph_lines), font_name=BODY_FONT, size=10.2)


def build_document(spec: dict) -> Path:
    parsed = [parse_source(SOURCE_DIR / source) for source in spec["sources"]]
    _, metadata_headers, metadata_rows, _ = parsed[0]
    doc = Document()
    configure_document(doc)
    doc.core_properties.title = spec["title"]
    doc.core_properties.subject = spec["subtitle"]
    doc.core_properties.author = "Codex"

    title_p = doc.add_paragraph(spec["title"], style="Title")
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle_p = doc.add_paragraph()
    subtitle_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle_p.paragraph_format.space_after = Pt(20)
    set_run_font(
        subtitle_p.add_run(spec["subtitle"]),
        name=HEADING_FONT,
        size=12,
        color="404040",
    )
    intro_p = doc.add_paragraph()
    intro_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    intro_p.paragraph_format.left_indent = Inches(0.2)
    intro_p.paragraph_format.right_indent = Inches(0.2)
    intro_p.paragraph_format.first_line_indent = Pt(0)
    intro_p.paragraph_format.space_after = Pt(12)
    add_inline_runs(intro_p, spec["intro"], font_name=BODY_FONT, size=10.2)
    add_metadata_table(doc, metadata_headers, metadata_rows)

    for index, (source_title, _, _, body_lines) in enumerate(parsed):
        doc.add_page_break()
        p = doc.add_paragraph(style="Heading 1")
        add_inline_runs(p, source_title, font_name=HEADING_FONT, size=16)
        add_body(doc, body_lines, SOURCE_DIR)

    while doc.paragraphs and not doc.paragraphs[-1].text.strip():
        last = doc.paragraphs[-1]
        parent = last._element.getparent()
        parent.remove(last._element)

    output = OUTPUT_DIR / spec["output"]
    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output)
    return output


def main() -> None:
    for spec in DOCUMENTS:
        print(build_document(spec))


if __name__ == "__main__":
    main()
