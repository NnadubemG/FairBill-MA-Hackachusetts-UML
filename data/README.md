# /data — FairBill MA data

This folder holds the inputs and committed outputs of the price-data pipeline.

- `raw/` — **gitignored**, large public source files. Never committed.
- `processed/` — small, committed JSON the backend and `/core` read.
- `manifest.json` — one record per source: name, URL, local path, format, download
  date, status (ok/failed/manual), and notes. Updated by `pipeline.download`.
- `procedure_list.csv` — the curated code list the whole pipeline filters to.
- `hospitals_input.csv` — binds each hospital id to its raw file and parser `format_id`.

## Hard rules (from steering)

- Never invent a number. Every price figure carries `data_source` and `data_year`.
  Where we have no figure, the field is `null` — never a placeholder like `0`.
- Percentage- or algorithm-based negotiated charges are **not** dollars; they are
  skipped and written to `pipeline/skipped.log`, never estimated into a number.
- Raw files are streamed and filtered to the curated codes while reading, so a
  multi-hundred-MB file never lands in memory.

## Processed files

| File | Shape | Source stage | Notes |
| --- | --- | --- | --- |
| `procedures.json` | `ProcedureInfo[]` | `procedures` | From `procedure_list.csv`. |
| `hospitals.json` | `{id,name,city,type}[]` | `hospitals` | Public fields only. |
| `prices.json` | `PriceStat[]` | `prices` | Per hospital × code × payer group. |
| `medicare.json` | `PriceReference[]` | `medicare` | MA locality `10112`. Needs the PFS raw file. |
| `reference.json` | `PriceReference[]` | `reference` | One combined record per code for `/core`. |
| `bundle_pairs.json` | `BundlePair[]` | `ncci` | Needs the NCCI raw file. |
| `quantity_limits.json` | `QuantityLimit[]` | `quantity_limits` | Needs `typical_max_units`. |
| `chia_tiers.json` | internal | `chia` | Needs CHIA data. |

## Field names `/core` and the compare API load

`/core` (Thomas) and `backend/compare` read `processed/` by exact filename and the
contract field names above. Keys the compare API returns per code: `code`,
`plain_label`, `code_system`, `hospitals[]` (each with `price_stats` keyed by payer
group: `commercial` / `medicare_advantage` / `medicaid_managed` / `cash` / `gross`),
`medicare`, `reference`, `statewide` (`min`/`median`/`max`/`ma_range_low`/`ma_range_high`),
`data_years`, and `framing_note`. Missing values are `null`.

## Regenerate

```
# 1) fetch raw sources (auto where possible; others print as "manual")
python -m pipeline.download all

# 2) build processed outputs (data-source/year required for raw-backed stages)
python -m pipeline.run procedures --force
python -m pipeline.run hospitals  --force
python -m pipeline.run prices      --force --data-source "<hospital files>" --data-year 2026
python -m pipeline.run medicare    --force --data-source "Medicare national, non-QP" --data-year 2026
python -m pipeline.run ncci        --force --data-source "CMS NCCI PTP" --data-year 2026
python -m pipeline.run reference   --force

# 3) validate before committing
python -m pipeline.validate
```

## Known gaps (as of this writing)

- **Downloaded automatically:** Lahey (Burlington) CMS JSON — the live format test case.
- **Manual / not yet downloaded:** Mass General (~1.8 GB ZIP), BIDMC and other Beth
  Israel Lahey hospitals, UMass Memorial, Baystate, Boston Medical Center, Cambridge
  Health Alliance; CMS Physician Fee Schedule (PFS, drives `medicare.json`); CMS NCCI
  edits (license click-through, drives `bundle_pairs.json`); CHIA procedure prices and
  relative-price tiers (form-gated). See `manifest.json` for the status of each.
- Because PFS/NCCI/CHIA aren't downloaded yet, `medicare.json`, `bundle_pairs.json`,
  and `chia_tiers.json` are absent and the compare API returns `medicare: null` and
  `chia_tier: null` — honest empty, not fabricated.
- A large hospital's `prices.json` contribution is small because we keep only the ~19
  curated codes. If `prices.json` ever approaches ~10 MB, trim the hospital set or codes.
