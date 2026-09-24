import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(os.environ.get("CAMPCOMMAND_REPO_ROOT", Path(__file__).resolve().parents[2]))


@dataclass(frozen=True)
class Settings:
    warehouse_url: str
    admin_url: str
    landing_dir: Path
    reports_dir: Path
    clients_dir: Path
    contracts_dir: Path
    dbt_project_dir: Path


def load_settings() -> Settings:
    env = os.environ
    host = env.get("CAMPCOMMAND_DB_HOST", "localhost")
    port = env.get("CAMPCOMMAND_DB_PORT", "5443")
    db = env.get("CAMPCOMMAND_DB_NAME", "campcommand")
    return Settings(
        # In production this points at Snowflake, e.g.
        # snowflake://LOADER@<account>/CAMPCOMMAND/RAW?warehouse=LOADING&role=LOADER
        warehouse_url=env.get(
            "CAMPCOMMAND_WAREHOUSE_URL",
            f"postgresql+psycopg://loader:loader@{host}:{port}/{db}",
        ),
        admin_url=env.get(
            "CAMPCOMMAND_ADMIN_URL",
            f"postgresql+psycopg://postgres:postgres@{host}:{port}/{db}",
        ),
        landing_dir=Path(env.get("CAMPCOMMAND_LANDING_DIR", REPO_ROOT / "landing")),
        reports_dir=Path(env.get("CAMPCOMMAND_REPORTS_DIR", REPO_ROOT / "reports")),
        clients_dir=REPO_ROOT / "clients",
        contracts_dir=REPO_ROOT / "contracts",
        dbt_project_dir=REPO_ROOT / "warehouse",
    )
