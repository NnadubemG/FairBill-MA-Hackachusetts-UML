"""Letter handler: a fixed template, with one optional model-written paragraph.

Flow (see the design doc):
  request -> clean patient fields -> (coding review only) build safe item facts
          -> one model call for the reason paragraph, if there are items
          -> paragraph accepted by code, or the fixed fallback
          -> assemble the body from the template -> LetterDraft

The model is called only for a coding review that has at least one usable flag. It is called
at most once and never retried. Any failure in the model path means the fixed fallback
paragraph is used. The handler does not raise for a model failure. An unknown letter type
raises ``InvalidLetterType`` (a caller bug). Nothing about the patient, the flags or the
model reply is logged or written to disk.
"""

from __future__ import annotations

from backend.extract.llm_client import LLMClient

from . import config, prompts, templates
from ._contracts import LetterDraft
from .checks import accept_paragraph
from .facts import ItemFact, build_items
from .models import CODING_REVIEW, LETTER_TYPES, InvalidLetterType, LetterRequest, LetterResult
from .request import clean_patient

# Fixed, generic warning. Never contains patient or bill content.
WARN_STANDARD_WORDING = "Standard wording was used for the reason paragraph."


def _model_paragraph(letter_type: str, items: list[ItemFact], client: LLMClient) -> str | None:
    """Ask the model once. Return the paragraph only if it passes every check."""
    try:
        raw = client.invoke(
            system=prompts.build_system_prompt(),
            content=prompts.build_user_content(letter_type, items),
            max_tokens=config.MAX_TOKENS,
        )
        text = prompts.parse_response(raw)
    except Exception:  # noqa: BLE001 - deterministic fallback for ANY model failure
        return None  # no exception detail is kept or logged (privacy)
    if text is not None and accept_paragraph(text, items):
        return text.strip()
    return None


def generate_letter(request: LetterRequest, *, client: LLMClient) -> LetterResult:
    """Build the letter for ``request``.

    ``client`` is injected (use ``FakeLLMClient`` for dev and tests).
    """
    letter_type = request.letter_type
    if letter_type not in LETTER_TYPES:
        raise InvalidLetterType("unknown letter type")  # never echo the value

    patient = clean_patient(request.patient)
    warnings: list[str] = []

    items: list[ItemFact] = []
    if letter_type == CODING_REVIEW:
        items, item_warnings = build_items(request.flags, request.line_items)
        warnings.extend(item_warnings)

    paragraph: str | None = None
    if items:  # the only case where the model is used
        paragraph = _model_paragraph(letter_type, items, client)
        if paragraph is None:
            warnings.append(WARN_STANDARD_WORDING)

    used_fallback = paragraph is None
    if paragraph is None:
        paragraph = templates.fallback_paragraph(letter_type, has_items=bool(items))

    draft = LetterDraft(
        subject=templates.subject(letter_type, patient),
        body=templates.assemble_body(letter_type, patient, paragraph, items),
        referenced_line_item_ids=templates.referenced_line_ids(items),
    )
    return LetterResult(draft=draft, used_fallback=used_fallback, warnings=warnings)


__all__ = ["generate_letter", "WARN_STANDARD_WORDING"]
