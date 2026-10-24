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
