"""A fake model that answers from the ground truth ("the oracle").

It exists to run the whole harness offline (``--fake``) and to test the scoring. Its numbers
say nothing about a real model, and the report says so.

It has the same shape as ``CachingClient``: ``scoped(task, file_sha256)`` returns a client for
one task and one bill, plus ``stats`` and ``model_for``. The extract reply is the truth lines.
The explain reply keeps each flag's reason and adds a different closing question. The letter
reply is a fixed first-person paragraph with no figures (worded differently from the fallback,
so tests can tell them apart).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Callable, Sequence

from backend.extract.llm_client import LLMClient, LLMError

from . import config
from .cache import CacheStats
from .corpus import Bill

ORACLE_QUESTION = "Could you walk me through this line?"
ORACLE_LETTER_PARAGRAPH = (
    "I would like to understand the lines listed below. "
    "I am asking how they were coded and billed. "
    "A review would help me understand them better."
)

# A hook to damage the extract reply (used by tests and dry runs):
# (bill, line dicts) -> line dicts.
ExtractTransform = Callable[[Bill, list[dict]], list[dict]]

_LINE_FIELDS = (
    "id", "description", "billed_amount", "code", "code_system", "raw_description",
    "quantity", "unit", "date_of_service",
)


def _line_dict(line: Any) -> dict:
    data = asdict(line)
    return {k: data.get(k) for k in _LINE_FIELDS}


class OracleClient:
    """Fake model keyed by the bill file hash."""

    def __init__(self, bills: Sequence[Bill], *, extract_transform: ExtractTransform | None = None) -> None:
        self._by_sha = {b.file_sha256: b for b in bills}
        self._transform = extract_transform
        self.stats = CacheStats()

    # --- same shape as CachingClient ------------------------------------------

    def scoped(self, task: str, file_sha256: str) -> LLMClient:
        return _OracleScoped(self, task, file_sha256)

    def model_for(self, task: str) -> str:
        return config.FAKE_MODEL_LABEL

    # --- replies -----------------------------------------------------------------

    def reply(self, task: str, file_sha256: str, content: list[dict]) -> str:
        self.stats.real_calls += 1
        bill = self._by_sha.get(file_sha256)
        if bill is None:
            raise LLMError("oracle has no bill for this file")
        if task == "extract":
            return self._extract(bill)
        if task == "explain":
            return self._explain(content)
        if task == "letter":
            return json.dumps({"paragraph": ORACLE_LETTER_PARAGRAPH})
        raise LLMError("oracle does not know this task")

    def _extract(self, bill: Bill) -> str:
        lines = [_line_dict(li) for li in bill.truth.line_items]
        if self._transform is not None:
            lines = self._transform(bill, lines)
        meta = bill.truth.bill_metadata
        hints = {str(li["id"]): ("high" if li.get("code") else "low") for li in lines}
        return json.dumps({
            "line_items": lines,
            "metadata": {
                "hospital_name": meta.hospital_name,
                "statement_date": meta.statement_date,
                "total": meta.total_billed,
            },
            "confidence_hints": hints,
        })

    @staticmethod
    def _explain(content: list[dict]) -> str:
        try:
            flags = json.loads(content[0]["text"])["flags"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError("oracle could not read the explain request") from exc
        return json.dumps({
            "explanations": [
                {"key": f["key"], "text": f"{f['reason'].strip()} {ORACLE_QUESTION}"} for f in flags
            ]
        })


class _OracleScoped:
    def __init__(self, owner: OracleClient, task: str, file_sha256: str) -> None:
        self._owner, self._task, self._sha = owner, task, file_sha256

    def invoke(
        self,
        *,
        system: str,
        content: list[dict],
        repair_hint: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        return self._owner.reply(self._task, self._sha, content)


__all__ = ["ORACLE_QUESTION", "ORACLE_LETTER_PARAGRAPH", "ExtractTransform", "OracleClient"]
