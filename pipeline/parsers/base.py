"""Parser protocol and the normalized row a parser yields.

One parser per hospital file format. A parser's only job is to STREAM the raw file and
yield normalized rows for codes in the curated set -- it does not classify payers,
parse rates into dollars, or aggregate. Those steps happen once, in the prices stage,
so every format shares the same downstream logic.

Streaming + filtering while reading keeps memory low: a parser must never materialize a
whole raw file. All string fields originate from an untrusted bill/file and are treated
as inert data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Literal, Optional, Protocol, runtime_checkable

from contracts.types import CodeSystem

# Which price column a raw row came from. The prices stage maps negotiated rows into a
# payer group (via payer_groups.classify); cash/gross are their own payer groups.
RateKind = Literal["negotiated", "cash", "gross"]


@dataclass(frozen=True)
class RawPriceRow:
    """One normalized price observation from a hospital file, pre-aggregation."""

    hospital_id: str
    code: str
    raw_payer: str          # raw plan/payer label; "" for cash/gross rows
    raw_rate: str           # verbatim rate cell; may be blank, %, or a formula
    rate_kind: RateKind
    code_system: Optional[CodeSystem] = None


@runtime_checkable
class Parser(Protocol):
    """A per-format parser. ``format_id`` keys it in the registry."""

    format_id: str

    def rows(self, path: str, curated: set[str]) -> Iterator[RawPriceRow]:
        """Yield RawPriceRow for curated codes only, streaming the file."""
        ...
