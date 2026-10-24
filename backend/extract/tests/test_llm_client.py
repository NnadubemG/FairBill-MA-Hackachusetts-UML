"""Tests for the LLM client abstraction (spec task 2).

Covers T12 (model id from env var, clear error when unset) and the FakeLLMClient
scripting/fallback behavior that the rest of the suite relies on. All offline.
"""

from __future__ import annotations

import pytest

from backend.extract import config
from backend.extract.llm_client import (
    LLMClient,
    LLMError,
    FakeLLMClient,
    make_client,
)

SYS = "system instruction"
CONTENT = [{"type": "text", "text": "extract the line items"}]


def test_fake_client_satisfies_protocol():
    client = FakeLLMClient(default="{}")
    assert isinstance(client, LLMClient)


def test_fake_client_default_response():
    client = FakeLLMClient(default='{"line_items": []}')
    out = client.invoke(system=SYS, content=CONTENT)
    assert out == '{"line_items": []}'
    assert client.calls == 1


def test_fake_client_queue_is_fifo():
    client = FakeLLMClient(responses=["first", "second"])
    assert client.invoke(system=SYS, content=CONTENT) == "first"
    assert client.invoke(system=SYS, content=CONTENT) == "second"
    assert client.calls == 2


def test_fake_client_fingerprint_lookup():
    fp = FakeLLMClient.fingerprint(SYS, CONTENT, None)
    client = FakeLLMClient(by_fingerprint={fp: "matched"})
    assert client.invoke(system=SYS, content=CONTENT) == "matched"


def test_fake_client_fingerprint_is_deterministic():
    a = FakeLLMClient.fingerprint(SYS, CONTENT, None)
    b = FakeLLMClient.fingerprint(SYS, CONTENT, None)
    assert a == b
    # repair_hint changes the fingerprint
    c = FakeLLMClient.fingerprint(SYS, CONTENT, "fix it")
    assert c != a


def test_fake_client_raises_when_no_script():
    client = FakeLLMClient()  # nothing scripted
    with pytest.raises(LLMError):
        client.invoke(system=SYS, content=CONTENT)


def test_fake_client_raise_on_invoke():
    boom = RuntimeError("simulated model failure")
    client = FakeLLMClient(raise_on_invoke=boom)
    with pytest.raises(RuntimeError, match="simulated model failure"):
        client.invoke(system=SYS, content=CONTENT)


# --- Real client (Anthropic Messages API), tested with a fake `anthropic` module ---
# The real package is never imported here. We put a stand-in module in sys.modules so
# the lazy `import anthropic` inside the client finds it. No network, no API key.

import logging
import sys
from types import SimpleNamespace

FAKE_KEY = "fake-test-key-not-real"


def _install_fake_anthropic(monkeypatch, *, reply_blocks=None, raises=None):
    """Install a fake `anthropic` module. Returns a dict that records what was used."""
    seen: dict = {"init": None, "calls": []}

    class _Messages:
        def create(self, **kwargs):
            seen["calls"].append(kwargs)
            if raises is not None:
                raise raises
            return SimpleNamespace(content=reply_blocks or [])

    class _Anthropic:
        def __init__(self, **kwargs):
            seen["init"] = kwargs
            self.messages = _Messages()

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=_Anthropic))
    return seen


def _text(t):
    return SimpleNamespace(type="text", text=t)


def test_make_client_requires_model_name(monkeypatch):
    # T12: unset model name -> clear ConfigError, no hardcoded fallback.
    monkeypatch.setenv(config.ENV_API_KEY, FAKE_KEY)
    monkeypatch.delenv(config.ENV_MODEL_ID, raising=False)
    with pytest.raises(config.ConfigError, match=config.ENV_MODEL_ID):
        make_client()


def test_make_client_requires_api_key(monkeypatch):
    monkeypatch.setenv(config.ENV_MODEL_ID, "some-model-name")
    monkeypatch.delenv(config.ENV_API_KEY, raising=False)
    with pytest.raises(config.ConfigError, match=config.ENV_API_KEY):
        make_client()


def test_config_error_never_contains_key_value(monkeypatch):
    monkeypatch.setenv(config.ENV_API_KEY, "   ")  # blank counts as unset
    with pytest.raises(config.ConfigError) as err:
        config.get_api_key()
    assert FAKE_KEY not in str(err.value)


def test_make_client_reads_key_and_model_from_env(monkeypatch):
    seen = _install_fake_anthropic(monkeypatch)
    monkeypatch.setenv(config.ENV_API_KEY, FAKE_KEY)
    monkeypatch.setenv(config.ENV_MODEL_ID, "model-from-env")
    client = make_client()
    assert isinstance(client, LLMClient)
    assert seen["init"]["api_key"] == FAKE_KEY
    client.invoke(system=SYS, content=CONTENT)
    assert seen["calls"][0]["model"] == "model-from-env"


