"""Print a SyntheticBill as plain text (and, in a later task, PDF).

Two styles change only how the bill LOOKS. Ground truth is never affected:
  plain  ISO dates, $ amounts, no extra header or footer
  messy  MM/DD/YY dates, amounts without $, extra header and footer lines
"""

from __future__ import annotations

import textwrap
from datetime import date
from decimal import Decimal
from typing import Final

from contracts.types import LineItem, SyntheticBill

STYLES: Final[tuple[str, ...]] = ("plain", "messy")

_W_DATE, _W_CODE, _W_DESC, _W_QTY, _W_AMT = 10, 8, 34, 4, 12
_GAP = "  "
_WIDTH = _W_DATE + _W_CODE + _W_DESC + _W_QTY + _W_AMT + 4 * len(_GAP)


def _check_style(style: str) -> None:
    if style not in STYLES:
        raise ValueError(f"Unknown style {style!r}. Valid styles: {', '.join(STYLES)}")


def _date_text(value: str | None, style: str) -> str:
    if not value:
        return ""
    if style == "messy":
        try:
            return date.fromisoformat(value).strftime("%m/%d/%y")
        except ValueError:
            return value
    return value


def _money(amount: float, style: str) -> str:
    text = f"{Decimal(str(amount)):,.2f}"
    return text if style == "messy" else f"${text}"


def _qty_text(quantity: float | None) -> str:
    if quantity is None:
        return ""
    return str(int(quantity)) if float(quantity).is_integer() else str(quantity)


def _row(item: LineItem, style: str) -> list[str]:
    """One printed row, plus continuation rows when the description wraps."""
    description = item.raw_description or item.description
    parts = textwrap.wrap(description, width=_W_DESC, break_long_words=True) or [""]
    first = _GAP.join(
        [
            _date_text(item.date_of_service, style).ljust(_W_DATE),
            (item.code or "").ljust(_W_CODE),
            parts[0].ljust(_W_DESC),
            _qty_text(item.quantity).rjust(_W_QTY),
            _money(item.billed_amount, style).rjust(_W_AMT),
        ]
    )
    indent = " " * (_W_DATE + _W_CODE + 2 * len(_GAP))
    return [first.rstrip()] + [(indent + part).rstrip() for part in parts[1:]]


def layout(bill: SyntheticBill, style: str = "plain") -> list[str]:
    """The printed bill as lines of text. Shared by the text and PDF renderers."""
    _check_style(style)
    meta = bill.bill_metadata
    lines: list[str] = []
    if style == "messy":
        lines += ["*** ACCT STMT - DUPLICATE COPY ***", "-" * _WIDTH]
    lines += [
        meta.hospital_name,
        "PATIENT STATEMENT",
        f"Statement date: {_date_text(meta.statement_date, style)}",
        f"Account: SYN-{bill.bill_id}    Patient: SAMPLE PATIENT (FICTIONAL)",
        "",
        _GAP.join(
            [
                "DATE".ljust(_W_DATE),
                "CODE".ljust(_W_CODE),
                "DESCRIPTION".ljust(_W_DESC),
                "QTY".rjust(_W_QTY),
                "AMOUNT".rjust(_W_AMT),
            ]
        ),
        "-" * _WIDTH,
    ]
    for item in bill.line_items:
        lines += _row(item, style)
    lines += [
        "-" * _WIDTH,
        ("TOTAL CHARGES".ljust(_WIDTH - _W_AMT - len(_GAP)) + _GAP + _money(meta.total_billed, style).rjust(_W_AMT)),
    ]
    if style == "messy":
        lines += [
            "",
            "PLEASE REMIT PAYMENT WITHIN 30 DAYS",
            "QUESTIONS? CALL 555-0100 (FICTIONAL NUMBER)",
        ]
    return lines


def render_text(bill: SyntheticBill, style: str = "plain") -> str:
    """The bill as plain text. Same input, same output."""
    return "\n".join(layout(bill, style)) + "\n"


# --- PDF ---------------------------------------------------------------------
# A minimal, dependency-free PDF writer: one built-in Courier font, fixed-size pages, no
# compression, and no dates or ids, so equal input gives byte-identical output.

LINES_PER_PAGE: Final = 55
_PAGE_W, _PAGE_H = 612, 792  # US Letter, points
_MARGIN_X, _TOP_Y = 40, 750
_FONT_SIZE, _LEADING = 9, 12


def _pdf_text(line: str) -> bytes:
    """Escape one line for a PDF string literal. Non-latin-1 characters become '?'."""
    cleaned = "".join(" " if ord(ch) < 32 else ch for ch in line)
    data = cleaned.encode("latin-1", errors="replace")
    return data.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _page_stream(page_lines: list[str]) -> bytes:
    parts = [f"BT /F1 {_FONT_SIZE} Tf {_LEADING} TL {_MARGIN_X} {_TOP_Y} Td".encode("ascii")]
    for index, line in enumerate(page_lines):
        if index:
            parts.append(b"T*")
        parts.append(b"(" + _pdf_text(line) + b") Tj")
    parts.append(b"ET")
    return b"\n".join(parts)


def render_pdf(bill: SyntheticBill, style: str = "plain") -> bytes:
    """The bill as a PDF. Same input, same bytes."""
    lines = layout(bill, style)
    pages = [lines[i : i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)] or [[]]

    # Object numbers: 1 catalog, 2 page tree, 3 font, then (page, content) pairs.
    page_numbers = [4 + 2 * i for i in range(len(pages))]
    kids = " ".join(f"{n} 0 R" for n in page_numbers)
    bodies: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>",
    ]
    for number, page_lines in zip(page_numbers, pages):
        stream = _page_stream(page_lines)
        bodies.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_W} {_PAGE_H}] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {number + 1} 0 R >>"
            ).encode("ascii")
        )
        bodies.append(f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for number, body in enumerate(bodies, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(bodies) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"  # every entry is exactly 20 bytes
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += f"trailer\n<< /Size {len(bodies) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii")
    return bytes(out)
