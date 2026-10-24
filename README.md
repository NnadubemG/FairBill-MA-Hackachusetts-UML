# FairBill MA

**Understand your hospital bill, line by line.** A free, no-login web tool for adults in
Massachusetts. Upload a hospital bill, confirm the lines, and see how each charge compares to
real Massachusetts hospital prices. Anything that stands out is flagged as "may be worth asking
about", with the reason and the data source. Then get an editable letter to send the hospital.
**Nothing is stored.**

- **Track:** Healthcare & Biotech, Hackachusetts 2026
- **Team:** Nnadubem Ganobi, Thomas Williamson, Erwin Coq, David Taveras
- **Live site:** _[public URL being set up; link coming]_
- **How we used Kiro:** [`.kiro/KIRO_WRITEUP.md`](.kiro/KIRO_WRITEUP.md)

> Guidance for people navigating their own bill. **Not legal advice and not medical advice.**

## Quick start (run it locally)

Requires Python 3.12+ (deployment target is 3.12; tested locally on 3.13).

```bash
git clone https://github.com/NnadubemG/FairBill-MA-Hackachusetts-UML.git
cd FairBill-MA-Hackachusetts-UML
pip install -r requirements.txt
python -m app_server.server --port 8000
```

Open **http://127.0.0.1:8000/**. The site runs in **demo mode** without an API key: everything
works except reading an uploaded PDF automatically.

### Try it in 60 seconds
1. On the home page, choose **"Test bill: ER visit priced against real MA data"**, then click **Use sample bill**.
2. Review the lines and click **Check my bill**.
3. You should see the ER visit flagged as above both the Medicare reference and the Massachusetts
   range, the CT scan, chest X-ray, and ECG flagged as above the Medicare reference, a duplicated
   blood test, and one item with no reference price. Each flag shows its reason and data source.
4. Click **Draft a letter**, then **Ask for a coding review**, then **Create my letter**. Copy, download, or print it.
5. Open **Compare prices** in the top menu to see 7 Massachusetts hospitals side by side for any of 19 procedures.

A plain-text copy of the test bill is in [`data/demo/test-bill-er-visit.txt`](data/demo/test-bill-er-visit.txt).

### Turn on automatic bill reading (optional)
Set these in your terminal only. Never put them in a file.
```powershell
$env:ANTHROPIC_API_KEY = "<your key>"
$env:EXTRACT_MODEL_ID  = "<model>"; $env:EXPLAIN_MODEL_ID = "<model>"; $env:LETTER_MODEL_ID = "<model>"
```
With these set, `/health` reports `"model": "live"`.

## How it works
1. **Read.** An AI model turns the bill into structured line items. It only reads.
2. **Confirm.** The patient checks and edits every line before anything is compared.
3. **Check.** Deterministic rules in `/core`, not the AI, compare each line to reference data.
   They flag prices outside the Massachusetts range, duplicates, unusual quantities, and possible
   unbundling.
4. **Ask.** The patient gets an editable letter that asks questions and makes no accusations.

Every price carries a `data_source` and `data_year`. If we don't have a figure, we show "—" and
never guess.

## Run the tests
```bash
pip install -r requirements-dev.txt
python -m pytest -q                                   # core, pipeline, compare, analyze, server
python -m pytest -q evals/tests backend/extract/tests  # AI features + evals (offline)
node --test frontend/app/tests/*.test.mjs frontend/src/compare/tests/*.test.mjs
python -m pipeline.validate                           # data rules: provenance, no negatives, etc.
```

## Repository layout
| Path | What it is |
| --- | --- |
| `frontend/` | The web app (vanilla ES modules, no build step) and the price chart |
| `app_server/` | One server for the web app and API (local) and an AWS Lambda handler |
| `core/` | Deterministic checks engine. Pure Python: no network, no randomness, no AI |
| `backend/` | `extract` (bill reading), `explain`, `letter`, `analyze`, `compare` |
| `pipeline/` | Downloads and parses public price files into `data/processed/` |
| `data/` | Processed price data, source manifest, demo test bill |
| `contracts/` | JSON Schema contracts shared by every part (+ TS/Python mirrors) |
| `synthetic/` | Fictional bills with known answers, for tests and evals |
| `evals/` | Scores the AI features against the synthetic bills |
| `infra/` | AWS SAM template (Lambda + CloudFront) and deploy scripts; see also `Dockerfile` |
| `.kiro/` | Kiro steering, specs, hooks, and the Kiro write-up |

## Data sources
- **Hospital prices:** the public machine-readable standard-charges files that hospitals must publish
  under federal price-transparency rules (45 CFR 180), downloaded from each hospital's own site.
  Seven Massachusetts hospitals: Lahey Hospital & Medical Center, Beth Israel Deaconess Medical Center,
  BID-Milton, BID-Needham, BID-Plymouth, Anna Jaques Hospital, and South Shore Hospital. 19 common
  procedures, 405 price records, 2026 files.
- **Medicare reference:** CMS Medicare Physician Fee Schedule 2026 (non-QP), Massachusetts locality.
- **Quantity limits:** CMS NCCI Medically Unlikely Edits (practitioner services).
- Status and gaps for each source are in [`data/manifest.json`](data/manifest.json) and [`data/README.md`](data/README.md).
  Codes with no published figure show "—".
- All bills in this repo are **fictional**.

## Privacy
Nothing is stored. Bills, lines, and letters live in the browser tab only. Request bodies and
uploaded content are never logged.

## License
MIT. See `LICENSE`.
