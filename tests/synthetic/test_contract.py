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
