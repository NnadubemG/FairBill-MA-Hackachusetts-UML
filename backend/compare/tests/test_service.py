"""Tests for the compare service + store. Covers C1-C9."""

from __future__ import annotations

from pathlib import Path

from backend.compare.framing import FRAMING_NOTE
from backend.compare.service import compare, list_procedures
from backend.compare.store import Store
from pipeline import jsonio

FIXTURES = Path(__file__).parent / "fixtures" / "processed"

BANNED = [
    "overcharged",
    "illegal",
    "fraud",
    "incorrect charge",
    "you should dispute",
    "you are owed",
]


def _store() -> Store:
    return Store.load(FIXTURES)


# C9: store loads all five files from disk
def test_c9_store_loads_from_disk():
    s = _store()
    assert set(s.procedures) == {"99213", "80053"}
    assert set(s.hospitals) == {"mgh", "bmc"}
    assert "99213" in s.prices_by_code
    assert "99213" in s.medicare_by_code
    assert "mgh" in s.chia_by_hospital


def test_c9_missing_file_tolerated(tmp_path):
    # Only procedures.json present; everything else empty -> still well formed.
    jsonio.write_json(tmp_path / "procedures.json",
                      [{"code": "99213", "code_system": "CPT",
                        "plain_label": "x", "category": None, "typical_max_units": None}])
    s = Store.load(tmp_path)
    out = compare(s, "99213")
    assert out["found"] is True
    assert out["hospitals"] == []
    assert out["medicare"] is None


# C5: framing note present on both endpoints and banned-word-free
def test_c5_framing_note_present_and_clean():
    s = _store()
    assert list_procedures(s)["framing_note"] == FRAMING_NOTE
    assert compare(s, "99213")["framing_note"] == FRAMING_NOTE
    low = FRAMING_NOTE.lower()
    for word in BANNED:
        assert word not in low


# list_procedures: stable code order
def test_list_procedures_order():
    procs = list_procedures(_store())["procedures"]
    assert [p["code"] for p in procs] == ["80053", "99213"]


# C1: known code, multiple hospitals, grouping + medicare + statewide
def test_c1_known_code():
    out = compare(_store(), "99213")
    assert out["found"] is True
    assert out["plain_label"] == "Office visit, established patient"

    by_id = {h["hospital_id"]: h for h in out["hospitals"]}
    assert set(by_id) == {"mgh", "bmc"}

    mgh = by_id["mgh"]
    assert mgh["name"] == "Massachusetts General Hospital"
    assert mgh["price_stats"]["commercial"]["median_rate"] == 150.0
    assert mgh["price_stats"]["cash"]["cash_price"] == 95.0
    assert mgh["chia_tier"]["tier"] == "high"

    assert out["medicare"]["medicare_price"] == 92.47
    # statewide over commercial medians 150 (mgh) and 170 (bmc)
    assert out["statewide"] == {"min": 150.0, "median": 160.0, "max": 170.0}
    # all 99213 price stats + medicare are 2025 (the 2024 record is for code 80053)
    assert out["data_years"] == [2025]


# C6: code present but no medicare entry
def test_c6_no_medicare():
    out = compare(_store(), "80053")
    assert out["found"] is True
    assert out["medicare"] is None
    # only bmc has 80053 (gross only)
    assert [h["hospital_id"] for h in out["hospitals"]] == ["bmc"]


# C2: unknown code -> well-formed not-found
def test_c2_unknown_code():
    out = compare(_store(), "00000")
    assert out["found"] is False
    assert out["hospitals"] == []
    assert out["medicare"] is None
    assert out["statewide"] == {"min": None, "median": None, "max": None}
    assert out["note"]
    assert out["framing_note"] == FRAMING_NOTE


# C3: partial data (gross only) -> populated gross, nulls elsewhere, missing_note set
def test_c3_partial_gross_only():
    bmc = {h["hospital_id"]: h for h in compare(_store(), "80053")["hospitals"]}["bmc"]
    assert bmc["price_stats"]["gross"]["gross_charge"] == 420.0
    assert "commercial" not in bmc["price_stats"]
    assert bmc["missing_note"] == "no commercial negotiated rates in the source files"


# C4: cash-only hospital excluded from statewide (which uses commercial medians)
def test_c4_cash_only_excluded_from_statewide():
    s = Store.from_dicts(
        procedures=[{"code": "99213", "code_system": "CPT", "plain_label": "x",
                     "category": None, "typical_max_units": None}],
        hospitals=[{"id": "h1", "name": "H1", "city": "X", "type": "community"}],
        prices=[{"hospital_id": "h1", "code": "99213", "code_system": "CPT",
                 "payer_group": "cash", "min_rate": None, "median_rate": None,
                 "max_rate": None, "cash_price": 50.0, "gross_charge": None,
                 "data_source": "s", "data_year": 2025}],
    )
    out = compare(s, "99213")
    assert out["statewide"] == {"min": None, "median": None, "max": None}
    h = out["hospitals"][0]
    assert h["price_stats"]["cash"]["cash_price"] == 50.0
    assert h["missing_note"] == "no commercial negotiated rates in the source files"


# C8: statewide aggregation across three commercial medians
def test_c8_statewide_three_hospitals():
    procs = [{"code": "99213", "code_system": "CPT", "plain_label": "x",
              "category": None, "typical_max_units": None}]
    hosp = [{"id": h, "name": h, "city": "X", "type": "community"}
            for h in ("a", "b", "c")]
    prices = [
        {"hospital_id": h, "code": "99213", "code_system": "CPT",
         "payer_group": "commercial", "min_rate": m, "median_rate": m, "max_rate": m,
         "cash_price": None, "gross_charge": None, "data_source": "s", "data_year": 2025}
        for h, m in (("a", 100.0), ("b", 200.0), ("c", 300.0))
    ]
    out = compare(Store.from_dicts(procedures=procs, hospitals=hosp, prices=prices), "99213")
    assert out["statewide"] == {"min": 100.0, "median": 200.0, "max": 300.0}


# C7: determinism -- same store, same request -> byte-identical serialization
def test_c7_determinism():
    s = _store()
    assert jsonio.dumps(compare(s, "99213")) == jsonio.dumps(compare(s, "99213"))
