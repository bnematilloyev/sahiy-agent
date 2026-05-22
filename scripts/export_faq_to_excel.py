#!/usr/bin/env python3
"""Export FAQ seed data (faq_100 + quick_replies) to Excel."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.data.faq_100 import FAQ_ENTRIES
from scripts.data.faq_quick_replies import QUICK_REPLY_FAQ_ENTRIES

OUTPUT = Path(__file__).resolve().parent / "data" / "faq_seed.xlsx"

COLUMNS = ("id", "manba", "category", "question", "answer", "source_type", "source_id")


def _rows():
    for item in FAQ_ENTRIES:
        yield {
            "id": item["id"],
            "manba": "faq_100",
            "category": item.get("category", ""),
            "question": item.get("question", ""),
            "answer": item.get("answer", ""),
            "source_type": "",
            "source_id": "",
        }
    for item in QUICK_REPLY_FAQ_ENTRIES:
        yield {
            "id": item["id"],
            "manba": "quick_replies",
            "category": item.get("category", ""),
            "question": item.get("question", ""),
            "answer": item.get("answer", ""),
            "source_type": item.get("source_type", ""),
            "source_id": item.get("source_id", ""),
        }


def main() -> None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font
    except ImportError:
        print("openpyxl kerak: pip install openpyxl")
        sys.exit(1)

    wb = Workbook()
    ws = wb.active
    ws.title = "FAQ seed"

    header_font = Font(bold=True)
    for col, name in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=col, value=name)
        cell.font = header_font

    for row_idx, row in enumerate(_rows(), start=2):
        for col_idx, key in enumerate(COLUMNS, start=1):
            value = row[key]
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if key in ("question", "answer"):
                cell.alignment = Alignment(wrap_text=True, vertical="top")

    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 50
    ws.column_dimensions["E"].width = 70
    ws.column_dimensions["F"].width = 12
    ws.column_dimensions["G"].width = 12
    ws.freeze_panes = "A2"

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUTPUT)
    total = len(FAQ_ENTRIES) + len(QUICK_REPLY_FAQ_ENTRIES)
    print(f"Yozildi: {OUTPUT} ({total} qator)")


if __name__ == "__main__":
    main()
