"""Fixed letter template, fallback paragraphs, and body assembly.

Everything here is deterministic. The only places text from outside enters the letter are:
- the patient's own fields (name, account number, hospital, date, notes), cleaned and
  inserted into fixed slots, and
- the reason paragraph (model text that passed the checks, or the fixed fallback), and
- the items section (a line's safe code/amount/date and the flag's basis).

The fixed text asks for documents and explanations. It never says a charge is wrong,
never mentions a law, and never sets a deadline. Tests run every fixed string through the
banned-word and tone checks.
"""

from __future__ import annotations

from typing import Sequence

from .facts import ItemFact
from .models import CODING_REVIEW, FINANCIAL_ASSISTANCE, ITEMIZED_BILL, PatientFields
from .request import clean_patient

TOP_LINE = "Draft for you to review and edit before sending."

PLACEHOLDER_NAME = "[Your name]"
PLACEHOLDER_ACCOUNT = "[Account number]"
PLACEHOLDER_HOSPITAL = "[Hospital name]"
PLACEHOLDER_DATE = "[Date]"

GREETING = "Dear Billing Office,"
ITEMS_HEADING = "These are the lines I am asking about:"
NOTES_HEADING = "Additional notes from me:"
CLOSING = "Thank you for your help. Please let me know if you need anything else from me."
SIGN_OFF = "Sincerely,"

SUBJECTS = {
    ITEMIZED_BILL: "Request for an itemized bill with codes",
    CODING_REVIEW: "Request for a coding and billing review",
    FINANCIAL_ASSISTANCE: "Request for a financial assistance review",
}

_FALLBACK_PARAGRAPHS = {
    ITEMIZED_BILL: (
        "I would like to understand my bill better. "
        "A bill that shows each charge with its billing code would help me see what each "
        "line is for. "
        "I would be grateful for your help."
    ),
    FINANCIAL_ASSISTANCE: (
        "I would like to learn what help may be available with this bill. "
        "I am asking about the hospital's financial assistance options. "
        "I would be grateful for your help."
    ),
}
_CODING_PARAGRAPH_WITH_ITEMS = (
    "I would like to understand the charges listed below. "
    "I am asking how these lines were coded and billed. "
    "I would be grateful for a review so that I can understand them better."
)
_CODING_PARAGRAPH_NO_ITEMS = (
    "I would like to understand the charges on my bill. "
    "I am asking how they were coded and billed. "
    "I would be grateful for a review so that I can understand them better."
)

_CODING_REQUEST_TAIL = (
    "how each one was coded and billed, and send me the documentation that supports the "
    "codes and the units. If anything needs to be updated after your review, please send "
    "me a corrected statement."
)
_REQUESTS = {
    ITEMIZED_BILL: (
        "Please send me an itemized bill that lists each charge with its billing code, the "
        "date of service, the units, and the amount. Please also include any payments and "
        "adjustments that have been applied."
    ),
    FINANCIAL_ASSISTANCE: (
        "Please tell me whether I may qualify for financial assistance (sometimes called "
        "charity care or free care) under your policy. Please send me a copy of the policy "
        "and the application, and let me know how to apply."
    ),
}
_CODING_REQUEST_WITH_ITEMS = "For the lines listed above, please let me know " + _CODING_REQUEST_TAIL
_CODING_REQUEST_NO_ITEMS = "For the charges on my bill, please let me know " + _CODING_REQUEST_TAIL


def subject(letter_type: str, patient: PatientFields) -> str:
    """The fixed subject line for the type, with the account number when given."""
    base = SUBJECTS[letter_type]
    account = clean_patient(patient).account_number
    return f"{base} - Account {account}" if account else base


def fallback_paragraph(letter_type: str, has_items: bool = False) -> str:
    """The fixed reason paragraph used when the model text is not used. No figures."""
    if letter_type == CODING_REVIEW:
        return _CODING_PARAGRAPH_WITH_ITEMS if has_items else _CODING_PARAGRAPH_NO_ITEMS
    return _FALLBACK_PARAGRAPHS[letter_type]


