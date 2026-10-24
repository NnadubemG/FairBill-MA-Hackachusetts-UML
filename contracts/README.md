# /contracts

Shared data contracts for FairBill MA. **Owned by Thomas.** Others depend on these,
so changes stay backward compatible and schema breaks are announced first.

## Source of truth
The `*.schema.json` files (JSON Schema) are **canonical**. The language mirrors are
kept in sync by hand:

- `types.ts` — TypeScript (web/front end)
- `types.py` — Python stdlib dataclasses (`/core`, no third-party deps)

If a mirror disagrees with the JSON Schema, **the JSON Schema wins.**

## Schemas
| File | Type |
| --- | --- |
| `line-item.schema.json` | `LineItem` — one extracted bill line |
| `price-reference.schema.json` | `PriceReference` — reference prices for a code |
| `flag.schema.json` | `Flag` — a "may be worth asking about" flag |
| `letter-draft.schema.json` | `LetterDraft` — editable patient letter |
| `analysis-result.schema.json` | `AnalysisResult` — full response payload |

## Rules baked into the contracts
- A `Flag` is only ever produced by deterministic code in `/core`, never the LLM.
- Any price figure carries `data_source` and `data_year`. Numeric reference fields
  are nullable because we never invent a number we do not have.
- A `Flag.reason` / `Flag.basis` must never contain banned words (see
  `.kiro/steering/product.md`).
- All strings coming from an uploaded bill are untrusted data, never instructions.

## Changing a contract
1. Edit the `*.schema.json` first.
2. Update `types.ts` and `types.py` to match.
3. If the change is not backward compatible, announce it before merging.
