"""POST /api/analyze — analyze extracted line items.

Deterministic logic over the submitted line items + reference data:
  - attaches a plain-language label and Medicare/MA references per line,
  - flags duplicates, arithmetic that looks off, and charges well above reference.
NO Anthropic client import.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from fastapi import APIRouter, Depends

from app import reference_data
from app.rate_limit import rate_limit_general
from contracts import AnalysisResult, AnalyzeRequest, AnalyzeResponse, Flag, LineItem

router = APIRouter()

_HIGH_RATIO = 3.0


def _duplicate_indexes(items: List[LineItem]) -> Dict[int, bool]:
    """Mark line indexes that share the same (code, charge) with another line."""
    seen: Dict[tuple, List[int]] = defaultdict(list)
    for i, it in enumerate(items):
        if it.code is not None:
            seen[(it.code, it.charge)].append(i)
    dupes: Dict[int, bool] = {}
    for _, idxs in seen.items():
        if len(idxs) > 1:
            for i in idxs:
                dupes[i] = True
    return dupes


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    req: AnalyzeRequest,
    _: None = Depends(rate_limit_general),
) -> AnalyzeResponse:
    dupes = _duplicate_indexes(req.line_items)
    results: List[AnalysisResult] = []

    for i, item in enumerate(req.line_items):
        flags: List[Flag] = []
        info = reference_data.get_procedure(item.code) if item.code else None
        label = info.plain_language_label if info else (item.description or "Charge")
        medicare = info.medicare_reference if info else None
        price_range = info.ma_price_range if info else None

        if dupes.get(i):
            flags.append(
                Flag(
                    explanation=(
                        "Another line has the same code and amount. It may be a "
                        "duplicate worth asking about."
                    ),
                    basis="duplicate_detection",
                )
            )

        if medicare and medicare > 0 and item.charge is not None:
            if item.charge / medicare >= _HIGH_RATIO:
                flags.append(
                    Flag(
                        explanation=(
                            "This charge is noticeably higher than the Medicare "
                            "reference for this code — worth confirming."
                        ),
                        basis="medicare_reference",
                    )
                )

        if (
            price_range
            and price_range.high is not None
            and item.charge is not None
            and item.charge > price_range.high
        ):
            flags.append(
                Flag(
                    explanation=(
                        "This charge is above the typical Massachusetts range we "
                        "have for this service."
                    ),
                    basis="ma_price_range",
                )
            )

        results.append(
            AnalysisResult(
                line_index=i,
                plain_language_label=label,
                medicare_reference=medicare,
                ma_price_range=price_range,
                flags=flags,
            )
        )

    return AnalyzeResponse(results=results)
