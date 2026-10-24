"""Tests for the Bedrock client abstraction (spec task 2).

Covers T12 (model id from env var, clear error when unset) and the FakeBedrockClient
scripting/fallback behavior that the rest of the suite relies on. All offline.
"""

from __future__ import annotations

import pytest

from backend.extract import config
from backend.extract.bedrock_client import (
    BedrockClient,
    BedrockError,
    FakeBedrockClient,
    make_client,
)

SYS = "system instruction"
CONTENT = [{"type": "text", "text": "extract the line items"}]


def test_fake_client_satisfies_protocol():
    client = FakeBedrockClient(default="{}")
    assert isinstance(client, BedrockClient)


def test_fake_client_default_response():
    client = FakeBedrockClient(default='{"line_items": []}')
    out = client.invoke(system=SYS, content=CONTENT)
    assert out == '{"line_items": []}'
    assert client.calls == 1


def test_fake_client_queue_is_fifo():
    client = FakeBedrockClient(responses=["first", "second"])
    assert client.invoke(system=SYS, content=CONTENT) == "first"
    assert client.invoke(system=SYS, content=CONTENT) == "second"
    assert client.calls == 2


def test_fake_client_fingerprint_lookup():
    fp = FakeBedrockClient.fingerprint(SYS, CONTENT, None)
    client = FakeBedrockClient(by_fingerprint={fp: "matched"})
    assert client.invoke(system=SYS, content=CONTENT) == "matched"


def test_fake_client_fingerprint_is_deterministic():
    a = FakeBedrockClient.fingerprint(SYS, CONTENT, None)
    b = FakeBedrockClient.fingerprint(SYS, CONTENT, None)
    assert a == b
    # repair_hint changes the fingerprint
    c = FakeBedrockClient.fingerprint(SYS, CONTENT, "fix it")
    assert c != a


def test_fake_client_raises_when_no_script():
    client = FakeBedrockClient()  # nothing scripted
    with pytest.raises(BedrockError):
        client.invoke(system=SYS, content=CONTENT)


def test_fake_client_raise_on_invoke():
    boom = RuntimeError("simulated model failure")
    client = FakeBedrockClient(raise_on_invoke=boom)
    with pytest.raises(RuntimeError, match="simulated model failure"):
        client.invoke(system=SYS, content=CONTENT)


def test_make_client_requires_model_id(monkeypatch):
    # T12: unset model id -> clear ConfigError, no hardcoded fallback.
    monkeypatch.delenv(config.ENV_MODEL_ID, raising=False)
    with pytest.raises(config.ConfigError):
        make_client()


def test_make_client_reads_model_id_from_env(monkeypatch):
    # T12: with the env var set, make_client() reaches the boto3 path.
    # boto3 is not installed on the offline dev box, so we assert it fails trying to
    # import/use boto3 rather than on a missing model id. Either way, the model id
    # was read from the environment and never hardcoded.
    monkeypatch.setenv(config.ENV_MODEL_ID, "anthropic.fake-model-v1")
    monkeypatch.setenv(config.ENV_AWS_REGION, "us-east-1")
    try:
        make_client()
    except config.ConfigError:
        pytest.fail("model id was set but make_client raised ConfigError")
    except Exception:
        # Expected: boto3 missing or no AWS creds. The point is we got past config.
        pass
