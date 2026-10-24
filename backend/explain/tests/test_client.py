"""Tests for the explain real client wiring (spec task 7). Covers E20.

The real `anthropic` package is never used here. A stand-in module is put in
sys.modules, so there is no network and no real key.
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from backend.explain import config
from backend.explain.client import make_explain_client
from backend.explain.handler import explain
from backend.extract import config as extract_config

from .factories import GOOD_TEXT, make_flag

FAKE_KEY = "fake-test-key-not-real"


def install_fake_anthropic(monkeypatch, reply_text: str = "{}"):
    seen: dict = {"init": None, "calls": []}

    class _Messages:
        def create(self, **kwargs):
            seen["calls"].append(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=reply_text)])

    class _Anthropic:
        def __init__(self, **kwargs):
            seen["init"] = kwargs
            self.messages = _Messages()

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=_Anthropic))
    return seen


def test_e20_model_name_unset_is_a_clear_error(monkeypatch):
    monkeypatch.setenv(extract_config.ENV_API_KEY, FAKE_KEY)
    monkeypatch.delenv(config.ENV_MODEL_ID, raising=False)
    with pytest.raises(extract_config.ConfigError, match="EXPLAIN_MODEL_ID"):
        make_explain_client()


def test_e20_api_key_unset_is_a_clear_error(monkeypatch):
    monkeypatch.setenv(config.ENV_MODEL_ID, "explain-model")
    monkeypatch.delenv(extract_config.ENV_API_KEY, raising=False)
    with pytest.raises(extract_config.ConfigError, match="ANTHROPIC_API_KEY"):
        make_explain_client()


def test_extract_model_variable_is_not_used_by_explain(monkeypatch):
    # Only EXTRACT_MODEL_ID is set: explain must still fail, not borrow it.
    monkeypatch.setenv(extract_config.ENV_API_KEY, FAKE_KEY)
    monkeypatch.setenv(extract_config.ENV_MODEL_ID, "extract-model")
    monkeypatch.delenv(config.ENV_MODEL_ID, raising=False)
    with pytest.raises(extract_config.ConfigError):
        make_explain_client()


def test_explain_client_uses_explain_model_name(monkeypatch):
    seen = install_fake_anthropic(monkeypatch)
    monkeypatch.setenv(extract_config.ENV_API_KEY, FAKE_KEY)
    monkeypatch.setenv(extract_config.ENV_MODEL_ID, "extract-model")
    monkeypatch.setenv(config.ENV_MODEL_ID, "explain-model")
    client = make_explain_client()
    client.invoke(system="s", content=[{"type": "text", "text": "x"}])
    assert seen["init"]["api_key"] == FAKE_KEY
    assert seen["calls"][0]["model"] == "explain-model"


def test_extract_default_still_uses_extract_variable(monkeypatch):
    from backend.extract.llm_client import make_client

    seen = install_fake_anthropic(monkeypatch)
    monkeypatch.setenv(extract_config.ENV_API_KEY, FAKE_KEY)
    monkeypatch.setenv(extract_config.ENV_MODEL_ID, "extract-model")
    monkeypatch.setenv(config.ENV_MODEL_ID, "explain-model")
    make_client().invoke(system="s", content=[{"type": "text", "text": "x"}])
    assert seen["calls"][0]["model"] == "extract-model"


def test_end_to_end_with_real_client_class_and_stand_in_sdk(monkeypatch):
    reply = json.dumps({"explanations": [{"key": "f0", "text": GOOD_TEXT}]})
    seen = install_fake_anthropic(monkeypatch, reply_text=reply)
    monkeypatch.setenv(extract_config.ENV_API_KEY, FAKE_KEY)
    monkeypatch.setenv(config.ENV_MODEL_ID, "explain-model")

    result = explain([make_flag()], client=make_explain_client())

    assert result.flags[0].explanation == GOOD_TEXT
    assert result.fallback_count == 0
    assert len(seen["calls"]) == 1                      # one batched call
    call = seen["calls"][0]
    assert call["model"] == "explain-model"
    assert call["max_tokens"] > 0
    assert "data" in call["system"].lower()
    assert len(call["messages"]) == 1 and call["messages"][0]["role"] == "user"
    blocks = call["messages"][0]["content"]
    assert len(blocks) == 1 and blocks[0]["type"] == "text"
    assert set(json.loads(blocks[0]["text"])["flags"][0]) == {"key", "flag_type", "reason", "basis"}
