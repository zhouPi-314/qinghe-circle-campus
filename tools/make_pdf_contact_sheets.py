from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw


COLUMNS = 3
ROWS = 2
THUMB_WIDTH = 420
GAP = 24


def document_name(path: Path) -> str:
    return re.sub(r"-\d+$", "", path.stem)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: make_pdf_contact_sheets.py <page-png-directory> <output-directory>")

    source = Path(sys.argv[1])
    output = Path(sys.argv[2])
    output.mkdir(parents=True, exist_ok=True)

    groups: dict[str, list[Path]] = {}
    for path in sorted(source.glob("*.png")):
        groups.setdefault(document_name(path), []).append(path)

    for name, pages in groups.items():
        for start in range(0, len(pages), COLUMNS * ROWS):
            batch = pages[start : start + COLUMNS * ROWS]
            thumbnails = []
            for page in batch:
                with Image.open(page) as image:
                    height = round(image.height * THUMB_WIDTH / image.width)
                    thumbnails.append((page, image.resize((THUMB_WIDTH, height)).convert("RGB")))

            cell_height = max(image.height for _, image in thumbnails) + 34
            sheet = Image.new(
                "RGB",
                (
                    GAP + COLUMNS * (THUMB_WIDTH + GAP),
                    GAP + ROWS * (cell_height + GAP),
                ),
                "white",
            )
            draw = ImageDraw.Draw(sheet)
            for index, (page, image) in enumerate(thumbnails):
                row, column = divmod(index, COLUMNS)
                x = GAP + column * (THUMB_WIDTH + GAP)
                y = GAP + row * (cell_height + GAP)
                page_number = page.stem.rsplit("-", 1)[-1]
                draw.text((x, y), f"Page {page_number}", fill="black")
                sheet.paste(image, (x, y + 24))

            suffix = f"-{start // (COLUMNS * ROWS) + 1:02d}"
            sheet.save(output / f"{name}-contact{suffix}.png")


if __name__ == "__main__":
    main()
