import json
from datetime import date
from pathlib import Path

import pytest

from campcommand.pipeline import Pipeline
from campcommand.synthetic.exports import SALES_WEEK_MISSING_COLUMN, SALES_WEEK_WITH_ROW_ERRORS, write_round
from campcommand.synthetic.world import build_world

SEASON = (date(2026, 6, 22), date(2026, 8, 21))


@pytest.fixture(scope="module")
def pipeline(settings):
    return Pipeline(settings)


def export(pipeline, round_number):
    for tenant_id, client in pipeline.clients.items():
        world = build_world(tenant_id, 11, SEASON[0])
        write_round(world, client, pipeline.registry, pipeline.settings.landing_dir, SEASON, round_number, 11)


@pytest.fixture(scope="module")
def first_round(pipeline):
    export(pipeline, 1)
    return {t: pipeline.ingest_tenant(t) for t in pipeline.clients}


def test_every_file_is_accounted_for(first_round, pipeline):
    for tenant_id, results in first_round.items():
        landed = sorted(p.name for p in (pipeline.settings.landing_dir / tenant_id).iterdir())
        assert sorted(r.source_file for r in results) == landed


def test_reference_feeds_load_with_row_level_errors(first_round):
    for results in first_round.values():
        statuses = {r.feed: r.status for r in results if r.feed != "commissary_transactions"}
        assert statuses == {
            "buildings": "loaded_with_errors",
            "staff": "loaded_with_errors",
            "assets": "loaded_with_errors",
        }


def test_file_missing_a_required_column_is_rejected_whole(first_round):
    for results in first_round.values():
        sales = [r for r in results if r.feed == "commissary_transactions"]
        rejected = sales[SALES_WEEK_MISSING_COLUMN]
        assert rejected.status == "rejected"
        assert rejected.rows_loaded == 0
        assert sales[SALES_WEEK_WITH_ROW_ERRORS].status == "loaded_with_errors"


def test_quarantine_holds_each_injected_problem(first_round, query):
    rules = {
        rule
        for (violations,) in query("select violations from raw.quarantine where tenant_id = 'tall_pines'")
        for rule in {v["rule"] for v in json.loads(violations)}
    }
    assert rules == {
        "duplicate_key",
        "required",
        "not_allowed",
        "unknown_reference",
        "held_reference",
        "out_of_range",
        "invalid_type",
        "bad_format",
        "missing_column",
    }


def test_reports_speak_the_clients_language(first_round):
    report = next(r for r in first_round["chene_rouge"] if r.feed == "buildings").report_path
    html = Path(report).read_text(encoding="utf-8")
    assert "Camp Chêne Rouge" in html
    assert "Nom is blank" in html
    rows_csv = next(Path(report).parent.glob("*buildings*_rows_to_fix.csv")).read_text(encoding="utf-8-sig")
    assert rows_csv.splitlines()[0].startswith("Row in your file,Code du bâtiment,Nom")


def test_reingesting_the_same_files_is_a_no_op(first_round, pipeline, query):
    before = query("select count(*) from raw.buildings")
    again = [r for t in pipeline.clients for r in pipeline.ingest_tenant(t)]
    assert {r.status for r in again} == {"skipped"}
    assert query("select count(*) from raw.buildings") == before


def test_corrected_exports_resolve_the_quarantine(first_round, pipeline, query):
    export(pipeline, 2)
    second = [r for t in pipeline.clients for r in pipeline.ingest_tenant(t) if r.status != "skipped"]
    assert {r.status for r in second} == {"loaded"}

    still_open = query(
        "select tenant_id, feed, record_key from raw.quarantine where resolved_batch_id is null"
    )
    # Only rows with no key at all (a blank asset tag) can't be matched to a
    # resend; everything else was closed out automatically.
    assert {(tenant, feed, key) for tenant, feed, key in still_open} == {
        ("tall_pines", "assets", None),
        ("lakeview", "assets", None),
        ("chene_rouge", "assets", None),
    }


def test_sales_lines_are_not_double_counted_across_overlapping_exports(first_round, query):
    raw_lines, distinct_lines = query(
        """
        select count(*), count(distinct tenant_id || transaction_id || '-' || line_number)
        from raw.commissary_transactions
        """
    )[0]
    assert raw_lines > distinct_lines
