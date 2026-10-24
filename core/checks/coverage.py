"""Coverage check: a valid code with no reference price on file.

Says only that we could not compare the item. It makes no claim about the price.
"""

from __future__ import annotations

from typing import Sequence

from contracts.types import Flag, LineItem
from core import constants
from core.language import no_reference_text
from core.reference import ReferenceIndex, clean_code


def check_coverage(items: Sequence[LineItem], index: ReferenceIndex) -> list[Flag]:
    if not index.has_refs:
        return []  # nothing loaded is not the same as "code not covered"
    flags: list[Flag] = []
    for item in items:
        if index.lookup(item).status != "not_found":
            continue  # found, ambiguous, or no usable code: stay silent
        code = clean_code(item.code)
        if code is None:
            continue
        reason, basis = no_reference_text(code)
        flags.append(
            Flag(
                line_item_id=item.id,
                flag_type="no_reference_found",
                severity=constants.SEVERITY["no_reference_found"],
                reason=reason,
                basis=basis,
                data_source=None,
                data_year=None,
            )
        )
    return flags
