"""POST /api/letter — draft a letter for the user to review and send themselves.

Calls Anthropic (model from LETTER_MODEL_ID). One of only two modules that import
`anthropic_client`. The drafted subject and body are run through the banned-words
guardrail before returning; the app never sends anything on the user's behalf.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app import anthropic_client, guardrails
from app.rate_limit import rate_limit_model
from contracts import LetterDraft, LetterRequest, LetterResponse

router = APIRouter()

_LETTER_PURPOSE = {
    "itemized_bill_request": "politely request a fully itemized bill",
    "billing_question": "politely ask a question about a charge",
    "charge_dispute": "politely dispute a specific charge and ask for review",
    "insurance_appeal": "politely appeal an insurance decision",
    "financial_assistance_request": "politely ask about financial assistance options",
}

_SYSTEM = (
    "You draft a short, polite letter a patient can review, edit, and send "
    "themselves to a medical provider or insurer. Keep it calm, plain-spoken, and "
    "non-accusatory. Provide general information only. Avoid professional "
    "conclusions, accusations, and outcome claims. Return ONLY valid JSON of the "
    'form {"subject": string, "body": string} and nothing else.'
)


def _build_prompt(req: LetterRequest) -> str:
    purpose = _LETTER_PURPOSE.get(req.type, "politely ask a question")
    lines = [
        f"Draft a letter to the {req.recipient} to {purpose}.",
    ]
    if req.context:
        lines.append(f"Patient's context: {req.context}")
    if req.line_items:
        lines.append("Relevant charges:")
        for it in req.line_items:
            code = it.code or "(no code)"
            charge = "unknown" if it.charge is None else f"{it.charge} cents"
            lines.append(f"- {code}: {it.description} — {charge}")
    lines.append(
        "Leave clearly marked placeholders in [BRACKETS] for the patient's name, "
        "account number, and any details you do not have."
    )
    return "\n".join(lines)


def _parse(raw: str) -> tuple[str, str]:
    import json

    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    data = json.loads(text)
    return str(data.get("subject", "")), str(data.get("body", ""))


@router.post("/letter", response_model=LetterResponse)
async def letter(
    req: LetterRequest,
    _: None = Depends(rate_limit_model),
) -> LetterResponse:
    model = anthropic_client.letter_model_id()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="letter_model_not_configured",
        )

    try:
        raw = anthropic_client.complete(
            model=model,
            system=_SYSTEM,
            user_content=_build_prompt(req),
            max_tokens=1500,
            temperature=0.3,
        )
    except anthropic_client.AnthropicConfigError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="letter_unavailable",
        )
    except anthropic_client.AnthropicCallError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="letter_failed",
        )

    try:
        subject, body = _parse(raw)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="letter_bad_model_output",
        )

    # Guardrail the model-authored text before returning.
    subject, _s = guardrails.scrub(subject)
    body, _b = guardrails.scrub(body)

    return LetterResponse(
        letter=LetterDraft(
            type=req.type,
            recipient=req.recipient,
            subject=subject,
            body=body,
        )
    )
