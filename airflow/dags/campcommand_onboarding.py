"""Client onboarding: validate and load whatever camps have dropped off.

One mapped task per camp with new files. Within a camp, feeds load in
dependency order (buildings before assets, and so on), so a camp is the unit
of parallelism, not a file. Any batch that produced an error report is
emailed to that camp's contact as soon as the camp's files are done.
"""

from datetime import timedelta

import pendulum
from airflow.sdk import dag, task
from campcommand_common import DEFAULT_ARGS, PIPELINE_PYTHON, RAW_REFERENCE_DATA


@dag(
    dag_id="campcommand_onboarding",
    schedule="@hourly",
    start_date=pendulum.datetime(2026, 6, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS | {"retry_delay": timedelta(minutes=2)},
    doc_md=__doc__,
    tags=["campcommand", "ingestion"],
)
def campcommand_onboarding():
    # The pipeline runs in its own virtualenv (see airflow/Dockerfile), so
    # each task imports what it needs inside the function.
    @task.external_python(python=PIPELINE_PYTHON, expect_airflow=False)
    def tenants_with_new_files() -> list[str]:
        from campcommand.config import load_settings
        from campcommand.pipeline import Pipeline, sha256_of

        pipeline = Pipeline(load_settings())
        pending = []
        for tenant_id in pipeline.clients:
            for feed, path in pipeline.discover(tenant_id):
                if not pipeline.warehouse.already_ingested(tenant_id, feed, sha256_of(path)):
                    pending.append(tenant_id)
                    break
        return pending

    @task.external_python(
        python=PIPELINE_PYTHON,
        expect_airflow=False,
        outlets=[RAW_REFERENCE_DATA],
        max_active_tis_per_dagrun=4,
    )
    def ingest(tenant_id: str) -> list[dict]:
        from campcommand.config import load_settings
        from campcommand.notify import send_report
        from campcommand.pipeline import Pipeline

        pipeline = Pipeline(load_settings())
        client = pipeline.clients[tenant_id]
        batches = []
        for r in pipeline.ingest_tenant(tenant_id):
            if r.status == "skipped":
                continue
            if r.report_path:
                send_report(client, r.feed, r.source_file, r.report_path)
            batches.append(
                {
                    "tenant_id": r.tenant_id,
                    "source_file": r.source_file,
                    "status": r.status,
                    "rows_loaded": r.rows_loaded,
                    "rows_quarantined": r.rows_quarantined,
                    "rows_resolved": r.rows_resolved,
                }
            )
        return batches

    @task
    def summarize(results) -> dict:
        batches = [b for tenant_batches in results for b in tenant_batches]
        summary = {
            "files": len(batches),
            "rejected": sum(b["status"] == "rejected" for b in batches),
            "rows_loaded": sum(b["rows_loaded"] for b in batches),
            "rows_quarantined": sum(b["rows_quarantined"] for b in batches),
            "rows_resolved": sum(b["rows_resolved"] for b in batches),
        }
        print(summary)
        return summary

    summarize(ingest.expand(tenant_id=tenants_with_new_files()))


campcommand_onboarding()
