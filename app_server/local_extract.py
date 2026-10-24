"""No-AI fallback reader for bills that already contain text (plain .txt or text PDFs).

Used when no model is configured (demo mode), or for .txt uploads. It only reads text that is
literally in the file and matches a bill line layout:

    DATE  CODE  DESCRIPTION  QTY  AMOUNT
    2026-09-14  99284  ER VISIT LEVEL 4  1  $2,950.00

Every line it finds is marked "please check", so the patient confirms it before anything is
compared. It never guesses: a row that doesn't match the layout is skipped, and a scanned image
or a compressed font PDF simply yields nothing (the patient then types the lines in).
Stdlib only. Nothing is logged or stored.
"""

from __future__ import annotations

import re
import zlib
from datetime import date

_STREAM = re.compile(rb"<<(.*?)>>\s*stream\r?\n(.*?)\r?\nendstream", re.S)
_TJ = re.compile(rb"\((?:\\.|[^\\)])*\)\s*Tj|\[(?:\((?:\\.|[^\\)])*\)|[^\]])*\]\s*TJ")
_STR = re.compile(rb"\(((?:\\.|[^\\)])*)\)")

_DATE = r"(?P<date>\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})"
_CODE = r"(?P<code>[A-Z]?\d{3,5}[A-Z]?|[A-Z]\d{4})"
_ROW = re.compile(
    rf"^\s*(?:{_DATE}\s+)?(?:{_CODE}\s+)?(?P<desc>\S.*?\S)\s+(?P<qty>\d+(?:\.\d+)?)\s+"
    r"\$?(?P<amt>-?[\d,]+\.\d{2})\s*$"
)
_SKIP = re.compile(r"^\s*(TOTAL|SUBTOTAL|BALANCE|AMOUNT DUE|PAYMENT|ADJUSTMENT)", re.I)


def _unescape(raw: bytes) -> str:
    out = bytearray()
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == 0x5C and i + 1 < len(raw):  # backslash
            n = raw[i + 1]
            if 0x30 <= n <= 0x37:  # octal \ddd
                j = i + 1
                while j < len(raw) and j < i + 4 and 0x30 <= raw[j] <= 0x37:
                    j += 1
                out.append(int(raw[i + 1:j], 8) & 0xFF)
                i = j
                continue
            out.append({ord("n"): 10, ord("r"): 13, ord("t"): 9}.get(n, n))
            i += 2
            continue
        out.append(c)
        i += 1
    return out.decode("latin-1")


def pdf_text_lines(data: bytes) -> list[str]:
    """Text lines drawn by Tj/TJ operators, in order. Empty if the PDF has no plain text."""
    lines: list[str] = []
    for head, body in _STREAM.findall(data):
        if b"/FlateDecode" in head:
            try:
                body = zlib.decompress(body)
            except zlib.error:
                continue
        elif b"/Filter" in head:
            continue  # other encodings: not plain text
        for op in _TJ.findall(body):
            text = "".join(_unescape(s) for s in _STR.findall(op))
            if text.strip():
                lines.append(text)
    return lines


def _iso(text: str | None) -> str | None:
    if not text:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})", text)
    if not m:
        return None
    mo, d, y = int(m[1]), int(m[2]), int(m[3])
    if y < 100:
        y += 2000
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def _system(code: str | None) -> str | None:
    if not code:
        return None
    if re.fullmatch(r"\d{5}", code):
        return "CPT"
    if re.fullmatch(r"[A-Z]\d{4}", code):
        return "HCPCS"
    return None


def parse_bill_text(lines: list[str]) -> dict:
    """Bill text lines -> {line_items, metadata, line_confidence}. Only matching rows count."""
    items: list[dict] = []
    meta: dict = {"hospital_name": None, "statement_date": None, "total": None}
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        if meta["hospital_name"] is None and not any(ch.isdigit() for ch in line) \
                and not line.strip().startswith(("*", "-")) and len(line.strip()) > 3:
            meta["hospital_name"] = line.strip()
            continue
        m = re.search(r"statement date:\s*(\S+)", line, re.I)
        if m:
            meta["statement_date"] = _iso(m[1])
            continue
        if _SKIP.match(line):
            t = re.search(r"\$?(-?[\d,]+\.\d{2})\s*$", line)
            if t and re.match(r"^\s*TOTAL", line, re.I):
                meta["total"] = float(t[1].replace(",", ""))
            continue
        m = _ROW.match(line)
        if not m or m["desc"].upper() == "DESCRIPTION":
            continue
        amount = float(m["amt"].replace(",", ""))
        if amount < 0:
            continue
        code = m["code"]
        items.append(
            {
                "id": str(len(items) + 1),
                "description": m["desc"].strip().title(),
                "raw_description": m["desc"].strip(),
                "code": code,
                "code_system": _system(code),
                "quantity": float(m["qty"]),
                "unit": "each",
                "date_of_service": _iso(m["date"]),
                "billed_amount": amount,
            }
        )
    return {
        "line_items": items,
        "metadata": meta,
        "line_confidence": [
            {"line_item_id": it["id"], "confidence": "low", "needs_confirmation": True} for it in items
        ],
    }


def extract_locally(data: bytes, content_type: str) -> dict:
    """Read a .txt or text-PDF bill without a model. Returns an ExtractionResult-shaped dict."""
    ct = content_type.split(";", 1)[0].strip().lower()
    if ct == "text/plain":
        lines = data.decode("utf-8", errors="replace").splitlines()
    elif ct == "application/pdf":
        lines = pdf_text_lines(data)
    else:
        lines = []
    result = parse_bill_text(lines)
    if result["line_items"]:
        result["warnings"] = [
            "Automatic AI reading is off, so we read the text directly from your file. "
            "Please check every line against your bill before continuing."
        ]
    else:
        result["warnings"] = [
            "We couldn't read lines from this file automatically. Please enter the bill lines by hand."
        ]
    return result
