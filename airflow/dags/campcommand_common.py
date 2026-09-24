import os

from airflow.sdk import Asset

REPO_ROOT = os.environ.get("CAMPCOMMAND_REPO_ROOT", "/opt/campcommand")
PIPELINE_PYTHON = os.environ.get("CAMPCOMMAND_PYTHON", f"{REPO_ROOT}/venv/bin/python")
DBT_DIRS = f"--project-dir {REPO_ROOT}/warehouse --profiles-dir {REPO_ROOT}/warehouse"

# Updated whenever onboarding loads a client file; the warehouse DAG runs on it.
RAW_REFERENCE_DATA = Asset("campcommand://raw/reference_data")

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "retries": 2,
}


def dbt(command: str) -> str:
    return f"dbt --no-use-colors {command} {DBT_DIRS}"
