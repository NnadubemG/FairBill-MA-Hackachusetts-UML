# Design: /core checks v2 (quantity and unbundling)

## Overview

Two new pure checks join the three from v1. `analyze(items, refs, *, quantity_limits=(), bundle_pairs=())`
runs all of them. New data arrives through two new contracts, produced outside `/core` (ND's pipeline).
Nothing here reads files or the network.

## Architecture

```
items, refs, quantity_limits, bundle_pairs
   |
   v
analyze() --> check_price / check_duplicates / check_coverage   (v1, unchanged)
          --> check_quantity     core/checks/quantity.py
          --> check_unbundling   core/checks/unbundling.py
   |
   v
Flag[] sorted by every field
```

Shared helpers move out of v1 modules so both versions use them:
- `core/dates.py`: `service_date(item)` (was private in `duplicates.py`).
- `core/reference.py`: `has_provenance(record)` (was private in `price.py`), and `ReferenceIndex` accepts any
  record with `code`, `code_system`, `data_year` (so `QuantityLimit` reuses the same normalization and lookup).

## Components and Interfaces

```python
def analyze(items, refs, *, quantity_limits=(), bundle_pairs=()) -> list[Flag]
def check_quantity(items, index: ReferenceIndex) -> list[Flag]
def check_unbundling(items, pairs) -> list[Flag]
```

Templates (no `$`, only validated codes and numbers):
- quantity reason: "The quantity of {q} for this item may be worth asking about. It is more than the typical maximum of {max} units we have on file for this code."
  basis: "Typical maximum for code {code}: {max} units. Source: {source}, {year}."
- unbundling reason: "Code {code_2} appears on the same bill as code {code_1}. These two codes are often billed together as one service, so it may be worth asking about whether both are expected."
  basis: "A published coding edit pairs code {code_1} with code {code_2}. Source: {source}, {year}."

Key decisions:
- **Quantity numbers** print without a trailing `.0` when whole.
- **Unbundling codes** are compared after `clean_code` (uppercase, validated), with exact match, since NCCI covers CPT/HCPCS.
- **Dates**: both undated, or both dated and equal, count as the same visit. Anything else is silent.
- **One flag per (item, pair)**; exact duplicate pairs are collapsed first.
- **Severity**: quantity `low`; unbundling `medium` for indicator `"0"`, `low` for `"1"`.

## Data Models

New contracts (additive):
- `QuantityLimit`: `code`, `code_system?`, `max_units`, `data_source`, `data_year`.
- `BundlePair`: `code_1`, `code_2`, `modifier_indicator` (`"0"|"1"|"9"`), `data_source`, `data_year`.
- `SyntheticBill` gains optional `quantity_limits`, `bundle_pairs`; scenario values `quantity`, `unbundling`.

## Correctness Properties

- **PQ1** With no limits and no pairs, `analyze` equals the v1 result. (R1)
- **PQ2** No banned words in any flag, with limits and pairs supplied. (R4.1)
- **PQ3** Bill text (descriptions, ids) never appears in flag text. (R4.2)
- **PQ4** Order of items, limits, and pairs never changes the output. (R4.3)
- **PQ5** `analyze` never raises, including NaN/infinity quantities and odd pairs. (R4.4)
- **PQ6** Every `quantity_implausible` flag has a limit with provenance and a quantity strictly above it. (R2)
- **PQ7** Every `possible_unbundling` flag points at an item whose code is `code_2` of some supplied pair. (R3)
- **PQ8** For any generated synthetic bill, `analyze` equals `expected_flags`. (R5.3)

## Error Handling

Unusable data produces silence, as in v1: bad quantity, bad limit, missing provenance, unusable code, unknown
indicator, mixed dated/undated items.

## Testing Strategy

Test cases (listed before tasks).

**Quantity**
- TQ1 quantity above the limit: one flag, severity `low`, source and year set, text states the limit.
- TQ2 quantity equal to the limit: no flag.
- TQ3 no limit for the code, or ambiguous limits: no flag.
- TQ4 quantity missing, zero, negative, NaN, infinity: no flag.
- TQ5 `max_units` zero, negative, NaN: no flag.
- TQ6 limit with blank source or non-integer year: no flag.
- TQ7 REV code `0120` matches limit `120`; CPT `00100` does not match `100`.
- TQ8 fractional quantity above a whole limit flags; `2.0` prints as `2`.
- TQ9 two limits for one code, different years: newest wins.

**Unbundling**
- TU1 both codes present, both undated: flag on the `code_2` item only.
- TU2 both present, same date: flag; different dates: no flag; one dated one not: no flag.
- TU3 only `code_1` present, or only `code_2` present: no flag.
- TU4 indicator `"0"` gives `medium`; `"1"` gives `low`; `"9"` or `"7"` gives nothing.
- TU5 pair with blank source, bad year, or an unusable code: ignored.
- TU6 item with `code_system` REV or DRG is ignored; `CPT`, `HCPCS`, and `None` are used.
- TU7 two `code_2` items: both flagged; two identical pairs: one flag each.
- TU8 two different pairs hit one `code_2` item: two flags with different basis.
- TU9 text names both codes and contains no `$` or banned word.

**Engine and v1 compatibility**
- TE1 `analyze(items, refs)` equals the earlier result for every v1 test (existing tests keep passing).
- TE2 the new arguments are keyword-only.

**Synthetic**
- TS-N1 `quantity` scenario: one line over its limit; expected `quantity_implausible` only.
- TS-N2 `unbundling` scenario: 93000 and 93005 together; expected `possible_unbundling` on the 93005 line only.
- TS-N3 clean, duplicate, high_price, unknown_code, injection, and mixed bills never trigger the new checks.
- TS-N4 `unbundle_only` codes never appear in other scenarios.
- TS-N5 contract mirrors match the schemas.

## Out of scope

Modifier handling (`LineItem` has no modifier field), place-of-service rules, and anything needing real data.
