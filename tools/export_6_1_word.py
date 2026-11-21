from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "docs" / "6.1-requirements"
OUTPUT_DIR = ROOT / "提交物" / "6.1"

DOCUMENTS = [
    {
        "source": "AI原始需求文档.md",
        "output": "01-AI生成的原始需求文档.docx",
        "subtitle": "课程提交物 6.1 需求分析",
        "intro": (
            "本文档记录 Codex 在需求发散阶段提出的完整功能设想，作为后续人工删减的输入。"
            "文中功能不代表最终开发范围，不能直接作为编码基线。"
        ),
    },
    {
        "source": "删减决策表.md",
        "output": "02-删减决策表.docx",
        "subtitle": "课程提交物 6.1 需求分析",
        "intro": (
            "本文档逐项记录原始需求的保留、简化、延后或删除决定，并说明首版范围和判断依据。"
            "最终开发以通过审核的删减结果和正式需求规格为准。"
        ),
    },
]

BODY_FONT = "宋体"
HEADING_FONT = "微软雅黑"
CODE_FONT = "Consolas"
BLACK = "000000"
WHITE = "FFFFFF"
HEADER_BLUE = "1F4E78"
ROW_BLUE = "EAF2F8"
LABEL_BLUE = "D9EAF7"
BORDER_GRAY = "D9D9D9"

COLUMN_WIDTHS = {
    ("项目", "内容"): (1.25, 5.65),
    ("ID", "功能", "优先级", "为什么需要"): (0.85, 2.65, 0.65, 2.75),
    ("原始需求", "决策", "最终范围", "理由"): (1.35, 0.80, 2.55, 2.20),
    ("模块", "主要需求"): (1.35, 5.55),
}

CENTER_HEADERS = {"ID", "优先级", "决策"}


def set_run_font(
    run,
    *,
    name: str,
    size: float,
    bold: bool = False,
    color: str = BLACK,
) -> None:
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), name)


def remove_paragraph_borders(style) -> None:
    ppr = style.element.get_or_add_pPr()
    for border in ppr.findall(qn("w:pBdr")):
        ppr.remove(border)


def add_inline_runs(
    paragraph,
    text: str,
    *,
    font_name: str,
    size: float,
    color: str = BLACK,
) -> None:
    pattern = re.compile(r"(\*\*.+?\*\*|`[^`]+`)")
    cursor = 0
    for match in pattern.finditer(text):
        if match.start() > cursor:
            run = paragraph.add_run(text[cursor : match.start()])
            set_run_font(run, name=font_name, size=size, color=color)
        token = match.group(0)
        if token.startswith("**"):
            run = paragraph.add_run(token[2:-2])
            set_run_font(run, name=font_name, size=size, bold=True, color=color)
        else:
            run = paragraph.add_run(token[1:-1])
            set_run_font(run, name=CODE_FONT, size=max(size - 0.5, 8.0), color=color)
        cursor = match.end()
    if cursor < len(text):
        run = paragraph.add_run(text[cursor:])
        set_run_font(run, name=font_name, size=size, color=color)


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    for old in tc_pr.findall(qn("w:shd")):
        tc_pr.remove(old)
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    tc_pr.append(shading)


def set_cell_margins(cell, top: int = 40, start: int = 90, bottom: int = 40, end: int = 90) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    old = tc_pr.find(qn("w:tcMar"))
    if old is not None:
        tc_pr.remove(old)
    margins = OxmlElement("w:tcMar")
    for name, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = OxmlElement(f"w:{name}")
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")
        margins.append(node)
    tc_pr.append(margins)


def set_table_borders(table) -> None:
    tbl_pr = table._tbl.tblPr
    old = tbl_pr.find(qn("w:tblBorders"))
    if old is not None:
        tbl_pr.remove(old)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        node = OxmlElement(f"w:{edge}")
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), "4")
        node.set(qn("w:space"), "0")
        node.set(qn("w:color"), BORDER_GRAY)
        borders.append(node)
    tbl_pr.append(borders)


def set_fixed_layout(table) -> None:
    tbl_pr = table._tbl.tblPr
    old = tbl_pr.find(qn("w:tblLayout"))
    if old is not None:
        tbl_pr.remove(old)
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl_pr.append(layout)


def set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    tr_pr.append(header)


def prevent_row_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    no_split = OxmlElement("w:cantSplit")
    tr_pr.append(no_split)


def add_page_field(paragraph) -> None:
    run = paragraph.add_run()
    set_run_font(run, name=BODY_FONT, size=9)
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend((begin, instr, separate, text, end))


