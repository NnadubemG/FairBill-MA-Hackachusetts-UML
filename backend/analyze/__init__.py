"""Analyze handler: confirmed LineItem[] -> AnalysisResult.

Pure Python (stdlib only). Combines ND's processed reference data with Thomas's /core
checks engine, and optionally Sam's explain function. David wraps `handle` in a Lambda.

Nothing here is persisted and no request body is ever logged.
"""

from .handler import AnalyzeError, analyze_bill, handle
from .store import ReferenceStore

__all__ = ["analyze_bill", "handle", "AnalyzeError", "ReferenceStore"]
