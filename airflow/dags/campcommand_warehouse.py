"""Rebuild the warehouse after new client data lands.

Triggered by the onboarding DAG through the raw reference data asset, not on
a clock: nothing downstream changes until a camp sends something.
"""

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag
from campcommand_common import DEFAULT_ARGS, RAW_REFERENCE_DATA, dbt


@dag(
    dag_id="campcommand_warehouse",
    schedule=[RAW_REFERENCE_DATA],
    start_date=pendulum.datetime(2026, 6, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    doc_md=__doc__,
    tags=["campcommand", "dbt"],
)
def campcommand_warehouse():
    seed = BashOperator(task_id="seed", bash_command=dbt("seed"))
    build = BashOperator(task_id="build", bash_command=dbt("build --exclude resource_type:seed"))
    seed >> build


campcommand_warehouse()
