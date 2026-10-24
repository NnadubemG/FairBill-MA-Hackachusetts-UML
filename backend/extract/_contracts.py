"""Import shim for the shared `/contracts` Python mirror.

`/contracts` is not a package (it is the shared source-of-truth directory owned by
Thomas), so this shim makes `contracts/types.py` importable from `/backend/extract`
without copying or redefining any contract type. The JSON Schema remains canonical;
we only reuse the dataclass mirror here.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# repo_root/backend/extract/_contracts.py -> repo_root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_TYPES_PATH = _REPO_ROOT / "contracts" / "types.py"


def _load_contracts():
    spec = importlib.util.spec_from_file_location("fairbill_contracts", _TYPES_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"Cannot load contracts mirror at {_TYPES_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("fairbill_contracts", module)
    spec.loader.exec_module(module)
    return module


_contracts = _load_contracts()

# Re-export the contract types we use. Do NOT redefine them.
LineItem = _contracts.LineItem
CodeSystem = _contracts.CodeSystem

# Path to the canonical JSON Schema, used by the validator.
LINE_ITEM_SCHEMA_PATH = _REPO_ROOT / "contracts" / "line-item.schema.json"

__all__ = ["LineItem", "CodeSystem", "LINE_ITEM_SCHEMA_PATH"]
