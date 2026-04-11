from __future__ import annotations

from io import BytesIO
from typing import List

import fitz
import pdfplumber


def _group_words_by_lines(words: list[dict]) -> List[str]:
    rows: dict[tuple[int, int], list[str]] = {}
    for w in words:
        key = (int(w["top"] // 8), int(w["x0"] // 150))
        rows.setdefault(key, []).append(w["text"])
    ordered = []
    for key in sorted(rows.keys()):
        ordered.append(" ".join(rows[key]))
    return ordered


async def extract_pdf_text(content: bytes) -> str:
    text_parts: List[str] = []
    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            for page in pdf.pages:
                words = page.extract_words() or []
                if words:
                    text_parts.extend(_group_words_by_lines(words))
                else:
                    text_parts.append(page.extract_text() or "")
    except Exception:
        text_parts = []

    text = "\n".join(p for p in text_parts if p).strip()
    if text:
        return text

    with fitz.open(stream=content, filetype="pdf") as doc:
        return "\n".join(page.get_text("text") for page in doc)
