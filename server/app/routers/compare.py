"""GET /api/compare — compare a charge against reference pricing.

Deterministic logic: computes charged/medicare ratio and emits grounded flags.
NO Anthropic client import.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app import reference_data
from app.rate_limit import rate_limit_general
from contracts import CompareResponse, Flag

router = APIRouter()

# A charge this many times the Medicare reference is worth a gentle flag.
_HIGH_RATIO = 3.0


@router.get("/compare", response_model=CompareResponse)
async def compare(
    code: str = Query(...),
    charged: int = Query(..., ge=0),
    units: Optional[int] = Query(default=None, ge=0),
    _: None = Depends(rate_limit_general),
) -> CompareResponse:
    info = reference_data.get_procedure(code)
    medicare = info.medicare_reference if info else None
    price_range = info.ma_price_range if info else None

    ratio: Optional[float] = None
    flags: List[Flag] = []

    if medicare and medicare > 0:
        ratio = round(charged / medicare, 2)
        if ratio >= _HIGH_RATIO:
            flags.append(
                Flag(
                    explanation=(
                        "This charge is noticeably higher than the Medicare "
                        "reference for this code. It may be worth asking the "
                        "billing office about."
                    ),
                    basis="medicare_reference",
                )
            )

    if price_range and price_range.high is not None and charged > price_range.high:
        flags.append(
            Flag(
                explanation=(
                    "This charge is above the typical Massachusetts range we "
                    "have for this service. Confirming it with the provider can "
                    "help."
                ),
                basis="ma_price_range",
            )
        )

    return CompareResponse(
        code=code,
        charged=charged,
        medicare_reference=medicare,
        ma_price_range=price_range,
        ratio_to_medicare=ratio,
        flags=flags,
    )
