"""Shared domain contracts package (Python side).

Re-exports the dataclasses and type aliases from ``contracts.py`` so backend
code can do, e.g.::

    from contracts import LineItem, AnalysisResult, ExtractRequest

This mirrors ``contracts/index.ts``. Keep both in sync.
"""

from .contracts import (
    AnalysisResult,
    AnalyzeRequest,
    AnalyzeResponse,
    ApiError,
    Cents,
    CompareRequest,
    CompareResponse,
    Confidence,
    ExtractRequest,
    ExtractResponse,
    Flag,
    FlagBasis,
    IsoTimestamp,
    LetterDraft,
    LetterRecipient,
    LetterRequest,
    LetterResponse,
    LetterType,
    LineItem,
    PriceRange,
    ProcedureInfo,
    ProceduresRequest,
    ProceduresResponse,
)

__all__ = [
    "AnalysisResult",
    "AnalyzeRequest",
    "AnalyzeResponse",
    "ApiError",
    "Cents",
    "CompareRequest",
    "CompareResponse",
    "Confidence",
    "ExtractRequest",
    "ExtractResponse",
    "Flag",
    "FlagBasis",
    "IsoTimestamp",
    "LetterDraft",
    "LetterRecipient",
    "LetterRequest",
    "LetterResponse",
    "LetterType",
    "LineItem",
    "PriceRange",
    "ProcedureInfo",
    "ProceduresRequest",
    "ProceduresResponse",
]
