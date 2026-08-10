#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES_DIR = ROOT / "categories"
MAX_DESCRIPTION = 120


def shorten(text: str, limit: int = MAX_DESCRIPTION) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def compact_table(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        if not line.startswith("|") or "---" in line:
            out.append(line)
            continue
        cells = line.split("|")
        # Generated category tables use:
        # Repository | 中文描述 | Original description | Lang | Stars | Classifier | Status | Last push
        if len(cells) >= 10 and cells[1].strip() != "Repository":
            cells[3] = " " + shorten(cells[3].strip()) + " "
            line = "|".join(cells)
        out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> None:
    if not CATEGORIES_DIR.exists():
        return
    for path in CATEGORIES_DIR.glob("*.md"):
        compact_table(path)


if __name__ == "__main__":
    main()
