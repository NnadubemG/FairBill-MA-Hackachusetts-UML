"""Disk cache for model calls, keyed by the bill file hash.

Every model call in the harness goes through ``CachingClient``. A reply that is already on
disk is returned without calling the model, so a rerun costs nothing, and a change to the
file, the model, the task or any prompt gives a new key (a miss).

Key = SHA-256 of: schema tag | task | model name | SHA-256 of the bill file | hash of the
whole request (system prompt, content, repair hint, max_tokens).

Entry files hold only ``task``, ``model``, ``file_sha256`` and ``reply``. They never hold the
API key, and have no timestamps. Only successful, non-empty text replies are cached.

Two guards keep cost under control:
- ``cache_only``: a miss never reaches the model (it acts like a failed call).
- ``max_calls``: real calls stop after N (cache hits do not count).

``CacheMiss`` and ``BudgetExceeded`` are ``LLMError`` subclasses, so the features' own
fallbacks (extract, explain, letter) handle them exactly like a failed model call.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from backend.extract.llm_client import LLMClient, LLMError

SCHEMA_TAG = "evals-cache-v1"
_ENTRY_FIELDS = ("task", "model", "file_sha256", "reply")


class CacheMiss(LLMError):
    """A cache-only run asked for a reply that is not on disk."""


class BudgetExceeded(LLMError):
    """The real-call budget (``max_calls``) is used up."""


@dataclass
class CacheStats:
    """Counters for the report. No content, only numbers."""

    hits: int = 0
    misses: int = 0  # every call that was not answered from disk
    real_calls: int = 0  # calls that reached the model (successful or not)
    failures: int = 0  # real calls that raised
    cache_only_misses: int = 0
    budget_hit: bool = False
    write_errors: int = 0


def sha256_bytes(data: bytes) -> str:
    """SHA-256 of bytes, as hex."""
    return hashlib.sha256(data).hexdigest()


def request_hash(
    system: str,
    content: list[dict],
    repair_hint: str | None = None,
    max_tokens: int | None = None,
) -> str:
    """Hash of the whole request. Does not depend on dict order."""
    payload = json.dumps(
        {"system": system, "content": content, "repair_hint": repair_hint, "max_tokens": max_tokens},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return sha256_bytes(payload.encode("utf-8"))


def cache_key(task: str, model: str, file_sha256: str, req_hash: str) -> str:
    """The key for one call."""
    parts = "\0".join([SCHEMA_TAG, task, model, file_sha256, req_hash])
    return sha256_bytes(parts.encode("utf-8"))


class CachingClient:
    """Cache around one real client per task. Use ``scoped`` to get a client for one call site."""

    def __init__(
        self,
        inners: Mapping[str, LLMClient | None],
        models: Mapping[str, str],
        cache_dir: Path,
        *,
        cache_only: bool = False,
        max_calls: int = 60,
    ) -> None:
        self._inners = dict(inners)
        self._models = dict(models)
        self._dir = Path(cache_dir)
        self._cache_only = cache_only
        self._max_calls = max_calls
        self.stats = CacheStats()

    # --- public ----------------------------------------------------------------

    def scoped(self, task: str, file_sha256: str) -> LLMClient:
        """A client for one task and one bill file."""
        return _Scoped(self, task, file_sha256)

    def model_for(self, task: str) -> str:
        return self._models.get(task, "")

    # --- internals -------------------------------------------------------------

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        ignore = self._dir / ".gitignore"
        if not ignore.exists():
            ignore.write_text("*\n", encoding="utf-8")

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    def _read(self, key: str, task: str, model: str, file_sha256: str) -> str | None:
        """The cached reply, or None if there is no valid entry for exactly this call."""
        try:
            with open(self._path(key), encoding="utf-8") as fh:
                entry = json.load(fh)
        except (OSError, ValueError):
            return None
        if not isinstance(entry, dict) or set(entry) != set(_ENTRY_FIELDS):
            return None
        reply = entry["reply"]
        if not isinstance(reply, str) or not reply.strip():
            return None
        if (entry["task"], entry["model"], entry["file_sha256"]) != (task, model, file_sha256):
            return None
        return reply

    def _write(self, key: str, task: str, model: str, file_sha256: str, reply: str) -> None:
        entry = {"task": task, "model": model, "file_sha256": file_sha256, "reply": reply}
        tmp = self._dir / f".{key}.tmp-{os.getpid()}"
        try:
            self._ensure_dir()
            tmp.write_text(json.dumps(entry, sort_keys=True), encoding="utf-8")
            os.replace(tmp, self._path(key))
        except OSError:
            self.stats.write_errors += 1
            try:
                tmp.unlink()
            except OSError:
                pass

    def call(
        self,
        task: str,
        file_sha256: str,
        *,
        system: str,
        content: list[dict],
        repair_hint: str | None = None,
        max_tokens: int | None = None,
    ) -> Any:
        model = self.model_for(task)
        key = cache_key(task, model, file_sha256, request_hash(system, content, repair_hint, max_tokens))

        cached = self._read(key, task, model, file_sha256)
        if cached is not None:
            self.stats.hits += 1
            return cached

        self.stats.misses += 1
        if self._cache_only:
            self.stats.cache_only_misses += 1
            raise CacheMiss("not in the cache (cache-only run)")
        inner = self._inners.get(task)
        if inner is None:
            raise CacheMiss("no model client for this task")
        if self.stats.real_calls >= self._max_calls:
            self.stats.budget_hit = True
            raise BudgetExceeded("real-call budget reached")

        self.stats.real_calls += 1
        try:
            reply = inner.invoke(
                system=system, content=content, repair_hint=repair_hint, max_tokens=max_tokens
            )
        except Exception:
            self.stats.failures += 1
            raise  # not cached; the feature's own fallback handles it
        if isinstance(reply, str) and reply.strip():
            self._write(key, task, model, file_sha256, reply)
        return reply


class _Scoped:
    """Implements the ``LLMClient`` shape for one task and one bill file."""

    def __init__(self, owner: CachingClient, task: str, file_sha256: str) -> None:
        self._owner = owner
        self._task = task
        self._sha = file_sha256

    def invoke(
        self,
        *,
        system: str,
        content: list[dict],
        repair_hint: str | None = None,
        max_tokens: int | None = None,
    ) -> Any:
        return self._owner.call(
            self._task,
            self._sha,
            system=system,
            content=content,
            repair_hint=repair_hint,
            max_tokens=max_tokens,
        )


__all__ = [
    "SCHEMA_TAG",
    "CacheMiss",
    "BudgetExceeded",
    "CacheStats",
    "CachingClient",
    "sha256_bytes",
    "request_hash",
    "cache_key",
]
