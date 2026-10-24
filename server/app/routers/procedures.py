"""GET /api/procedures — look up known procedures/codes for reference.

Deterministic lookup over reference data. NO Anthropic client import.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app import reference_data
from app.rate_limit import rate_limit_general
from contracts import ProceduresResponse

router = APIRouter()


@router.get("/procedures", response_model=ProceduresResponse)
async def procedures(
    query: Optional[str] = Query(default=None),
    codes: Optional[List[str]] = Query(default=None),
    _: None = Depends(rate_limit_general),
) -> ProceduresResponse:
    if codes:
        found = [p for c in codes if (p := reference_data.get_procedure(c))]
        return ProceduresResponse(procedures=found)

    results = reference_data.all_procedures()
    if query:
        q = query.lower()
        results = [
            p
            for p in results
            if q in p.code.lower()
            or q in p.plain_language_label.lower()
            or q in p.description.lower()
        ]
    return ProceduresResponse(procedures=results)
