# FairBill MA

A free, no-login web tool for adult patients in Massachusetts. Upload a hospital
bill, confirm the extracted line items, and get plain-language labels, Medicare
reference prices, Massachusetts hospital price ranges, and "may be worth asking
about" flags, each with a reason and a data basis. You can also generate an editable
letter draft. **Nothing is stored.**

Built for Hackachusetts (Massachusetts AI Coalition Hackathon, 2026) — Healthcare &
Biotech track.

> This is guidance for people navigating their own bill. It is **not legal advice and
> not medical advice.**

## How it works
1. A patient uploads a bill. The LLM extracts structured line items.
2. The patient confirms the extracted items.
3. Deterministic code in `/core` compares each item to reference data and produces
   flags — never the LLM.
4. The patient can generate an editable letter draft.

Every price figure shown carries a `data_source` and a `data_year`. We never invent
numbers.

## Repository layout
| Path | Purpose |
| --- | --- |
| `contracts/` | JSON Schema source of truth + TypeScript and Python mirrors |
| `core/` | Deterministic checks engine (pure Python 3.12) |
| `synthetic/` | Synthetic bill generator for tests and demos |
| `docs/` | `kiro-log.md` and writeup material |
| `.kiro/steering/` | Project rules and conventions |
| `.kiro/hooks/` | Agent hooks |

See `.kiro/steering/` for the full product, tech, structure, and testing rules.

## Privacy
No persistence of user data. Request bodies and uploaded content are never logged.

## License
MIT. See `LICENSE`.
