"""Integration tests for the prices stage. Covers U21-U24 and property P6."""

from __future__ import annotations

from pathlib import Path

from pipeline import jsonio
from pipeline.stages.hospitals import HospitalBinding
from pipeline.stages.prices import build_prices, build_prices_for_hospital

FIXTURES = Path(__file__).parent / "fixtures"
RAW_DIR = FIXTURES  # fixture file lives here, used as the "raw" dir
CURATED = {"99213", "80053"}
SOURCE = "Hospital MRF (test)"
YEAR = 2025

BINDING = HospitalBinding(
    hospital_id="h1",
    format_id="generic_csv",
    source_file="prices_hospital.csv",
)


def _stats(skip_log=None):
    return build_prices_for_hospital(
        BINDING, CURATED, SOURCE, YEAR, raw_dir=RAW_DIR, skip_log_path=skip_log
    )


def _by_key(stats):
    return {(s.code, s.payer_group): s for s in stats}


# U21 aggregation + grouping: two commercial negotiated rates -> one commercial PriceStat
def test_u21_commercial_aggregation(tmp_path):
    stats = _stats(tmp_path / "skip.log")
    by = _by_key(stats)
    commercial = by[("99213", "commercial")]
    assert commercial.min_rate == 100.0
    assert commercial.median_rate == 150.0
    assert commercial.max_rate == 200.0
    assert commercial.cash_price is None
    assert commercial.gross_charge is None


# U22 percentage skipped + logged: the 110% row is excluded and logged with no $ value
def test_u22_percentage_skipped_and_logged(tmp_path):
    log = tmp_path / "skip.log"
    stats = _stats(log)
    by = _by_key(stats)
    # the % rate did not inflate the commercial stats (still just 100 & 200)
    assert by[("99213", "commercial")].max_rate == 200.0

    content = log.read_text(encoding="utf-8")
    assert "99213" in content
    assert "percent" in content.lower()
    # no dollar figure written to the skip log
    import re
    assert not re.search(r"\$\s*\d", content)


# U23 all-missing -> null; gross only populates gross_charge
def test_u23_gross_only_and_blank_negotiated(tmp_path):
    stats = _stats(tmp_path / "skip.log")
    by = _by_key(stats)

    gross = by[("80053", "gross")]
    assert gross.gross_charge == 420.0
    assert gross.min_rate is None
    assert gross.median_rate is None
    assert gross.max_rate is None
    assert gross.cash_price is None

    # 80053 negotiated had only a blank rate -> no usable value -> no record
    assert ("80053", "commercial") not in by


# cash grouping check
def test_cash_group(tmp_path):
    by = _by_key(_stats(tmp_path / "skip.log"))
    cash = by[("99213", "cash")]
    assert cash.cash_price == 95.0
    assert cash.min_rate is None


# U24 provenance present on every record
def test_u24_provenance_on_every_record(tmp_path):
    stats = _stats(tmp_path / "skip.log")
    assert stats  # non-empty
    for s in stats:
        assert s.data_source == SOURCE
        assert s.data_year == YEAR


# P6 determinism: building twice yields byte-identical prices.json
def test_p6_determinism(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    build_prices([BINDING], CURATED, SOURCE, YEAR, out_path=a, raw_dir=RAW_DIR,
                 skip_log_path=tmp_path / "sa.log")
    build_prices([BINDING], CURATED, SOURCE, YEAR, out_path=b, raw_dir=RAW_DIR,
                 skip_log_path=tmp_path / "sb.log")
    assert a.read_bytes() == b.read_bytes()


# min <= median <= max holds on emitted negotiated records
def test_emitted_records_respect_ordering(tmp_path):
    for s in _stats(tmp_path / "skip.log"):
        if s.min_rate is not None:
            assert s.min_rate <= s.median_rate <= s.max_rate


def test_build_prices_sorted(tmp_path):
    out = tmp_path / "prices.json"
    build_prices([BINDING], CURATED, SOURCE, YEAR, out_path=out, raw_dir=RAW_DIR,
                 skip_log_path=tmp_path / "s.log")
    data = jsonio.read_json(out)
    keys = [(r["hospital_id"], r["code"], r["payer_group"]) for r in data]
    assert keys == sorted(keys)
