import logging
from datetime import date, datetime
from pathlib import Path

import typer
from sqlalchemy import create_engine, text

from campcommand.clients import load_clients
from campcommand.config import load_settings
from campcommand.contracts import ContractRegistry
from campcommand.pipeline import Pipeline
from campcommand.sync import deliver, read_uploads, write_uploads
from campcommand.synthetic.events import SeasonSimulator
from campcommand.synthetic.exports import season_for, write_round
from campcommand.synthetic.world import build_world
from campcommand.warehouse import Warehouse

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _events_dir(landing_dir: Path) -> Path:
    return landing_dir / "_events"


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(message)s")


@app.command()
def bootstrap() -> None:
    """Create roles, the raw schema and raw tables (local Postgres)."""
    settings = load_settings()
    sql = (settings.dbt_project_dir / "bootstrap" / "postgres.sql").read_text()
    engine = create_engine(settings.admin_url, isolation_level="AUTOCOMMIT")
    conn = engine.raw_connection()
    try:
        # Straight to the driver: the script has format() placeholders that
        # SQLAlchemy would otherwise try to bind.
        conn.cursor().execute(sql)
        conn.commit()
    finally:
        conn.close()
    Warehouse(settings.warehouse_url, ContractRegistry(settings.contracts_dir)).create_tables()
    typer.echo("warehouse bootstrapped")


@app.command()
def reset(yes: bool = typer.Option(False, "--yes")) -> None:
    """Drop the raw and dbt schemas, landing files and reports."""
    if not yes:
        typer.confirm("Drop all CampCommand schemas and generated files?", abort=True)
    settings = load_settings()
    engine = create_engine(settings.admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        for schema in (
            "raw",
            "staging",
            "intermediate",
            "core",
            "reporting",
            "monitoring",
            "security",
            "analytics",
        ):
            conn.execute(text(f"drop schema if exists {schema} cascade"))
    for directory in (settings.landing_dir, settings.reports_dir):
        for path in sorted(directory.rglob("*"), reverse=True) if directory.exists() else []:
            path.unlink() if path.is_file() else path.rmdir()
    typer.echo("reset")


@app.command()
def generate(
    round_number: int = typer.Option(1, "--round", help="1 = first exports, 2 = corrected re-exports."),
    seed: int = 11,
    today: str = typer.Option(
        None, help="YYYY-MM-DD; the season generated is the last one before this date."
    ),
) -> None:
    """Write synthetic client exports (and, for round 1, a season of app events)."""
    settings = load_settings()
    registry = ContractRegistry(settings.contracts_dir)
    clients = load_clients(settings.clients_dir)
    season = season_for(date.fromisoformat(today) if today else date.today())

    for tenant_id, client in clients.items():
        world = build_world(tenant_id, seed, season[0])
        files = write_round(world, client, registry, settings.landing_dir, season, round_number, seed)
        typer.echo(f"{client.name}: {len(files)} export file(s)")
        if round_number == 1:
            uploads = SeasonSimulator(world, client.timezone, season, seed).run()
            write_uploads(_events_dir(settings.landing_dir) / f"{tenant_id}.jsonl", uploads)
            events = sum(len(u.events) for u in uploads)
            typer.echo(f"  {len(uploads):,} device uploads carrying {events:,} events")


@app.command()
def ingest(tenant: list[str] = typer.Option(None, help="Only these tenants.")) -> None:
    """Validate and load everything waiting in the landing folder."""
    pipeline = Pipeline(load_settings())
    tenants = tenant or list(pipeline.clients)
    width = max(len(t) for t in tenants)
    for tenant_id in tenants:
        for r in pipeline.ingest_tenant(tenant_id):
            if r.status == "skipped":
                continue
            line = (
                f"{tenant_id:<{width}}  {r.source_file:<42} {r.status:<19}"
                f"{r.rows_loaded:>6,} loaded {r.rows_quarantined:>4} held"
            )
            if r.rows_resolved:
                line += f"  {r.rows_resolved} resolved"
            typer.echo(line)


@app.command()
def sync(
    until: str = typer.Option(None, help="Only deliver uploads received up to this ISO timestamp."),
) -> None:
    """Land device uploads into raw.app_events."""
    settings = load_settings()
    warehouse = Warehouse(settings.warehouse_url, ContractRegistry(settings.contracts_dir))
    cutoff = datetime.fromisoformat(until) if until else None
    total = 0
    for path in sorted(_events_dir(settings.landing_dir).glob("*.jsonl")):
        total += deliver(warehouse, read_uploads(path), cutoff)
    typer.echo(f"landed {total:,} event rows")


@app.command()
def status() -> None:
    """Onboarding health per camp and feed (reads monitoring.mon_ingestion_quality)."""
    settings = load_settings()
    engine = create_engine(settings.admin_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                select camp_name, feed, batches, files_rejected, rows_loaded, rows_quarantined,
                       rows_resolved, rows_open
                from monitoring.mon_ingestion_quality
                order by camp_name, feed
                """
            )
        ).fetchall()
    header = f"{'camp':<18} {'feed':<24} {'files':>5} {'rejected':>8} {'loaded':>8} {'held':>6} {'fixed':>6} {'open':>5}"
    typer.echo(header)
    typer.echo("-" * len(header))
    for r in rows:
        typer.echo(f"{r[0]:<18} {r[1]:<24} {r[2]:>5} {r[3]:>8} {r[4]:>8,} {r[5]:>6,} {r[6]:>6,} {r[7]:>5}")


@app.command()
def quarantine(tenant: str = typer.Option(None)) -> None:
    """Rows still waiting on a client fix."""
    settings = load_settings()
    warehouse = Warehouse(settings.warehouse_url, ContractRegistry(settings.contracts_dir))
    rows = warehouse.open_quarantine(tenant)
    if not rows:
        typer.echo("nothing in quarantine")
        return
    for r in rows:
        typer.echo(f"{r['tenant_id']:<12} {r['feed']:<24} {r['source_file']:<40} row {r['source_row']}")


if __name__ == "__main__":
    app()
