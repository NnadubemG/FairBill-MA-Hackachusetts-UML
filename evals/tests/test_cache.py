"""Tests for the disk cache (spec task 2). Covers C1 to C13 and properties PE6, PE7."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.extract.handler import WARN_EXTRACTION_UNAVAILABLE, extract
from backend.extract.llm_client import FakeLLMClient, LLMClient, LLMError
from evals.cache import (
    BudgetExceeded,
    CacheMiss,
    CachingClient,
    cache_key,
    request_hash,
    sha256_bytes,
)

SYS = "system text"
CONTENT = [{"type": "text", "text": "hello"}]
SHA = sha256_bytes(b"bill file bytes")
TASKS = ("extract", "explain", "letter")


def make(cache_dir: Path, inner: LLMClient | None = None, *, model="model-a", **kw) -> CachingClient:
    return CachingClient(
        {t: inner for t in TASKS}, {t: model for t in TASKS}, cache_dir, **kw
    )


def call(client: CachingClient, task="extract", sha=SHA, **kw):
    kw.setdefault("system", SYS)
    kw.setdefault("content", CONTENT)
    return client.scoped(task, sha).invoke(**kw)


def entry_files(cache_dir: Path) -> list[Path]:
    return sorted(p for p in cache_dir.glob("*.json"))


# --- C1: miss then hit -----------------------------------------------------

def test_c1_second_identical_call_does_not_reach_the_model(tmp_path):
    inner = FakeLLMClient(default='{"x": 1}')
    c = make(tmp_path / "c", inner)
    assert call(c) == '{"x": 1}'
    assert call(c) == '{"x": 1}'
    assert inner.calls == 1
    assert (c.stats.misses, c.stats.hits, c.stats.real_calls) == (1, 1, 1)


def test_c1_a_second_client_reads_what_the_first_wrote(tmp_path):
    inner = FakeLLMClient(default="reply one")
    call(make(tmp_path / "c", inner))
    other = FakeLLMClient(default="different")
    c2 = make(tmp_path / "c", other)
    assert call(c2) == "reply one" and other.calls == 0


# --- C2 / C3 / C4: the key -------------------------------------------------

def test_c2_different_model_is_a_miss(tmp_path):
    inner = FakeLLMClient(responses=["from a", "from b"])
    assert call(make(tmp_path / "c", inner, model="model-a")) == "from a"
    assert call(make(tmp_path / "c", inner, model="model-b")) == "from b"
    assert inner.calls == 2


@pytest.mark.parametrize(
    "change",
    [
        {"task": "explain"},
        {"sha": sha256_bytes(b"another file")},
        {"system": "other system"},
        {"content": [{"type": "text", "text": "other"}]},
        {"repair_hint": "fix it"},
        {"max_tokens": 123},
    ],
)
def test_c3_changing_any_part_is_a_miss(tmp_path, change):
    inner = FakeLLMClient(default="reply")
    c = make(tmp_path / "c", inner)
    call(c)
    call(c, **change)
    assert inner.calls == 2


def test_c3_key_function_changes_with_each_part():
    base = ("extract", "m", SHA, request_hash(SYS, CONTENT, None, None))
    keys = {
        cache_key(*base),
        cache_key("explain", *base[1:]),
        cache_key(base[0], "m2", *base[2:]),
        cache_key(*base[:2], "f" * 64, base[3]),
        cache_key(*base[:3], request_hash("s2", CONTENT, None, None)),
        cache_key(*base[:3], request_hash(SYS, CONTENT, "hint", None)),
        cache_key(*base[:3], request_hash(SYS, CONTENT, None, 5)),
    }
    assert len(keys) == 7


def test_c4_key_ignores_dict_order():
    a = [{"type": "text", "text": "x", "extra": 1}]
    b = [{"extra": 1, "text": "x", "type": "text"}]
    assert request_hash(SYS, a) == request_hash(SYS, b)


def test_a_prompt_text_edit_invalidates_the_cache(tmp_path):
    inner = FakeLLMClient(responses=["old prompt reply", "new prompt reply"])
    c = make(tmp_path / "c", inner)
    assert call(c, system="prompt v1") == "old prompt reply"
    assert call(c, system="prompt v2") == "new prompt reply"


# --- C5 / C6: files --------------------------------------------------------

def test_c5_entry_file_holds_only_the_four_fields(tmp_path):
    d = tmp_path / "c"
    call(make(d, FakeLLMClient(default="the reply")), task="letter")
    files = entry_files(d)
    assert len(files) == 1
    entry = json.loads(files[0].read_text())
    assert entry == {"task": "letter", "model": "model-a", "file_sha256": SHA, "reply": "the reply"}
    assert files[0].name == cache_key("letter", "model-a", SHA, request_hash(SYS, CONTENT)) + ".json"
    assert [p.name for p in d.iterdir() if p.name.startswith(".") and p.name != ".gitignore"] == []


def test_c6_cache_folder_ignores_itself_in_git(tmp_path):
    d = tmp_path / "c"
    call(make(d, FakeLLMClient(default="r")))
    assert (d / ".gitignore").read_text() == "*\n"


# --- C7: damaged files -----------------------------------------------------

def _key(task="extract", model="model-a"):
    return cache_key(task, model, SHA, request_hash(SYS, CONTENT))


@pytest.mark.parametrize(
    "bad",
    [
        "not json",
        "",
        "[]",
        '"text"',
        "null",
        '{"task": "extract"}',
        json.dumps({"task": "extract", "model": "model-a", "file_sha256": SHA, "reply": 5}),
        json.dumps({"task": "extract", "model": "model-a", "file_sha256": SHA, "reply": ""}),
        json.dumps({"task": "extract", "model": "model-a", "file_sha256": SHA, "reply": "  "}),
        json.dumps({"task": "extract", "model": "model-a", "file_sha256": SHA, "reply": "ok", "extra": 1}),
        json.dumps({"task": "letter", "model": "model-a", "file_sha256": SHA, "reply": "wrong task"}),
        json.dumps({"task": "extract", "model": "other", "file_sha256": SHA, "reply": "wrong model"}),
        json.dumps({"task": "extract", "model": "model-a", "file_sha256": "0" * 64, "reply": "wrong file"}),
    ],
)
def test_c7_damaged_entry_is_a_miss_and_is_replaced(tmp_path, bad):
    d = tmp_path / "c"
    d.mkdir()
    (d / f"{_key()}.json").write_text(bad)
    inner = FakeLLMClient(default="fresh reply")
    assert call(make(d, inner)) == "fresh reply"
    assert inner.calls == 1
    assert json.loads((d / f"{_key()}.json").read_text())["reply"] == "fresh reply"


def test_c7_binary_garbage_in_an_entry_is_a_miss(tmp_path):
    d = tmp_path / "c"
    d.mkdir()
    (d / f"{_key()}.json").write_bytes(b"\xff\xfe\x00garbage")
    assert call(make(d, FakeLLMClient(default="ok"))) == "ok"


# --- C8 / C9: what is not cached -------------------------------------------

def test_c8_a_failed_call_is_not_cached_and_the_error_passes_through(tmp_path):
    d = tmp_path / "c"
    c = make(d, FakeLLMClient(raise_on_invoke=RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        call(c)
    assert entry_files(d) == [] and c.stats.failures == 1
    inner2 = FakeLLMClient(default="works now")
    assert call(make(d, inner2)) == "works now" and inner2.calls == 1


@pytest.mark.parametrize("reply", ["", "   \n", None, 5, ["x"]])
def test_c9_empty_or_non_text_replies_are_not_cached(tmp_path, reply):
    class _Inner:
        calls = 0

        def invoke(self, *, system, content, repair_hint=None, max_tokens=None):
            _Inner.calls += 1
            return reply

    d = tmp_path / "c"
    c = make(d, _Inner())
    assert call(c) == reply
    assert call(c) == reply
    assert _Inner.calls == 2 and entry_files(d) == []


# --- C10: cache-only -------------------------------------------------------

def test_c10_cache_only_miss_raises_and_never_calls_the_model(tmp_path):
    inner = FakeLLMClient(default="x")
    c = make(tmp_path / "c", inner, cache_only=True)
    with pytest.raises(CacheMiss):
        call(c)
    assert inner.calls == 0 and c.stats.cache_only_misses == 1 and c.stats.real_calls == 0


def test_c10_cache_only_still_serves_hits_and_needs_no_client(tmp_path):
    d = tmp_path / "c"
    call(make(d, FakeLLMClient(default="stored")))
    c = make(d, None, cache_only=True)
    assert call(c) == "stored"
    assert c.stats.hits == 1


def test_c10_miss_and_budget_errors_are_llm_errors_so_features_fall_back():
    assert issubclass(CacheMiss, LLMError) and issubclass(BudgetExceeded, LLMError)


def test_missing_client_for_a_task_acts_like_a_miss(tmp_path):
    c = CachingClient({"extract": None}, {"extract": "m"}, tmp_path / "c")
    with pytest.raises(CacheMiss):
        call(c)


# --- C11: budget -----------------------------------------------------------

def test_c11_budget_stops_real_calls_but_not_hits(tmp_path):
    inner = FakeLLMClient(default="r")
    c = make(tmp_path / "c", inner, max_calls=2)
    call(c, system="a")
    call(c, system="b")
    with pytest.raises(BudgetExceeded):
        call(c, system="c")
    assert c.stats.budget_hit is True and c.stats.real_calls == 2 and inner.calls == 2
    assert call(c, system="a") == "r"                    # a hit still works
    assert c.stats.hits == 1 and inner.calls == 2


def test_c11_a_failed_call_still_uses_budget(tmp_path):
    c = make(tmp_path / "c", FakeLLMClient(raise_on_invoke=RuntimeError("x")), max_calls=1)
    with pytest.raises(RuntimeError):
        call(c, system="a")
    with pytest.raises(BudgetExceeded):
        call(c, system="b")


def test_c11_zero_budget_blocks_every_real_call(tmp_path):
    inner = FakeLLMClient(default="r")
    with pytest.raises(BudgetExceeded):
        call(make(tmp_path / "c", inner, max_calls=0))
    assert inner.calls == 0


# --- C12: no key in cache files --------------------------------------------

def test_c12_the_api_key_never_reaches_a_cache_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-test-key-not-real")
    d = tmp_path / "c"
    c = make(d, FakeLLMClient(default="a reply"))
    call(c)
    call(c, task="explain")
    for p in d.iterdir():
        assert "fake-test-key-not-real" not in p.read_text()


# --- C13: replay -----------------------------------------------------------

ENVELOPE = json.dumps({
    "line_items": [{"id": "1", "description": "Visit", "billed_amount": 150, "code": "99213",
                    "code_system": "CPT"}],
    "metadata": {"hospital_name": "H", "statement_date": "03/04/2026", "total": 150},
    "confidence_hints": {"1": "high"},
})


def test_c13_cached_reply_gives_the_same_extraction_result(tmp_path):
    d = tmp_path / "c"
    live = extract(b"%PDF fake", "application/pdf", client=make(d, FakeLLMClient(default=ENVELOPE)).scoped("extract", SHA))
    replay_client = make(d, None, cache_only=True)
    replay = extract(b"%PDF fake", "application/pdf", client=replay_client.scoped("extract", SHA))
    assert replay == live and replay_client.stats.hits == 1 and replay_client.stats.misses == 0


def test_a_cache_only_miss_makes_extract_use_its_fallback(tmp_path):
    c = make(tmp_path / "c", None, cache_only=True)
    result = extract(b"%PDF fake", "application/pdf", client=c.scoped("extract", SHA))
    assert result.line_items == [] and result.warnings == [WARN_EXTRACTION_UNAVAILABLE]


def test_a_budget_stop_makes_extract_use_its_fallback(tmp_path):
    c = make(tmp_path / "c", FakeLLMClient(default=ENVELOPE), max_calls=0)
    result = extract(b"%PDF fake", "application/pdf", client=c.scoped("extract", SHA))
    assert result.warnings == [WARN_EXTRACTION_UNAVAILABLE] and c.stats.budget_hit


def test_the_tasks_do_not_share_cache_entries(tmp_path):
    inner = FakeLLMClient(responses=["for extract", "for letter"])
    c = make(tmp_path / "c", inner)
    assert call(c, task="extract") == "for extract"
    assert call(c, task="letter") == "for letter"


def test_no_files_are_written_outside_the_cache_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    call(make(tmp_path / "c", FakeLLMClient(default="r")))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["c"]


# --- Properties ------------------------------------------------------------

_text = st.text(max_size=20)


@settings(max_examples=200)
@given(_text, _text, _text, _text, st.one_of(st.none(), _text), st.one_of(st.none(), st.integers(0, 5000)))
def test_pe6_key_is_deterministic_and_changes_with_every_part(task, model, sha, system, hint, tokens):
    content = [{"type": "text", "text": system}]
    k1 = cache_key(task, model, sha, request_hash(system, content, hint, tokens))
    k2 = cache_key(task, model, sha, request_hash(system, content, hint, tokens))
    assert k1 == k2 and len(k1) == 64
    assert k1 != cache_key(task + "x", model, sha, request_hash(system, content, hint, tokens))
    assert k1 != cache_key(task, model + "x", sha, request_hash(system, content, hint, tokens))
    assert k1 != cache_key(task, model, sha + "x", request_hash(system, content, hint, tokens))
    assert k1 != cache_key(task, model, sha, request_hash(system + "x", content, hint, tokens))
    assert k1 != cache_key(task, model, sha, request_hash(system, content, (hint or "") + "x", tokens))
    assert k1 != cache_key(task, model, sha, request_hash(system, content, hint, (tokens or 0) + 1))


@settings(max_examples=100)
@given(st.text(min_size=1, max_size=200).filter(lambda s: s.strip()))
def test_pe7_whatever_is_stored_comes_back_unchanged(reply):
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "c"
        assert call(make(d, FakeLLMClient(default=reply))) == reply
        replay = make(d, None, cache_only=True)
        assert call(replay) == reply
        assert replay.stats.hits == 1


def test_cache_dir_is_created_on_demand(tmp_path):
    d = tmp_path / "does" / "not" / "exist"
    assert not d.exists()
    call(make(d, FakeLLMClient(default="r")))
    assert d.is_dir()
    assert os.path.isfile(d / ".gitignore")
