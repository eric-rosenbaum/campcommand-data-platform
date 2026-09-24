from campcommand.coercion import ParseOptions
from campcommand.mapping import MappedFile
from campcommand.validation import validate

LABELS = {
    "building_code": "Bldg Code",
    "building_name": "Building Name",
    "building_type": "Type",
    "capacity": "Beds",
    "year_built": "Year Built",
}


def mapped(rows, missing=()):
    return MappedFile(
        rows=rows,
        row_numbers=list(range(2, len(rows) + 2)),
        labels=LABELS,
        missing_columns=list(missing),
        unmapped_columns=[],
    )


def building(**overrides):
    return {
        "building_code": "TP-001",
        "building_name": "Birch",
        "building_type": "cabin",
        "capacity": "12",
        "year_built": "1970",
    } | overrides


def rules_for(result):
    return {(r.source_row, v.rule) for r in result.rejected for v in r.violations}


def test_clean_rows_are_typed(registry):
    result = validate(mapped([building()]), registry.get("buildings@1"), ParseOptions(), {})
    assert not result.rejected
    assert result.accepted[0].record["capacity"] == 12


def test_each_rule(registry):
    rows = [
        building(building_code="TP-001"),
        building(building_code="TP-002", building_name=""),
        building(building_code="TP-003", building_type="Yurt"),
        building(building_code="TP-004", capacity="lots"),
        building(building_code="TP-005", capacity="900"),
        building(building_code="tp 6"),
        building(building_code="TP-001", building_name="Birch again"),
    ]
    result = validate(mapped(rows), registry.get("buildings@1"), ParseOptions(), {})
    assert rules_for(result) == {
        (3, "required"),
        (4, "not_allowed"),
        (5, "invalid_type"),
        (6, "out_of_range"),
        (7, "bad_format"),
        (8, "duplicate_key"),
    }
    assert [r.source_row for r in result.accepted] == [2]


def test_messages_use_the_clients_column_names(registry):
    result = validate(mapped([building(building_name="")]), registry.get("buildings@1"), ParseOptions(), {})
    assert result.rejected[0].violations[0].message.startswith("Building Name is blank")


def test_duplicate_keeps_the_first_valid_row(registry):
    rows = [building(building_type="Yurt"), building(), building(building_name="Again")]
    result = validate(mapped(rows), registry.get("buildings@1"), ParseOptions(), {})
    assert [r.source_row for r in result.accepted] == [3]
    assert rules_for(result) == {(2, "not_allowed"), (4, "duplicate_key")}


def test_unknown_reference(registry):
    contract = registry.get("assets@1")
    rows = [
        {"asset_tag": "CR-EQ-1", "asset_name": "Canot", "building_code": "CR-01"},
        {"asset_tag": "CR-EQ-2", "asset_name": "Kayak", "building_code": "ZZ-99"},
    ]
    labels = {"asset_tag": "No d'inventaire", "asset_name": "Description", "building_code": "Bâtiment"}
    m = MappedFile(rows, [2, 3], labels, [], [])
    result = validate(m, contract, ParseOptions(), {("buildings", "building_code"): {"CR-01"}})
    assert rules_for(result) == {(3, "unknown_reference")}
    assert "Bâtiment 'ZZ-99'" in result.rejected[0].violations[0].message


def test_missing_required_column_rejects_the_file_but_keeps_keys(registry):
    result = validate(
        mapped([building(), building(building_code="TP-002")], missing=["Type"]),
        registry.get("buildings@1"),
        ParseOptions(),
        {},
    )
    assert not result.accepted
    assert [v.rule for v in result.file_violations] == ["missing_column"]
    assert [r.record["building_code"] for r in result.rejected] == ["TP-001", "TP-002"]


def test_reference_to_a_held_row_says_so(registry):
    contract = registry.get("assets@1")
    labels = {"asset_tag": "No d'inventaire", "asset_name": "Description", "building_code": "Bâtiment"}
    rows = [{"asset_tag": "CR-EQ-1", "asset_name": "Canot", "building_code": "CR-06"}]
    result = validate(
        MappedFile(rows, [2], labels, [], []),
        contract,
        ParseOptions(),
        known_keys={("buildings", "building_code"): set()},
        held_keys={("buildings", "building_code"): {"CR-06"}},
    )
    (violation,) = result.rejected[0].violations
    assert violation.rule == "held_reference"
    assert "held back" in violation.message
