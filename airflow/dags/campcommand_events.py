"""Keep the event-driven marts current.

Devices upload through the sync endpoint straight into raw.app_events. Every
15 minutes this runs the incremental event models, which pick up whatever
arrived since the last run: late events reopen the days they belong to and
duplicates are dropped.

land_device_uploads only exists for the local demo, where uploads come from
a file instead of the sync endpoint.
"""

from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag
from campcommand_common import DEFAULT_ARGS, dbt


@dag(
    dag_id="campcommand_events",
    schedule="*/15 * * * *",
    start_date=pendulum.datetime(2026, 6, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS | {"retry_delay": timedelta(minutes=1)},
    doc_md=__doc__,
    tags=["campcommand", "dbt", "events"],
)
def campcommand_events():
    land = BashOperator(task_id="land_device_uploads", bash_command="campcommand sync")
    freshness = BashOperator(
        task_id="check_event_freshness",
        bash_command=dbt("source freshness --select source:raw.app_events"),
    )
    build = BashOperator(
        task_id="build_event_models",
        bash_command=dbt(
            "build --select +tag:events --exclude resource_type:seed --indirect-selection cautious"
        ),
    )
    land >> freshness >> build


campcommand_events()
