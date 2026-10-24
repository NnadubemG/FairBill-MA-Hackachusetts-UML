"""Tests for explain scaffold and config (spec task 1). Covers E21."""

from __future__ import annotations

from contracts.types import Flag as ContractFlag
from core.constants import BANNED_WORDS as CORE_BANNED_WORDS

from backend.explain import config
from backend.explain._contracts import Flag
from backend.explain.models import ExplainResult


def test_e21_banned_words_match_core():
    # Read-only comparison so the two lists cannot drift apart.
    assert tuple(config.BANNED_WORDS) == tuple(CORE_BANNED_WORDS)


def test_flag_is_the_contract_class():
    assert Flag is ContractFlag


def test_env_var_name():
    assert config.ENV_MODEL_ID == "EXPLAIN_MODEL_ID"


def test_limits_are_sane():
    assert config.MAX_FLAGS_PER_CALL >= 1
    assert config.MAX_WORDS >= 20
    assert 1 <= config.MIN_SENTENCES <= config.MAX_SENTENCES


def test_explain_result_defaults():
    r = ExplainResult()
    assert r.flags == [] and r.fallback_count == 0 and r.warnings == []
