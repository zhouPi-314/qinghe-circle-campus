from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree


WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DRAWING = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
NS = {"w": WORD, "wp": DRAWING}


def findings_for(path: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    with zipfile.ZipFile(path) as package:
        document = ElementTree.fromstring(package.read("word/document.xml"))
        core = ElementTree.fromstring(package.read("docProps/core.xml"))

        title = core.findtext("{http://purl.org/dc/elements/1.1/}title")
        if not title or not title.strip():
            findings.append(
                {
                    "severity": "medium",
                    "kind": "missing_document_title",
                    "message": "Document title is empty.",
                }
            )

        for index, table in enumerate(document.findall(".//w:tbl", NS), start=1):
            first_row = table.find("w:tr", NS)
            header = first_row.find("w:trPr/w:tblHeader", NS) if first_row is not None else None
            if header is None:
                findings.append(
                    {
                        "severity": "medium",
                        "kind": "table_no_header_row",
                        "message": f"Table {index} first row is not marked as a header.",
                    }
                )

        for index, drawing in enumerate(document.findall(".//w:drawing", NS), start=1):
            properties = drawing.find(".//wp:docPr", NS)
            description = properties.get("descr", "").strip() if properties is not None else ""
            if not description:
                findings.append(
                    {
                        "severity": "high",
                        "kind": "image_missing_alt_text",
                        "message": f"Drawing {index} has no alternative text.",
                    }
                )

    return findings


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("usage: check_docx_structure.py <docx-directory> <output-json>")

    source = Path(sys.argv[1])
    output = Path(sys.argv[2])
    documents = []
    for path in sorted(source.glob("*.docx")):
        findings = findings_for(path)
        counts = {
            severity: sum(item["severity"] == severity for item in findings)
            for severity in ("high", "medium", "low")
        }
        documents.append(
            {
                "file": str(path),
                "counts": counts,
                "findings": findings,
            }
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"documents": documents}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
