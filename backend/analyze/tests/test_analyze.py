"""Tests for the analyze handler. Covers A1-A8.

A1 is the important one: for every synthetic sample bill, the handler's flags must equal
the bill's ground-truth expected_flags when given that bill's own reference data.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

import pytest

from backend.analyze.handler import (
    AnalyzeError,
    analyze_bill,
    handle,
    validate_line_items,
)
from backend.analyze.store import ReferenceStore
from contracts.types import Flag
from pipeline import jsonio

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLES = sorted(glob.glob(str(REPO_ROOT / "synthetic" / "samples" / "*.json")))

BANNED = ["overcharged", "illegal", "fraud", "incorrect charge",
          "you should dispute", "you are owed"]


def _store_for(bill: dict) -> ReferenceStore:
    return ReferenceStore.from_dicts(
        price_references=bill.get("price_references", []),
        quantity_limits=bill.get("quantity_limits", []),
        bundle_pairs=bill.get("bundle_pairs", []),
    )


# A1: ground truth for every sample bill.
@pytest.mark.parametrize("path", SAMPLES, ids=[os.path.basename(p) for p in SAMPLES])
def test_a1_matches_expected_flags(path):
    bill = jsonio.read_json(path)
    store = _store_for(bill)
    result = analyze_bill(bill["line_items"], store)

    got = {(f.line_item_id, f.flag_type) for f in result.flags}
    expected = {(e["line_item_id"], e["flag_type"]) for e in bill["expected_flags"]}
    assert got == expected, f"{os.path.basename(path)}: flags {got} != expected {expected}"


def test_samples_discovered():
    # Guard: make sure we actually found sample bills (so A1 isn't vacuously passing).
    assert len(SAMPLES) >= 6


# A2: price_references cover exactly the bill's referenced codes, with provenance.
def test_a2_price_references_filtered():
    bill = jsonio.read_json(REPO_ROOT / "synthetic" / "samples" / "bill-duplicate-1.json")
    store = _store_for(bill)
    result = analyze_bill(bill["line_items"], store)

    bill_codes = {li["code"].upper() for li in bill["line_items"] if li.get("code")}
    ref_codes = {r.code.upper() for r in result.price_references}
    assert ref_codes <= bill_codes  # only codes on the bill
    # every reference carries provenance
    for r in result.price_references:
        assert r.data_source and r.data_year is not None


# A3: bad input -> clear error, never crash.
def test_a3_not_a_list():
    with pytest.raises(AnalyzeError):
        validate_line_items({"not": "a list"})


def test_a3_too_many():
    items = [{"id": str(i), "description": "x", "billed_amount": 1.0} for i in range(201)]
    with pytest.raises(AnalyzeError):
        validate_line_items(items)


def test_a3_overlong_string():
    items = [{"id": "1", "description": "x" * 5000, "billed_amount": 1.0}]
    with pytest.raises(AnalyzeError):
        validate_line_items(items)


def test_a3_non_finite_number():
    items = [{"id": "1", "description": "x", "billed_amount": float("inf")}]
    with pytest.raises(AnalyzeError):
        validate_line_items(items)


def test_a3_missing_billed_amount():
    items = [{"id": "1", "description": "x"}]
    with pytest.raises(AnalyzeError):
        validate_line_items(items)


def test_a3_duplicate_ids():
    items = [{"id": "1", "description": "a", "billed_amount": 1.0},
             {"id": "1", "description": "b", "billed_amount": 2.0}]
    with pytest.raises(AnalyzeError):
        validate_line_items(items)


# A4: explain success -> explanation carried.
def test_a4_explain_sets_explanation():
    bill = jsonio.read_json(REPO_ROOT / "synthetic" / "samples" / "bill-duplicate-1.json")
    store = _store_for(bill)

    from dataclasses import replace

    def explain(flags):
        return [replace(f, explanation="plain language") for f in flags]

    result = analyze_bill(bill["line_items"], store, explain=explain)
    assert result.flags  # the duplicate bill produces flags
    assert all(f.explanation == "plain language" for f in result.flags)


# A5: explain failure -> analysis still succeeds, explanation None.
def test_a5_explain_failure_is_safe():
    bill = jsonio.read_json(REPO_ROOT / "synthetic" / "samples" / "bill-duplicate-1.json")
    store = _store_for(bill)

    def boom(flags):
        raise RuntimeError("explain crashed")

    result = analyze_bill(bill["line_items"], store, explain=boom)
    assert result.flags
    assert all(f.explanation is None for f in result.flags)


def test_a5_explain_malformed_return_ignored():
    bill = jsonio.read_json(REPO_ROOT / "synthetic" / "samples" / "bill-duplicate-1.json")
    store = _store_for(bill)
    result = analyze_bill(bill["line_items"], store, explain=lambda flags: "nonsense")
    assert all(f.explanation is None for f in result.flags)


# A6: handle() shape.
def test_a6_handle_ok():
    bill = jsonio.read_json(REPO_ROOT / "synthetic" / "samples" / "bill-duplicate-1.json")
    store = _store_for(bill)
    resp = handle({"line_items": bill["line_items"]}, store)
    assert "error" not in resp
    assert "line_items" in resp and "flags" in resp and "price_references" in resp
    got = {(f["line_item_id"], f["flag_type"]) for f in resp["flags"]}
    expected = {(e["line_item_id"], e["flag_type"]) for e in bill["expected_flags"]}
    assert got == expected


def test_a6_handle_bad_input():
    resp = handle({"line_items": {"not": "a list"}}, ReferenceStore())
    assert "error" in resp
    assert "flags" not in resp


def test_a6_handle_not_a_dict():
    resp = handle("not a dict", ReferenceStore())
    assert "error" in resp


# A7: no banned words in any static message the module emits.
def test_a7_no_banned_words_in_errors():
    import backend.analyze.handler as mod
    import inspect

    src = inspect.getsource(mod).lower()
    for w in BANNED:
        assert w not in src


# A8: missing reference files -> empty store, analysis still runs.
def test_a8_empty_store_runs():
    items = [{"id": "1", "description": "Office visit", "billed_amount": 150.0,
              "code": "99213", "code_system": "CPT", "quantity": 1}]
    result = analyze_bill(items, ReferenceStore())  # no refs at all
    # With no reference data, no price/quantity/unbundling flags; coverage needs refs too.
    assert isinstance(result.flags, list)
    assert [li.id for li in result.line_items] == ["1"]
    assert result.price_references == []