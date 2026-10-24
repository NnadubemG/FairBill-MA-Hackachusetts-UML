"""Tests for the letter real-client wiring and privacy (spec task 8).

Covers L20 (model name and key), L23 (end to end with the real client class), and PR1
(nothing private in logs, output, warnings, or on disk).

The real `anthropic` package is never used. A stand-in module is put in sys.modules, so
there is no network and no real key.
"""

from __future__ import annotations

import json
import logging
import sys
from types import SimpleNamespace

import pytest

from backend.extract import config as extract_config
from backend.extract.llm_client import FakeLLMClient
from backend.letter import config, templates
from backend.letter.client import make_letter_client
from backend.letter.handler import WARN_STANDARD_WORDING, generate_letter
from backend.letter.models import CODING_REVIEW, PatientFields

from .factories import make_flag, make_line, make_patient, make_request

FAKE_KEY = "fake-test-key-not-real"
GOOD = (
    "I would like to understand the charge of $1,234.50 for code 99213. "
    "I am asking how this line was coded and billed. "
    "I would be grateful for a review so that I can understand it better."
)


def install_fake_anthropic(monkeypatch, *, reply_text: str = "{}", raises: Exception | None = None):
    seen: dict = {"init": None, "calls": []}

    class _Messages:
        def create(self, **kwargs):
            seen["calls"].append(kwargs)
            if raises is not None:
                raise raises
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=reply_text)])

    class _Anthropic:
        def __init__(self, **kwargs):
            seen["init"] = kwargs
            self.messages = _Messages()

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=_Anthropic))
    return seen


def set_env(monkeypatch, *, letter="letter-model", key=FAKE_KEY):
    if key is None:
        monkeypatch.delenv(extract_config.ENV_API_KEY, raising=False)
    else:
        monkeypatch.setenv(extract_config.ENV_API_KEY, key)
    if letter is None:
        monkeypatch.delenv(config.ENV_MODEL_ID, raising=False)
    else:
        monkeypatch.setenv(config.ENV_MODEL_ID, letter)


def request_with_private_data():
    flags = [make_flag("1", reason="SECRET-FLAG-REASON may be worth asking about. It is a note.",
                       basis="SECRET-FLAG-BASIS. Source: X, 2026.")]
    patient = make_patient(name="Pat Privatename", account_number="ACCT-9988776",
                           hospital="Hidden Valley Hospital", notes="PRIVATE-NOTE-TEXT about my health")
    return make_request(CODING_REVIEW, patient=patient, flags=flags,
                        lines=[make_line("1", description="PRIVATE-LINE-DESCRIPTION")])


PRIVATE_STRINGS = ["Pat Privatename", "ACCT-9988776", "Hidden Valley", "PRIVATE-NOTE-TEXT",
                   "SECRET-FLAG-REASON", "SECRET-FLAG-BASIS", "PRIVATE-LINE-DESCRIPTION"]


# --- L20: model name and key -----------------------------------------------

def test_l20_model_name_unset_is_a_clear_error(monkeypatch):
    set_env(monkeypatch, letter=None)
    with pytest.raises(extract_config.ConfigError, match="LETTER_MODEL_ID"):
        make_letter_client()


def test_l20_api_key_unset_is_a_clear_error(monkeypatch):
    set_env(monkeypatch, key=None)
    with pytest.raises(extract_config.ConfigError, match="ANTHROPIC_API_KEY"):
        make_letter_client()


def test_l20_other_model_variables_are_not_used(monkeypatch):
    set_env(monkeypatch, letter=None)
    monkeypatch.setenv("EXTRACT_MODEL_ID", "extract-model")
    monkeypatch.setenv("EXPLAIN_MODEL_ID", "explain-model")
    with pytest.raises(extract_config.ConfigError):
        make_letter_client()


def test_l20_letter_model_name_is_used(monkeypatch):
    seen = install_fake_anthropic(monkeypatch)
    set_env(monkeypatch, letter="my-letter-model")
    monkeypatch.setenv("EXTRACT_MODEL_ID", "extract-model")
    monkeypatch.setenv("EXPLAIN_MODEL_ID", "explain-model")
    make_letter_client().invoke(system="s", content=[{"type": "text", "text": "x"}])
    assert seen["init"]["api_key"] == FAKE_KEY
    assert seen["calls"][0]["model"] == "my-letter-model"


