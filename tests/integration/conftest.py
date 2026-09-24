import os
from dataclasses import replace

import pytest
from dbt.cli.main import dbtRunner
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from campcommand.config import load_settings
from campcommand.contracts import ContractRegistry
from campcommand.warehouse import Warehouse

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def settings(request, tmp_path_factory):
    """A fresh database per test module, bootstrapped like the real one."""
    base = load_settings()
    name = f"campcommand_test_{request.module.__name__.rsplit('.', 1)[-1].removeprefix('test_')}"
    maintenance = make_url(base.admin_url).set(database="postgres")
    engine = create_engine(maintenance, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text(f"drop database if exists {name} with (force)"))
        conn.execute(text(f"create database {name}"))

    tmp = tmp_path_factory.mktemp(name)
    s = replace(
        base,
        admin_url=make_url(base.admin_url).set(database=name).render_as_string(hide_password=False),
        warehouse_url=make_url(base.warehouse_url).set(database=name).render_as_string(hide_password=False),
        landing_dir=tmp / "landing",
        reports_dir=tmp / "reports",
    )
    admin = create_engine(s.admin_url).raw_connection()
    admin.cursor().execute((s.dbt_project_dir / "bootstrap" / "postgres.sql").read_text())
    admin.commit()
    admin.close()
    Warehouse(s.warehouse_url, ContractRegistry(s.contracts_dir)).create_tables()

    previous = os.environ.get("CAMPCOMMAND_DB_NAME")
    os.environ["CAMPCOMMAND_DB_NAME"] = name
    yield s
    if previous is None:
        os.environ.pop("CAMPCOMMAND_DB_NAME", None)
    else:
        os.environ["CAMPCOMMAND_DB_NAME"] = previous
    with engine.connect() as conn:
        conn.execute(text(f"drop database if exists {name} with (force)"))


@pytest.fixture(scope="module")
def dbt(settings, tmp_path_factory):
    target = tmp_path_factory.mktemp("dbt_target")
    runner = dbtRunner()

    def run(*args: str):
        result = runner.invoke(
            [
                *args,
                "--project-dir",
                str(settings.dbt_project_dir),
                "--profiles-dir",
                str(settings.dbt_project_dir),
                "--target-path",
                str(target),
                "--log-level",
                "none",
            ]
        )
        failed = [r.node.name for r in (result.result or []) if r.status in ("error", "fail")]
        assert result.success, f"dbt {' '.join(args)} failed: {failed or result.exception}"
        return result

    return run


@pytest.fixture(scope="module")
def query(settings):
    engine = create_engine(settings.admin_url)

    def run(sql: str, **params):
        with engine.connect() as conn:
            return [tuple(r) for r in conn.execute(text(sql), params)]

    return run