def configure_document(doc: Document) -> None:
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(0.72)
    section.bottom_margin = Inches(0.72)
    section.left_margin = Inches(0.80)
    section.right_margin = Inches(0.80)
    section.header_distance = Inches(0.35)
    section.footer_distance = Inches(0.35)
    section.different_first_page_header_footer = True

    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor.from_string(BLACK)
    normal._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), BODY_FONT)
    normal.paragraph_format.line_spacing = 1.15
    normal.paragraph_format.space_after = Pt(6)

    title = doc.styles["Title"]
    title.font.name = HEADING_FONT
    title.font.size = Pt(24)
    title.font.bold = True
    title.font.color.rgb = RGBColor.from_string(BLACK)
    title._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), HEADING_FONT)
    title.paragraph_format.space_before = Pt(60)
    title.paragraph_format.space_after = Pt(14)
    remove_paragraph_borders(title)

    h1 = doc.styles["Heading 1"]
    h1.font.name = HEADING_FONT
    h1.font.size = Pt(15)
    h1.font.bold = True
    h1.font.color.rgb = RGBColor.from_string(BLACK)
    h1._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), HEADING_FONT)
    h1.paragraph_format.space_before = Pt(14)
    h1.paragraph_format.space_after = Pt(6)
    h1.paragraph_format.keep_with_next = True
    remove_paragraph_borders(h1)

    h2 = doc.styles["Heading 2"]
    h2.font.name = HEADING_FONT
    h2.font.size = Pt(12)
    h2.font.bold = True
    h2.font.color.rgb = RGBColor.from_string(BLACK)
    h2._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), HEADING_FONT)
    h2.paragraph_format.space_before = Pt(10)
    h2.paragraph_format.space_after = Pt(4)
    h2.paragraph_format.keep_with_next = True
    remove_paragraph_borders(h2)

    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    prefix = p.add_run("第 ")
    set_run_font(prefix, name=BODY_FONT, size=9)
    add_page_field(p)
    suffix = p.add_run(" 页")
    set_run_font(suffix, name=BODY_FONT, size=9)


def split_table_row(line: str) -> list[str]:
    return [part.strip() for part in line.strip().strip("|").split("|")]


def is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def parse_markdown(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    first_heading = next(i for i, line in enumerate(lines) if line.startswith("# "))
    title = lines[first_heading][2:].strip()
    first_section = next(i for i, line in enumerate(lines) if line.startswith("## "))
    front = lines[first_heading + 1 : first_section]
    metadata_headers = []
    metadata_rows = []
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
    if not rows:
        return
    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_ALIGN_PARAGRAPH.CENTER
    table.autofit = False
    set_fixed_layout(table)
    set_table_borders(table)
    widths = COLUMN_WIDTHS[("项目", "内容")]
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
        add_inline_runs(p, header, font_name=HEADING_FONT, size=9.5, color=WHITE)
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
                size=9.5,
                color=BLACK,
            )
            if col == 0:
                for run in p.runs:
                    run.font.bold = True
        prevent_row_split(row)


def add_markdown_table(doc: Document, table_lines: list[str]) -> None:
    rows = [split_table_row(line) for line in table_lines]
    if len(rows) < 2:
        return
    headers = rows[0]
    data = [row for row in rows[1:] if not is_separator_row(row)]
    widths = COLUMN_WIDTHS.get(tuple(headers))
    if widths is None or len(widths) != len(headers):
        widths = tuple(6.9 / len(headers) for _ in headers)

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
        p.paragraph_format.line_spacing = 1.05
        p.paragraph_format.first_line_indent = Pt(0)
        add_inline_runs(p, header, font_name=HEADING_FONT, size=9, color=WHITE)
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
            set_cell_margins(cell)
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
            add_inline_runs(p, value, font_name=BODY_FONT, size=9, color=BLACK)
        prevent_row_split(row)

    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def add_body(doc: Document, lines: list[str]) -> None:
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line:
            i += 1
            continue
        if line.startswith("### "):
            p = doc.add_paragraph(style="Heading 2")
            add_inline_runs(p, line[4:].strip(), font_name=HEADING_FONT, size=12)
            i += 1
            continue
        if line.startswith("## "):
            p = doc.add_paragraph(style="Heading 1")
            heading_text = line[3:].strip()
            add_inline_runs(p, heading_text, font_name=HEADING_FONT, size=15)
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
                add_inline_runs(p, bullet, font_name=BODY_FONT, size=10.5)
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
            add_inline_runs(
                p,
                "".join(quote_lines),
                font_name=BODY_FONT,
                size=10,
                color="3F3F3F",
            )
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
            ):
                break
            paragraph_lines.append(candidate.strip())
            i += 1
        p = doc.add_paragraph()
        p.paragraph_format.first_line_indent = Pt(21)
        p.paragraph_format.space_after = Pt(6)
        add_inline_runs(
            p,
            "".join(paragraph_lines),
            font_name=BODY_FONT,
            size=10.5,
        )


def build_document(spec: dict[str, str]) -> Path:
    source = SOURCE_DIR / spec["source"]
    output = OUTPUT_DIR / spec["output"]
    title, metadata_headers, metadata_rows, body_lines = parse_markdown(source)

    doc = Document()
    configure_document(doc)
    doc.core_properties.title = title
    doc.core_properties.subject = spec["subtitle"]
    doc.core_properties.author = "Codex"
    doc.core_properties.comments = "青禾流转课程项目 6.1 需求分析提交物"

    title_p = doc.add_paragraph(title, style="Title")
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    subtitle_p = doc.add_paragraph()
    subtitle_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle_p.paragraph_format.space_after = Pt(20)
    subtitle_run = subtitle_p.add_run(spec["subtitle"])
    set_run_font(
        subtitle_run,
        name=HEADING_FONT,
        size=12,
        color="404040",
    )

    intro_p = doc.add_paragraph()
    intro_p.paragraph_format.first_line_indent = Pt(0)
    intro_p.paragraph_format.left_indent = Inches(0.2)
    intro_p.paragraph_format.right_indent = Inches(0.2)
    intro_p.paragraph_format.space_after = Pt(12)
    intro_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    add_inline_runs(
        intro_p,
        spec["intro"],
        font_name=BODY_FONT,
        size=10.5,
    )

    add_metadata_table(doc, metadata_headers, metadata_rows)
    doc.add_page_break()
    add_body(doc, body_lines)

    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output)
    return output


def main() -> None:
    for spec in DOCUMENTS:
        output = build_document(spec)
        print(output)


if __name__ == "__main__":
    main()