def test_request_uses_messages_api_format(monkeypatch):
    seen = _install_fake_anthropic(monkeypatch, reply_blocks=[_text('{"line_items": []}')])
    monkeypatch.setenv(config.ENV_API_KEY, FAKE_KEY)
    monkeypatch.setenv(config.ENV_MODEL_ID, "m")
    bill_block = {
        "type": "document",
        "source": {"type": "base64", "media_type": "application/pdf", "data": "QUJD"},
    }
    instruction = {"type": "text", "text": "extract the line items"}
    out = make_client().invoke(system=SYS, content=[bill_block, instruction])

    assert out == '{"line_items": []}'
    call = seen["calls"][0]
    assert call["system"] == SYS                       # system prompt is separate
    assert call["max_tokens"] > 0
    assert len(call["messages"]) == 1
    msg = call["messages"][0]
    assert msg["role"] == "user"
    # The bill stays in its own block; our instruction is a different block.
    assert msg["content"][0] == bill_block
    assert msg["content"][1] == instruction


def test_repair_hint_is_extra_text_block_in_same_turn(monkeypatch):
    seen = _install_fake_anthropic(monkeypatch, reply_blocks=[_text("{}")])
    monkeypatch.setenv(config.ENV_API_KEY, FAKE_KEY)
    monkeypatch.setenv(config.ENV_MODEL_ID, "m")
    make_client().invoke(system=SYS, content=CONTENT, repair_hint="missing billed_amount")
    messages = seen["calls"][0]["messages"]
    assert len(messages) == 1                           # still one user turn
    last = messages[0]["content"][-1]
    assert last["type"] == "text" and "missing billed_amount" in last["text"]
    assert messages[0]["content"][: len(CONTENT)] == CONTENT


def test_only_text_blocks_are_returned(monkeypatch):
    blocks = [_text("{"), SimpleNamespace(type="thinking", text="IGNORE"), _text("}")]
    _install_fake_anthropic(monkeypatch, reply_blocks=blocks)
    monkeypatch.setenv(config.ENV_API_KEY, FAKE_KEY)
    monkeypatch.setenv(config.ENV_MODEL_ID, "m")
    assert make_client().invoke(system=SYS, content=CONTENT) == "{}"


def test_api_error_becomes_llm_error_with_type_only(monkeypatch, caplog):
    secret = f"bill text JANE DOE 55512345 {FAKE_KEY}"
    _install_fake_anthropic(monkeypatch, raises=RuntimeError(secret))
    monkeypatch.setenv(config.ENV_API_KEY, FAKE_KEY)
    monkeypatch.setenv(config.ENV_MODEL_ID, "m")
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(LLMError) as err:
            make_client().invoke(system=SYS, content=CONTENT)
    text = str(err.value)
    assert "RuntimeError" in text                       # exception type is allowed
    assert "JANE DOE" not in text and FAKE_KEY not in text
    assert err.value.__cause__ is None                  # original not chained
    assert err.value.__suppress_context__ is True
    assert FAKE_KEY not in caplog.text and "JANE DOE" not in caplog.text


def test_missing_anthropic_package_fails_clearly(monkeypatch):
    # sys.modules[name] = None makes `import anthropic` raise ImportError.
    monkeypatch.setitem(sys.modules, "anthropic", None)
    monkeypatch.setenv(config.ENV_API_KEY, FAKE_KEY)
    monkeypatch.setenv(config.ENV_MODEL_ID, "m")
    with pytest.raises(ImportError):
        make_client()


# --- max_tokens option -----------------------------------------------------

def test_real_client_passes_max_tokens(monkeypatch):
    seen = _install_fake_anthropic(monkeypatch, reply_blocks=[_text("{}")])
    monkeypatch.setenv(config.ENV_API_KEY, FAKE_KEY)
    monkeypatch.setenv(config.ENV_MODEL_ID, "m")
    make_client().invoke(system=SYS, content=CONTENT, max_tokens=321)
    assert seen["calls"][0]["max_tokens"] == 321


@pytest.mark.parametrize("bad", [None, 0, -5])
def test_real_client_falls_back_to_default_max_tokens(monkeypatch, bad):
    from backend.extract import llm_client

    seen = _install_fake_anthropic(monkeypatch, reply_blocks=[_text("{}")])
    monkeypatch.setenv(config.ENV_API_KEY, FAKE_KEY)
    monkeypatch.setenv(config.ENV_MODEL_ID, "m")
    make_client().invoke(system=SYS, content=CONTENT, max_tokens=bad)
    assert seen["calls"][0]["max_tokens"] == llm_client.DEFAULT_MAX_TOKENS


def test_fake_client_records_requests():
    client = FakeLLMClient(default="{}")
    client.invoke(system=SYS, content=CONTENT, max_tokens=77)
    assert client.requests == [{"system": SYS, "content": CONTENT, "max_tokens": 77}]
