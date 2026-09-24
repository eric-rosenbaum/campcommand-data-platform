"""The events pipeline must give the same answer however the data arrives.

Deliver a season of uploads to the warehouse in several stages, cut at
random points in time, running the incremental dbt models after each one.
Then rebuild everything from scratch with --full-refresh. The two results
have to match row for row.
"""

import random
from datetime import date

import pytest

from campcommand.contracts import ContractRegistry
from campcommand.sync import deliver
from campcommand.synthetic.events import SeasonSimulator
from campcommand.synthetic.world import build_world
from campcommand.warehouse import Warehouse

SEASON = (date(2026, 6, 22), date(2026, 8, 21))

SNAPSHOTS = {
    "fct_maintenance_events": """
        select event_id, work_order_key, event_action, event_at, received_at, building_key,
               asset_key, staff_key, is_late_arrival, is_clock_corrected
        from core.fct_maintenance_events
    """,
    "fct_work_orders": """
        select work_order_key, status, opened_at, assigned_at, started_at, completed_at,
               building_key, priority, labor_minutes, parts_cost, event_count
        from core.fct_work_orders
    """,
    "fct_waterfront_checks": """
        select event_id, checked_at, building_key, chlorine_ppm, ph, is_out_of_range
        from core.fct_waterfront_checks
    """,
    "rpt_maintenance_daily": """
        select tenant_id, activity_date, building_key, work_orders_opened, work_orders_completed,
               labor_minutes, parts_cost, late_events
        from reporting.rpt_maintenance_daily
    """,
}


@pytest.fixture(scope="module")
def uploads():
    out = []
    for tenant_id, tz in [("tall_pines", "America/New_York"), ("chene_rouge", "America/Toronto")]:
        world = build_world(tenant_id, 5, SEASON[0])
        out += SeasonSimulator(world, tz, SEASON, 5).run()
    return sorted(out, key=lambda u: u.received_at)


def snapshot(query) -> dict[str, list]:
    return {name: sorted(query(sql), key=repr) for name, sql in SNAPSHOTS.items()}


@pytest.mark.parametrize("seed", [1, 2])
def test_incremental_runs_match_a_full_rebuild(settings, dbt, query, uploads, seed):
    warehouse = Warehouse(settings.warehouse_url, ContractRegistry(settings.contracts_dir))
    with warehouse.engine.begin() as conn:
        conn.exec_driver_sql("truncate raw.app_events")

    rng = random.Random(seed)
    cut_points = sorted(rng.sample(range(1, len(uploads)), 5))
    select = ["--select", "+tag:events", "--indirect-selection", "cautious"]

    start = 0
    for i, cut in enumerate([*cut_points, len(uploads)]):
        deliver(warehouse, uploads[start:cut])
        start = cut
        dbt("build", *select, *(["--full-refresh"] if i == 0 else []))

    incremental = snapshot(query)
    dbt("build", *select, "--full-refresh")
    rebuilt = snapshot(query)

    for name in SNAPSHOTS:
        assert incremental[name] == rebuilt[name], name


def test_every_event_lands_exactly_once(query, uploads):
    distinct_events = len({e["event_id"] for u in uploads for e in u.events})
    uploaded_copies = sum(len(u.events) for u in uploads)
    (landed,) = query("select count(*) from raw.app_events")[0]
    (kept,) = query("select count(*) from intermediate.int_app_events_deduplicated")[0]

    assert uploaded_copies > distinct_events
    assert landed == uploaded_copies
    assert kept == distinct_events


def test_late_events_reopen_their_day(query):
    (late_days,) = query("select count(*) from reporting.rpt_maintenance_daily where late_events > 0")[0]
    assert late_days > 0
