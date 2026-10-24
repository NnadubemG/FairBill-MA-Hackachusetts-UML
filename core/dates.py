"""Service-date parsing shared by the duplicate and unbundling checks."""

from __future__ import annotations

from datetime import date
from typing import Optional

from contracts.types import LineItem


def service_date(item: LineItem) -> Optional[date]:
    """The item's date of service, or None if missing or unreadable (treated as undated)."""
    value = item.date_of_service
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None
