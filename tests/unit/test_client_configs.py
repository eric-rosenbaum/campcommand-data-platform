"""Client configs are hand-edited YAML. Catch mistakes before a file arrives."""


def test_every_feed_uses_a_known_contract(clients, registry):
    for client in clients.values():
        for cfg in client.feeds.values():
            assert registry.get(cfg.contract).feed == cfg.feed


def test_mapped_columns_exist_in_the_contract(clients, registry):
    for client in clients.values():
        for cfg in client.feeds.values():
            fields = registry.get(cfg.contract).fields
            unknown = set(cfg.columns.values()) - set(fields)
            assert not unknown, f"{client.tenant_id}/{cfg.feed}: {unknown}"


def test_every_required_field_is_mapped(clients, registry):
    for client in clients.values():
        for cfg in client.feeds.values():
            contract = registry.get(cfg.contract)
            required = {f.name for f in contract.fields.values() if f.required}
            assert required <= set(cfg.columns.values()), f"{client.tenant_id}/{cfg.feed}"


def test_value_maps_only_produce_allowed_values(clients, registry):
    for client in clients.values():
        for cfg in client.feeds.values():
            contract = registry.get(cfg.contract)
            for field, mapping in cfg.values.items():
                allowed = contract.fields[field].allowed
                if allowed is None:
                    continue
                assert set(mapping.values()) <= set(allowed), f"{client.tenant_id}/{cfg.feed}.{field}"
