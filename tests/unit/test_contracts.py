import pytest

from campcommand.contracts import ContractError


def test_every_version_upgrades_to_latest(registry):
    for feed in registry.feeds:
        latest = registry.latest(feed)
        for contract in registry.versions(feed):
            record = {name: None for name in contract.fields}
            upgraded = registry.upgrade(record, contract)
            assert set(upgraded) == set(latest.fields)


def test_assets_v1_record_becomes_v2(registry):
    v1 = registry.get("assets@1")
    upgraded = registry.upgrade(
        {
            "asset_tag": "CR-EQ-0042",
            "asset_name": "Canot",
            "building_code": "CR-03",
            "purchased_on": None,
            "purchase_price": 1450,
        },
        v1,
    )
    assert upgraded["purchase_cost"] == 1450
    assert upgraded["category"] == "other"
    assert upgraded["status"] == "in_service"
    assert "purchase_price" not in upgraded


def test_upgrade_never_overwrites_a_value(registry):
    v2 = registry.get("assets@2")
    record = {name: None for name in v2.fields} | {"category": "hvac"}
    assert registry.upgrade(record, v2)["category"] == "hvac"


def test_primary_keys_are_stable_across_versions(registry):
    for feed in registry.feeds:
        keys = {c.primary_key for c in registry.versions(feed)}
        assert len(keys) == 1, feed


def test_references_point_at_real_fields(registry):
    for feed in registry.feeds:
        for contract in registry.versions(feed):
            for f in contract.references:
                target_feed, target_field = f.references
                assert target_field in registry.latest(target_feed).fields


def test_unknown_contract(registry):
    with pytest.raises(ContractError):
        registry.get("assets@9")
