# Design: Synthetic bill generator

## Overview

`generate_bill(seed, scenario)` returns a `SyntheticBill`: a fictional bill plus its ground truth.
Renderers turn a bill into text and PDF. A small CLI writes JSON, text, and PDF files. Everything
is stdlib only. Unlike `/core`, `/synthetic` may write files, but only through the CLI.

Reference prices in the catalog are fictional and labelled `synthetic-demo`. They stand in for
ND's real processed data until it is wired in.

## Architecture

```
seed + scenario
      |
      v
generate_bill()  <-- catalog.py (fictional procedures + reference prices)
      |
      v
SyntheticBill (JSON, ground truth)
      |
      +--> render_text(bill, style)  -> .txt
      +--> render_pdf(bill, style)   -> .pdf
      v
CLI: python -m synthetic --seed N --scenario S --style plain --out DIR
```

```
synthetic/
  __init__.py     exports generate_bill, SCENARIOS, render_text, render_pdf
  catalog.py      CATALOG entries and the PriceReference list
  generate.py     generate_bill, to_json
  render.py       render_text, render_pdf (minimal stdlib PDF writer)
  __main__.py     CLI
  samples/        committed outputs for fixed seeds
tests/synthetic/  unit and property tests
```

Key decisions:
- **Prices relate to the references, not to `MEDICARE_MULTIPLE`.** For a catalog entry with fictional
  Medicare price `M`: `ma_range_low = 1.1*M`, `ma_range_high = 2.0*M`. Normal amounts are within
  `[low, 1.5*M]`, so they stay clean for any multiple of 1.5 or more. Anomalous amounts are
  `10 * ma_range_high`, which exceeds both thresholds for any multiple up to about 20.
- **Quantity.** Some lines have quantity above 1. The billed amount is `quantity * unit_amount`, and the
  unit amount follows the rule above, so `/core`'s per-unit logic is exercised.
- **Codes.** The catalog mixes CPT, HCPCS, and revenue codes (including a zero-padded `0120`).
  The `unknown_code` scenario uses a code that is not in the references.
- **Ids** are `"1"`, `"2"`, ... in printed order.
- **Plain labels** are written by us. The printed description is an abbreviated version, so
  `description` (plain label) and `raw_description` (as printed) differ.
- **Injection text** lives in a `raw_description`. Its source file carries the `language-guard: allow`
  marker because the text deliberately contains words the project bans in product copy.
- **PDF writer.** One Courier font, fixed 55 lines per page, `latin-1` text with `?` for anything else,
  `( ) \` escaped, no dates or ids in the file, so output is byte-identical for equal input.

## Components and Interfaces

```python
SCENARIOS: tuple[str, ...]  # clean, duplicate, high_price, unknown_code, injection, mixed
def generate_bill(seed: int, scenario: str) -> SyntheticBill
def to_json(bill: SyntheticBill) -> str          # sorted keys, 2-space indent, trailing newline
def render_text(bill: SyntheticBill, style: str = "plain") -> str   # style: plain | messy
def render_pdf(bill: SyntheticBill, style: str = "plain") -> bytes
```

CLI: `python -m synthetic --seed 7 --scenario mixed --style messy --out DIR` writes
`bill-<scenario>-<seed>.json`, `.txt`, and `.pdf` into `DIR` and nothing else.
`python -m synthetic --samples` regenerates `synthetic/samples/` from fixed seeds.

## Data Models

New contract `contracts/synthetic-bill.schema.json`, mirrored in `types.ts` and `types.py`. It reuses
`LineItem` and `PriceReference` and adds:
- `BillMetadata`: `hospital_name`, `statement_date` (ISO date), `total_billed`.
- `ExpectedFlag`: `line_item_id`, `flag_type` (same values as `Flag.flag_type`).
- `SyntheticBill`: `bill_id`, `seed`, `scenario`, `bill_metadata`, `line_items`, `price_references`,
  `expected_flags`.

## Correctness Properties

- **PS1** For any seed and scenario, `analyze(bill.line_items, bill.price_references)` has exactly the
  pairs in `bill.expected_flags`. (Req 2.2)
- **PS2** `generate_bill` is deterministic. (Req 1.1)
- **PS3** `to_json` then `json.loads` then rebuild gives an equal bill. (Req 5.1)
- **PS4** Line item ids are unique and every expected flag id exists. (Req 2.1)
- **PS5** Rendering never changes the bill, and rendering twice gives equal output. (Req 4.4)
- **PS6** `total_billed` equals the sum of billed amounts to the cent. (Req 2.1)

## Error Handling

Unknown scenario or style raises `ValueError` with the valid names. The CLI refuses an output path
that is a file, creates the folder if missing, and writes nothing outside it.

## Testing Strategy

Test cases (listed before tasks). Hypothesis properties above run over seeds 0 to 10,000 and all scenarios.

**Generator**
- TS-G1 same seed and scenario give equal bills.
- TS-G2 different seeds give different bills (across 20 seeds not all equal).
- TS-G3 `clean`: no expected flags, and `analyze` returns none.
- TS-G4 `duplicate`: two lines identical except id; expected duplicate flags for both; `analyze` matches.
- TS-G5 `high_price`: one line at 10 times the range high; expected both price flags on that id; `analyze` matches.
- TS-G6 `unknown_code`: one coded line absent from references; expected `no_reference_found` only for it.
- TS-G7 `injection`: instruction-like text in a `raw_description`; expected flags empty; `analyze` output never contains that text.
- TS-G8 `mixed`: duplicate, high price, and unknown code together; `analyze` matches.
- TS-G9 ids are `"1"..."n"` and every expected id exists.
- TS-G10 every reference has `data_source == "synthetic-demo"` and an integer `data_year`; names are marked fictional.
- TS-G11 `total_billed` equals the sum of amounts.
- TS-G12 amounts are finite, positive, and have at most 2 decimals.
- TS-G13 lines with quantity above 1 have `billed_amount == quantity * unit amount`.
- TS-G14 unknown scenario raises `ValueError`.

**Rendering**
- TS-R1 plain text contains each line's code, printed description, and amount.
- TS-R2 messy text uses `MM/DD/YY` dates and comma amounts, has header and footer lines, and still contains each code and description.
- TS-R3 text output is deterministic; unknown style raises `ValueError`.
- TS-R4 PDF starts with `%PDF-`, ends with `%%EOF`, every cross-reference offset points at `N 0 obj`, and `startxref` points at `xref`.
- TS-R5 PDF text contains every line's code and amount, including descriptions with `(`, `)`, `\`.
- TS-R6 a bill with more than 55 lines gives more than one page; PDF output is deterministic.
- TS-R7 non-latin-1 characters become `?` and do not raise.

**CLI and samples**
- TS-C1 the CLI writes the three expected files into the given folder and nothing else.
- TS-C2 committed samples equal freshly generated ones.
- TS-C3 output path that is an existing file is rejected.

**Contract**
- TS-K1 the schema parses, its required keys match the dataclass fields, and expected flag types match `FlagType`.

## Out of scope

Image bills (JPEG/PNG) need a third-party library. Insurance fields (EOB, payer, copay) are not modeled yet.