# --- L23: end to end with the real client class ----------------------------

def test_l23_end_to_end_with_the_real_client_class(monkeypatch):
    seen = install_fake_anthropic(monkeypatch, reply_text=json.dumps({"paragraph": GOOD}))
    set_env(monkeypatch)
    request = request_with_private_data()
    # Use a paragraph that fits this request's facts (code 99213, $1,234.50).
    result = generate_letter(request, client=make_letter_client())

    assert result.used_fallback is False and result.warnings == []
    assert GOOD in result.draft.body
    assert len(seen["calls"]) == 1                              # one call
    call = seen["calls"][0]
    assert call["model"] == "letter-model" and call["max_tokens"] == config.MAX_TOKENS
    assert "data" in call["system"].lower()
    assert len(call["messages"]) == 1 and call["messages"][0]["role"] == "user"
    blocks = call["messages"][0]["content"]
    assert len(blocks) == 1 and blocks[0]["type"] == "text"
    sent = json.dumps(call, ensure_ascii=False)
    for private in ("Pat Privatename", "ACCT-9988776", "Hidden Valley", "PRIVATE-NOTE-TEXT",
                    "PRIVATE-LINE-DESCRIPTION", "line_item_id"):
        assert private not in sent


# --- PR1: privacy ----------------------------------------------------------

def test_pr1_nothing_private_in_logs_or_output_on_success(caplog, capsys):
    request = request_with_private_data()
    client = FakeLLMClient(default=json.dumps({"paragraph": GOOD + " It is SECRET-FLAG-BASIS."}))
    with caplog.at_level(logging.DEBUG):
        result = generate_letter(request, client=client)
    out = capsys.readouterr()
    for sink in (caplog.text, out.out, out.err, " ".join(result.warnings)):
        for private in PRIVATE_STRINGS:
            assert private not in sink, private


def test_pr1_nothing_private_in_logs_or_warnings_on_failure(caplog, capsys):
    request = request_with_private_data()
    boom = RuntimeError("model failed for Pat Privatename ACCT-9988776 SECRET-FLAG-REASON")
    with caplog.at_level(logging.DEBUG):
        result = generate_letter(request, client=FakeLLMClient(raise_on_invoke=boom))
    out = capsys.readouterr()
    assert result.warnings == [WARN_STANDARD_WORDING]
    for sink in (caplog.text, out.out, out.err, " ".join(result.warnings)):
        for private in PRIVATE_STRINGS:
            assert private not in sink, private


def test_pr1_real_client_error_carries_only_the_exception_type(monkeypatch, caplog, capsys):
    secret = "Pat Privatename ACCT-9988776 " + FAKE_KEY
    install_fake_anthropic(monkeypatch, raises=RuntimeError(secret))
    set_env(monkeypatch)
    with caplog.at_level(logging.DEBUG):
        result = generate_letter(request_with_private_data(), client=make_letter_client())
    out = capsys.readouterr()
    assert result.used_fallback is True and result.warnings == [WARN_STANDARD_WORDING]
    for sink in (caplog.text, out.out, out.err, " ".join(result.warnings)):
        assert FAKE_KEY not in sink and "ACCT-9988776" not in sink and "Pat Privatename" not in sink


def test_pr1_api_key_never_appears_in_the_result(monkeypatch):
    install_fake_anthropic(monkeypatch, reply_text=json.dumps({"paragraph": GOOD}))
    set_env(monkeypatch)
    result = generate_letter(request_with_private_data(), client=make_letter_client())
    assert FAKE_KEY not in repr(result)


def test_pr1_no_files_are_written(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    generate_letter(request_with_private_data(), client=FakeLLMClient(default=json.dumps({"paragraph": GOOD})))
    generate_letter(request_with_private_data(), client=FakeLLMClient(raise_on_invoke=RuntimeError("x")))
    generate_letter(make_request("itemized_bill", patient=PatientFields()), client=FakeLLMClient(default="{}"))
    assert list(tmp_path.iterdir()) == []


def test_pr1_warnings_are_fixed_strings():
    request = request_with_private_data()
    result = generate_letter(request, client=FakeLLMClient(raise_on_invoke=RuntimeError("x")))
    assert result.warnings == [WARN_STANDARD_WORDING]
    assert templates.TOP_LINE not in WARN_STANDARD_WORDING
