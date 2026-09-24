from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from campcommand.pipeline import Pipeline
from campcommand.sync import deliver
from campcommand.synthetic.events import SeasonSimulator
from campcommand.synthetic.exports import write_round
from campcommand.synthetic.world import build_world

SEASON = (date(2026, 6, 22), date(2026, 8, 21))
TENANTS = ["tall_pines", "lakeview", "chene_rouge"]


@pytest.fixture(scope="module")
def built(settings, dbt):
    pipeline = Pipeline(settings)
    for tenant_id, client in pipeline.clients.items():
        world = build_world(tenant_id, 11, SEASON[0])
        write_round(world, client, pipeline.registry, settings.landing_dir, SEASON, 1, 11)
        pipeline.ingest_tenant(tenant_id)
        deliver(pipeline.warehouse, SeasonSimulator(world, client.timezone, SEASON, 11).run())
    dbt("build")
    return settings


@pytest.fixture(scope="module")
def tenant_tables(built, query):
    return [
        f"{schema}.{table}"
        for schema, table in query(
            """
            select table_schema, table_name
            from information_schema.columns
            where column_name = 'tenant_id'
              and table_schema in ('core', 'reporting', 'monitoring')
            """
        )
    ]


def connect_as(settings, role: str, password: str):
    url = make_url(settings.admin_url).set(username=role, password=password)
    return create_engine(url)


def tenants_visible(engine, table: str) -> set[str]:
    with engine.connect() as conn:
        return {r[0] for r in conn.execute(text(f"select distinct tenant_id from {table}"))}


def test_every_mart_is_covered(tenant_tables):
    assert len(tenant_tables) >= 12


@pytest.mark.parametrize("tenant", TENANTS)
def test_reader_sees_only_its_own_camp(built, tenant_tables, tenant):
    engine = connect_as(built, f"{tenant}_reader", "reader")
    for table in tenant_tables:
        assert tenants_visible(engine, table) <= {tenant}, table
    assert tenants_visible(engine, "core.fct_commissary_sales") == {tenant}


def test_platform_admin_sees_every_camp(built):
    admin = create_engine(built.admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("drop role if exists test_platform_admin"))
        conn.execute(text("create role test_platform_admin login password 'x' in role platform_admin"))
    engine = connect_as(built, "test_platform_admin", "x")
    assert tenants_visible(engine, "core.fct_commissary_sales") == set(TENANTS)
    engine.dispose()
    with admin.connect() as conn:
        conn.execute(text("drop owned by test_platform_admin"))
        conn.execute(text("drop role test_platform_admin"))


def test_reader_without_a_mapping_sees_nothing(built, tenant_tables):
    admin = create_engine(built.admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("drop role if exists test_unmapped"))
        conn.execute(text("create role test_unmapped login password 'x' in role tenant_reader"))
    engine = connect_as(built, "test_unmapped", "x")
    for table in tenant_tables:
        assert tenants_visible(engine, table) == set(), table
    engine.dispose()
    with admin.connect() as conn:
        conn.execute(text("drop owned by test_unmapped"))
        conn.execute(text("drop role test_unmapped"))


def test_inferred_members_stand_in_for_quarantined_reference_rows(built, query):
    # Round 1 quarantined a cabin with a blank name. Events at that cabin
    # still join, to an inferred building.
    inferred = query("select tenant_id, building_code from core.dim_building where is_inferred")
    assert {t for t, _ in inferred} == set(TENANTS)
