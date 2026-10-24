"""POST /api/extract — turn raw bill/EOB text into structured line items.

Calls Anthropic (model from EXTRACT_MODEL_ID). This is one of only two modules
that import `anthropic_client`. The model-generated plain-language labels are run
through the banned-words guardrail before returning.
"""

from __future__ import annotations

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app import anthropic_client, guardrails
from app.rate_limit import rate_limit_model
from contracts import ExtractRequest, ExtractResponse, LineItem

router = APIRouter()

_SYSTEM = (
    "You extract line items from a US medical bill or Explanation of Benefits. "
    "Return ONLY valid JSON with this exact shape and nothing else:\n"
    '{"line_items":[{"code":string|null,"description":string,"units":integer,'
    '"charge":integer_cents|null,"confidence":number_0_to_1,'
    '"needs_confirmation":boolean}],"overall_confidence":number_0_to_1}\n'
    "Money is whole US cents (e.g. $12.34 -> 1234). Use null when a value is not "
    "legible. Write descriptions in plain language. Provide general information "
    "only. Avoid professional conclusions, accusations, and outcome claims."
)


def _clamp01(x: float) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.0


def _parse(raw: str) -> ExtractResponse:
    """Parse model JSON into an ExtractResponse, tolerating stray prose/fences."""
    text = raw.strip()
    # Strip markdown fences if the model added them.
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
    # Grab the outermost JSON object.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    data = json.loads(text)

    items: List[LineItem] = []
    for raw_item in data.get("line_items", []):
        label = raw_item.get("description", "") or ""
        label, _ = guardrails.scrub(label)
        items.append(
            LineItem(
                code=raw_item.get("code"),
                description=label,
                units=int(raw_item.get("units", 1) or 1),
                charge=raw_item.get("charge"),
                confidence=_clamp01(raw_item.get("confidence", 0.0)),
                needs_confirmation=bool(raw_item.get("needs_confirmation", False)),
            )
        )

    return ExtractResponse(
        line_items=items,
        overall_confidence=_clamp01(data.get("overall_confidence", 0.0)),
    )


@router.post("/extract", response_model=ExtractResponse)
async def extract(
    req: ExtractRequest,
    _: None = Depends(rate_limit_model),
) -> ExtractResponse:
    if not req.text.strip() and not req.document_base64:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="text_or_document_required",
        )
    if bool(req.document_base64) != bool(req.document_media_type):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="document_data_incomplete",
        )

    model = anthropic_client.extract_model_id()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="extract_model_not_configured",
        )

    try:
        raw = anthropic_client.complete(
            model=model,
            system=_SYSTEM,
            user_content=(
                req.text.strip()
                or "Read the attached medical bill or Explanation of Benefits and extract its line items."
            ),
            document_base64=req.document_base64,
            document_media_type=req.document_media_type,
            max_tokens=2048,
            temperature=0.0,
        )
    except anthropic_client.AnthropicConfigError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="extract_unavailable",
        )
    except anthropic_client.AnthropicCallError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="extract_failed",
        )

    try:
        return _parse(raw)
    except (json.JSONDecodeError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="extract_bad_model_output",
        )
