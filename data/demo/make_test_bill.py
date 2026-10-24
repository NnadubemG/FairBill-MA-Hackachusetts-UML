"""Generate a fictional test bill that exercises FairBill against the REAL processed data.

    python data/demo/make_test_bill.py

Writes, next to this script:
  test-bill-er-visit.json  -> loaded by the app's sample picker (one click, no typing)
  test-bill-er-visit.pdf   -> to try the upload step (needs an AI key to be read)
  test-bill-er-visit.txt   -> same bill as plain text

Amounts are chosen against data/processed/reference.json (MA gross ranges from the Lahey
and BIDMC price files) so each line has a known expected outcome. The hospital, patient,
and account are fictional.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from contracts.types import LineItem  # noqa: E402
from synthetic.render import render_pdf, render_text  # noqa: E402

DOS = "2026-09-14"

# (id, code, system, description as printed, plain description, qty, amount, expected)
LINES = [
    ("1", "99284", "CPT", "ER VISIT LEVEL 4", "Emergency room visit, higher level", 1, 2950.00,
     "Above the MA range ($1,862-$1,922): price_outside_ma_range"),
    ("2", "74177", "CPT", "CT ABD/PELVIS W CONTRAST", "CT scan of the abdomen and pelvis", 1, 5400.00,
     "Above the MA range ($1,991-$3,721): price_outside_ma_range"),
    ("3", "80053", "CPT", "COMPREHENSIVE METABOLIC PNL", "Basic metabolic and chemistry blood panel", 1, 240.00,
     "Inside the MA range ($127-$658): no flag"),
    ("4", "85025", "CPT", "CBC W/AUTO DIFF", "Complete blood count lab test", 1, 68.00,
     "Same code, date and amount as line 5: duplicate_line_item"),
    ("5", "85025", "CPT", "CBC W/AUTO DIFF", "Complete blood count lab test", 1, 68.00,
     "Same code, date and amount as line 4: duplicate_line_item"),
    ("6", "71046", "CPT", "XR CHEST 2 VIEWS", "Chest X-ray", 1, 280.00,
     "Inside the MA range ($206-$325): no flag"),
    ("7", "93000", "CPT", "ECG 12 LEAD W/INTERP", "Heart rhythm tracing (ECG)", 1, 410.00,
     "Inside the MA range ($204-$593): no flag"),
    ("8", "J7030", "HCPCS", "NS 0.9% 1000ML INFUSION", "Saline IV fluid, 1000 mL", 1, 95.00,
     "Not in our reference data: no_reference_found"),
]

META = {
    "hospital_name": "Riverbend Community Hospital (FICTIONAL)",
    "statement_date": "2026-10-01",
}


def main() -> None:
    items = [
        LineItem(id=i, code=c, code_system=s, raw_description=raw, description=desc,
                 quantity=q, unit="each", billed_amount=amt, date_of_service=DOS)
        for i, c, s, raw, desc, q, amt, _ in LINES
    ]
    total = round(sum(it.billed_amount for it in items), 2)

    sample = {
        "id": "test-er-visit",
        "label": "Test bill: ER visit priced against real MA data",
        "scenario": "real_data_test",
        "metadata": {**META, "total": total},
        "line_items": [
            {k: v for k, v in vars(it).items()} for it in items
        ],
        "expected": {i: exp for i, *_rest, exp in LINES},
    }
    (HERE / "test-bill-er-visit.json").write_text(json.dumps(sample, indent=2) + "\n", encoding="utf-8")

    bill = SimpleNamespace(
        bill_id="TEST-1",
        bill_metadata=SimpleNamespace(total_billed=total, **META),
        line_items=items,
    )
    (HERE / "test-bill-er-visit.pdf").write_bytes(render_pdf(bill))
    (HERE / "test-bill-er-visit.txt").write_text(render_text(bill), encoding="utf-8")
    print(f"wrote test bill: {len(items)} lines, total ${total:,.2f}")


if __name__ == "__main__":
    main()
