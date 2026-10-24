"""End-to-end extraction tests with fixtures (spec task 9).

Confirms the full offline flow (fake client -> ExtractionResult) on scripted bills,
and property P4 (metadata.total is always a number or None, never a string).
"""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.extract.llm_client import FakeLLMClient
from backend.extract.handler import extract
from backend.extract.tests import fixtures

PNG = (b"\x89PNG fake", "image/png")


def _procs(tmp_path, codes):
    p = tmp_path / "procedures.json"
    p.write_text(json.dumps([{"code": c, "plain_label": "x"} for c in codes]))
    return p


def test_clean_bill_fixture(tmp_path):
    client = FakeLLMClient(default=fixtures.CLEAN_BILL)
    result = extract(*PNG, client=client, procedures_path=_procs(tmp_path, ["99213", "85025"]))
    assert len(result.line_items) == 2
    assert result.metadata.hospital_name == "Riverside General"
    assert result.metadata.total == 192.0
    assert all(not c.needs_confirmation for c in result.line_confidence)
    assert result.warnings == []


def test_no_codes_fixture_all_confirm(tmp_path):
    client = FakeLLMClient(default=fixtures.NO_CODES_BILL)
    result = extract(*PNG, client=client, procedures_path=_procs(tmp_path, ["99213"]))
    assert len(result.line_items) == 2
    assert all(li.code is None for li in result.line_items)
    assert all(c.needs_confirmation for c in result.line_confidence)
    assert all(c.confidence == "low" for c in result.line_confidence)


def test_blank_bill_fixture(tmp_path):
    client = FakeLLMClient(default=fixtures.BLANK_BILL)
    result = extract(*PNG, client=client, procedures_path=_procs(tmp_path, []))
    assert result.line_items == []
    assert result.warnings  # has the no-lines warning


def test_invalid_then_clean_retry(tmp_path):
    client = FakeLLMClient(responses=[fixtures.INVALID_FIRST, fixtures.CLEAN_BILL])
    result = extract(*PNG, client=client, procedures_path=_procs(tmp_path, ["99213", "85025"]))
    assert client.calls == 2
    assert len(result.line_items) == 2


# --- Property P4: total is a number or None --------------------------------

_money_like = st.one_of(
    st.none(),
    st.integers(min_value=-10_000, max_value=1_000_000),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e4, max_value=1e6),
    st.sampled_from(["$1,234.50", "", "N/A", "0.00", "(50.00)", "abc"]),
)


@settings(max_examples=100)
@given(_money_like)
def test_p4_metadata_total_is_number_or_none(total_value):
    raw = fixtures.envelope(
        [],
        metadata={"hospital_name": None, "statement_date": None, "total": total_value},
    )
    client = FakeLLMClient(default=raw)
    result = extract(*PNG, client=client)
    total = result.metadata.total
    assert total is None or isinstance(total, float)
    assert not isinstance(total, str)


@settings(max_examples=50)
@given(st.one_of(st.none(), st.text(max_size=12)))
def test_p4_statement_date_is_iso_or_none(date_value):
    raw = fixtures.envelope(
        [],
        metadata={"hospital_name": None, "statement_date": date_value, "total": None},
    )
    client = FakeLLMClient(default=raw)
    result = extract(*PNG, client=client)
    d = result.metadata.statement_date
    assert d is None or (isinstance(d, str) and len(d) == 10 and d[4] == "-" and d[7] == "-")
