"""Test helpers. Reference data here is synthetic and never real."""

from __future__ import annotations

from contracts.types import LineItem, PriceReference, QuantityLimit


def make_item(
    id: str = "1",
    code: str | None = "99285",
    code_system: str | None = "CPT",
    description: str = "test item",
    billed_amount: float = 100.0,
    **kwargs,
) -> LineItem:
    return LineItem(
        id=id,
        code=code,
        code_system=code_system,
        description=description,
        billed_amount=billed_amount,
        **kwargs,
    )


def make_limit(
    code: str = "99285",
    code_system: str | None = "CPT",
    max_units: float = 2.0,
    data_year: int = 2000,
    **kwargs,
) -> QuantityLimit:
    return QuantityLimit(
        code=code,
        code_system=code_system,
        max_units=max_units,
        data_source=kwargs.pop("data_source", "synthetic-test"),
        data_year=data_year,
        **kwargs,
    )


def make_ref(
    code: str = "99285",
    code_system: str | None = "CPT",
    data_year: int = 2000,
    **kwargs,
) -> PriceReference:
    return PriceReference(
        code=code,
        code_system=code_system,
        data_source="synthetic-test",
        data_year=data_year,
        **kwargs,
    )
