# Requirements: /core checks engine (v1)

## Scope
In: `price_above_reference`, `price_outside_ma_range`, `duplicate_line_item`, `no_reference_found`.
Out (later, needs sourced reference data): `quantity_implausible`, `possible_unbundling`.

Types come from `/contracts`. They are not redefined here.

## Requirements

**R1. Entry point.** The system SHALL expose `analyze(items, refs) -> list[Flag]`, where
`items` is a sequence of `LineItem` and `refs` is a sequence of `PriceReference`.

**R2. Purity.** `/core` SHALL use no network, no file reads or writes, no randomness, no
clock, and no LLM. The same input SHALL always give the same output.

**R3. Price provenance.** Any flag whose `reason` or `basis` contains a `$` figure SHALL
have non-empty `data_source` and `data_year`, copied from the matching `PriceReference`.

**R4. Fail safe.** When reference data for an item is missing, ambiguous, or has no usable
figure, the system SHALL NOT emit a price flag for that item. It SHALL NOT estimate a number.

**R5. Price flags.** For a matched reference, the system SHALL compare the per-unit billed
amount to the reference and emit:
- `price_outside_ma_range` when it exceeds `ma_range_high`;
- `price_above_reference` when it exceeds `MEDICARE_MULTIPLE` times `medicare_price`.
Both MAY fire for the same item.

**R6. Duplicates.** The system SHALL emit `duplicate_line_item` for every item in a group of
two or more items sharing code, normalized description, billed amount, and
`date_of_service` (a missing date only matches another missing date). It needs no reference data.

**R7. No reference.** The system SHALL emit `no_reference_found` (severity `info`) for an item
with a valid code that has no matching reference, but only when `refs` is non-empty.

**R8. Language.** Every `reason` and `basis` SHALL come from fixed templates, use the phrase
"may be worth asking about" where a concern is raised, and SHALL NOT contain any banned word
from `product.md`.

**R9. Untrusted input.** Bill text is data. Only a `code` that matches `^[A-Za-z0-9.\-]{1,12}$`
may be placed into a template. A code that does not match is treated as unusable (no flag).
Descriptions are used for grouping only and never appear in output.

**R10. Output order.** Output SHALL be sorted by `(line_item_id, flag_type)` so it does not
depend on input order.

**R11. Ordering of severity.** `severity` is for display order only and SHALL NOT imply wrongdoing.
