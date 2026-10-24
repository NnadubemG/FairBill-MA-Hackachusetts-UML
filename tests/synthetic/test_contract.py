import dataclasses
import json
import typing
from pathlib import Path

import contracts.types as t

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "contracts" / "synthetic-bill.schema.json").read_text(encoding="utf-8")
)


def required_fields(cls) -> set[str]:
    return {
        f.name
        for f in dataclasses.fields(cls)
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
    }


def test_synthetic_bill_schema_matches_python_mirror():  # TS-K1
    assert set(SCHEMA["required"]) == required_fields(t.SyntheticBill)
    assert set(SCHEMA["properties"]) == {f.name for f in dataclasses.fields(t.SyntheticBill)}

    meta = SCHEMA["properties"]["bill_metadata"]
    assert set(meta["required"]) == required_fields(t.BillMetadata)
    assert set(meta["properties"]) == {f.name for f in dataclasses.fields(t.BillMetadata)}

    expected = SCHEMA["properties"]["expected_flags"]["items"]
    assert set(expected["required"]) == required_fields(t.ExpectedFlag)


def test_scenarios_and_flag_types_match_the_mirror():  # TS-K1
    assert set(SCHEMA["properties"]["scenario"]["enum"]) == set(typing.get_args(t.SyntheticScenario))
    flag_enum = SCHEMA["properties"]["expected_flags"]["items"]["properties"]["flag_type"]["enum"]
    assert set(flag_enum) == set(typing.get_args(t.FlagType))


def load(name: str) -> dict:
    path = Path(__file__).resolve().parents[2] / "contracts" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_quantity_limit_and_bundle_pair_schemas_match_mirrors():  # TS-N5
    for name, cls in (("quantity-limit.schema.json", t.QuantityLimit), ("bundle-pair.schema.json", t.BundlePair)):
        schema = load(name)
        assert set(schema["required"]) == required_fields(cls)
        assert set(schema["properties"]) == {f.name for f in dataclasses.fields(cls)}
    pair = load("bundle-pair.schema.json")
    assert set(pair["properties"]["modifier_indicator"]["enum"]) == set(typing.get_args(t.ModifierIndicator))


def test_new_synthetic_fields_are_optional():  # TS-N5
    assert "quantity_limits" not in SCHEMA["required"] and "bundle_pairs" not in SCHEMA["required"]
    assert required_fields(t.SyntheticBill) == set(SCHEMA["required"])
