"""Tests for the eval config and corpus (spec task 1). Covers S1 to S4."""

from __future__ import annotations

import hashlib
import os

import pytest

from synthetic import SCENARIOS, STYLES

from evals import config
from evals.corpus import PrivatePathError, build_corpus, ensure_not_private


# --- S1: default corpus ----------------------------------------------------

def test_s1_default_corpus_is_every_scenario_in_every_style():
    bills = build_corpus()
    expected = len(SCENARIOS) * len(STYLES)        # computed, so a new scenario cannot break this
    assert len(bills) == expected
    assert len({b.key for b in bills}) == expected
    assert {b.scenario for b in bills} == set(SCENARIOS)
    assert {b.style for b in bills} == set(STYLES)
    for b in bills:
        assert b.truth.bill_id == b.bill_id and b.truth.scenario == b.scenario
        assert b.truth.line_items, b.key


def test_s1_same_arguments_same_bills():
    a, b = build_corpus(), build_corpus()
    assert [(x.key, x.pdf, x.file_sha256) for x in a] == [(x.key, x.pdf, x.file_sha256) for x in b]


def test_s1_sorted_by_bill_id_then_style():
    bills = build_corpus()
    assert [(b.bill_id, b.style) for b in bills] == sorted((b.bill_id, b.style) for b in bills)


def test_s1_layouts_differ_for_the_same_bill():
    mixed = [b for b in build_corpus(scenarios=["mixed"])]
    assert len(mixed) == 2 and mixed[0].pdf != mixed[1].pdf
    assert mixed[0].file_sha256 != mixed[1].file_sha256


# --- S2: PDFs --------------------------------------------------------------

def test_s2_pdf_bytes_and_hash():
    for b in build_corpus():
        assert b.pdf.startswith(b"%PDF-")
        assert b.file_sha256 == hashlib.sha256(b.pdf).hexdigest()


# --- S3: choosing bills ----------------------------------------------------

def test_s3_choose_scenarios_seeds_styles():
    bills = build_corpus(scenarios=["clean", "mixed"], seeds=[1, 2], styles=["plain"])
    assert [b.key for b in bills] == ["clean-1/plain", "clean-2/plain", "mixed-1/plain", "mixed-2/plain"]
    assert bills[0].truth.seed == 1 and bills[1].truth.seed == 2


def test_s3_repeats_are_dropped():
    bills = build_corpus(scenarios=["clean", "clean"], seeds=[1, 1], styles=["plain", "plain"])
    assert len(bills) == 1


@pytest.mark.parametrize(
    "kwargs,words",
    [
        ({"scenarios": ["nope"]}, ("unknown scenario", "nope", "clean")),
        ({"styles": ["fancy"]}, ("unknown style", "fancy", "plain")),
        ({"scenarios": []}, ("no scenario",)),
        ({"styles": []}, ("no style",)),
        ({"seeds": []}, ("no seeds",)),
        ({"seeds": ["1"]}, ("whole numbers",)),
        ({"seeds": [True]}, ("whole numbers",)),
    ],
)
def test_s3_bad_choices_give_a_clear_error(kwargs, words):
    with pytest.raises(ValueError) as err:
        build_corpus(**kwargs)
    for w in words:
        assert w in str(err.value)


def test_corpus_writes_no_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    build_corpus(scenarios=["clean"])
    assert list(tmp_path.iterdir()) == []


# --- S4: the /private guard ------------------------------------------------

@pytest.mark.parametrize(
    "bad",
    [
        config.PRIVATE_DIR,
        config.PRIVATE_DIR / "bill.pdf",
        config.PRIVATE_DIR / "deep" / "er" / "x.md",
        config.PRIVATE_DIR / ".." / "private" / "x.md",
        config.REPO_ROOT / "evals" / ".." / "private" / "x.md",
        str(config.PRIVATE_DIR / "x").upper(),                  # case-insensitive file systems
        str(config.PRIVATE_DIR).replace("private", "Private") + "/x",
    ],
)
def test_s4_private_paths_are_refused(bad):
    with pytest.raises(PrivatePathError):
        ensure_not_private(bad)


@pytest.mark.parametrize(
    "good",
    [
        config.DEFAULT_REPORT_PATH,
        config.DEFAULT_CACHE_DIR,
        config.REPO_ROOT / "docs" / "eval-results.md",
        config.REPO_ROOT / "private_notes" / "x.md",           # same prefix, different folder
        config.REPO_ROOT / "privatefile.md",
    ],
)
def test_s4_other_paths_are_allowed(good, tmp_path):
    assert ensure_not_private(good).name == os.path.basename(str(good))
    assert ensure_not_private(tmp_path / "x.md").name == "x.md"


def test_s4_private_error_message_has_no_path():
    with pytest.raises(PrivatePathError) as err:
        ensure_not_private(config.PRIVATE_DIR / "secret-name.pdf")
    assert "secret-name" not in str(err.value)


# --- config ----------------------------------------------------------------

def test_default_paths_are_inside_evals():
    for p in (config.DEFAULT_CACHE_DIR, config.DEFAULT_REPORT_PATH):
        assert config.EVALS_DIR in p.parents


def test_threshold_metrics_are_unique_and_ops_valid():
    metrics = [t.metric for t in config.THRESHOLDS]
    assert len(metrics) == len(set(metrics))
    assert all(t.op in {">=", "<=", "=="} for t in config.THRESHOLDS)
    assert any(t.hard for t in config.THRESHOLDS)


def test_default_budget_is_sixty_and_fits_one_full_run():
    assert config.DEFAULT_MAX_CALLS == 60
    assert len(build_corpus()) * 3 <= config.DEFAULT_MAX_CALLS     # extract + explain + letter


@pytest.mark.parametrize(
    "op,value,limit,expected",
    [(">=", 0.95, 0.95, True), (">=", 0.94, 0.95, False), ("<=", 0.25, 0.25, True),
     ("<=", 0.26, 0.25, False), ("==", 0, 0, True), ("==", 1, 0, False),
     (">=", None, 0.95, None), ("==", None, 0, None)],
)
def test_passes(op, value, limit, expected):
    assert config.passes(op, value, limit) is expected


def test_passes_rejects_unknown_operator():
    with pytest.raises(ValueError):
        config.passes("!=", 1, 0)


def test_model_variable_names():
    assert (config.ENV_API_KEY, config.ENV_EXTRACT_MODEL, config.ENV_EXPLAIN_MODEL,
            config.ENV_LETTER_MODEL) == ("ANTHROPIC_API_KEY", "EXTRACT_MODEL_ID",
                                         "EXPLAIN_MODEL_ID", "LETTER_MODEL_ID")