def requests_text(letter_type: str, has_items: bool = False) -> str:
    """The fixed request text for the type."""
    if letter_type == CODING_REVIEW:
        return _CODING_REQUEST_WITH_ITEMS if has_items else _CODING_REQUEST_NO_ITEMS
    return _REQUESTS[letter_type]


def _entry(item: ItemFact) -> str:
    """One line of the items section: safe code, amount, date, then the flag's basis."""
    head = f"Code {item.code}" if item.code else "An item"
    if item.amount:
        head += f", {item.amount}"
    if item.date:
        head += f", date of service {item.date}"
    entry = head + "."
    basis = item.basis.strip()
    if basis:
        if basis[-1] not in ".?!":
            basis += "."
        entry += " " + basis
    return "- " + entry


def items_section(items: Sequence[ItemFact]) -> str:
    """The list of lines the patient asks about. Empty text if there are none."""
    if not items:
        return ""
    return "\n".join([ITEMS_HEADING, *(_entry(i) for i in items)])


def referenced_line_ids(items: Sequence[ItemFact]) -> list[str]:
    """Ids of the cited lines, in input order, without duplicates."""
    seen: set[str] = set()
    ids: list[str] = []
    for item in items:
        if item.line_item_id not in seen:
            seen.add(item.line_item_id)
            ids.append(item.line_item_id)
    return ids


def assemble_body(
    letter_type: str,
    patient: PatientFields,
    paragraph: str,
    items: Sequence[ItemFact] = (),
) -> str:
    """Build the letter body. Patient fields are cleaned again here (it is idempotent).

    The items section is used for coding reviews only.
    """
    p = clean_patient(patient)
    name = p.name or PLACEHOLDER_NAME
    account = p.account_number or PLACEHOLDER_ACCOUNT
    hospital = p.hospital or PLACEHOLDER_HOSPITAL
    date = p.date or PLACEHOLDER_DATE

    shown_items = list(items) if letter_type == CODING_REVIEW else []
    has_items = bool(shown_items)

    blocks: list[str] = [
        TOP_LINE,
        date,
        f"{hospital} Billing Office\nRe: Account number {account}",
        GREETING,
        f"I am writing about my bill from {hospital}, account number {account}.",
        paragraph.strip(),
    ]
    if has_items:
        blocks.append(items_section(shown_items))
    blocks.append(requests_text(letter_type, has_items))
    if p.notes:
        blocks.append(f"{NOTES_HEADING}\n{p.notes}")
    blocks.append(CLOSING)
    blocks.append(f"{SIGN_OFF}\n{name}")
    return "\n\n".join(blocks)


def all_fixed_texts() -> list[str]:
    """Every fixed string we write ourselves. Used by tests to check tone and wording."""
    texts = [
        TOP_LINE, GREETING, ITEMS_HEADING, NOTES_HEADING, CLOSING, SIGN_OFF,
        PLACEHOLDER_NAME, PLACEHOLDER_ACCOUNT, PLACEHOLDER_HOSPITAL, PLACEHOLDER_DATE,
        *SUBJECTS.values(),
        *_FALLBACK_PARAGRAPHS.values(),
        _CODING_PARAGRAPH_WITH_ITEMS, _CODING_PARAGRAPH_NO_ITEMS,
        *_REQUESTS.values(),
        _CODING_REQUEST_WITH_ITEMS, _CODING_REQUEST_NO_ITEMS,
    ]
    return texts


__all__ = [
    "TOP_LINE",
    "PLACEHOLDER_NAME",
    "PLACEHOLDER_ACCOUNT",
    "PLACEHOLDER_HOSPITAL",
    "PLACEHOLDER_DATE",
    "GREETING",
    "ITEMS_HEADING",
    "NOTES_HEADING",
    "CLOSING",
    "SIGN_OFF",
    "SUBJECTS",
    "subject",
    "fallback_paragraph",
    "requests_text",
    "items_section",
    "referenced_line_ids",
    "assemble_body",
    "all_fixed_texts",
]
