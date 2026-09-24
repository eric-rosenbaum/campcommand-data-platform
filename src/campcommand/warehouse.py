"""Raw layer of the warehouse.

Written with SQLAlchemy Core so the same code loads Postgres locally and
Snowflake in production (via snowflake-sqlalchemy). Everything here is
append-only except quarantine resolution.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Engine,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    and_,
    create_engine,
    select,
    update,
)

from campcommand.contracts import Contract, ContractRegistry

SQL_TYPES = {
    "string": String,
    "integer": Integer,
    "decimal": lambda: Numeric(12, 2),
    "date": Date,
    "timestamp": DateTime,
    "boolean": Boolean,
}


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class BatchRecord:
    batch_id: str
    tenant_id: str
    feed: str
    contract: str
    source_file: str
    file_sha256: str
    rows_received: int
    rows_loaded: int
    rows_quarantined: int
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    report_path: str | None = None


@dataclass
class QuarantinedRow:
    source_row: int | None
    record_key: str | None
    record: dict
    violations: list[dict]


def _feed_table(metadata: MetaData, contract: Contract) -> Table:
    columns = [Column("tenant_id", String(40), nullable=False)]
    columns += [Column(f.name, SQL_TYPES[f.type]()) for f in contract.fields.values()]
    columns += [
        Column("_batch_id", String(36), nullable=False),
        Column("_source_file", String(255), nullable=False),
        Column("_source_row", Integer),
        Column("_contract_version", Integer, nullable=False),
        Column("_loaded_at", DateTime, nullable=False),
    ]
    return Table(contract.feed, metadata, *columns)


class Warehouse:
    def __init__(self, url: str | Engine, registry: ContractRegistry):
        self.engine = create_engine(url) if isinstance(url, str) else url
        self.metadata = MetaData(schema="raw")
        self.feeds = {feed: _feed_table(self.metadata, registry.latest(feed)) for feed in registry.feeds}

        self.batches = Table(
            "ingest_batches",
            self.metadata,
            Column("batch_id", String(36), primary_key=True),
            Column("tenant_id", String(40), nullable=False),
            Column("feed", String(60), nullable=False),
            Column("contract", String(60), nullable=False),
            Column("source_file", String(255), nullable=False),
            Column("file_sha256", String(64), nullable=False),
            Column("rows_received", Integer, nullable=False),
            Column("rows_loaded", Integer, nullable=False),
            Column("rows_quarantined", Integer, nullable=False),
            Column("status", String(30), nullable=False),
            Column("started_at", DateTime, nullable=False),
            Column("finished_at", DateTime),
            Column("report_path", String(500)),
        )

        self.quarantine = Table(
            "quarantine",
            self.metadata,
            Column("batch_id", String(36), nullable=False),
            Column("tenant_id", String(40), nullable=False),
            Column("feed", String(60), nullable=False),
            Column("source_file", String(255), nullable=False),
            Column("source_row", Integer),
            Column("record_key", String(255)),
            Column("record", Text, nullable=False),
            Column("violations", Text, nullable=False),
            Column("quarantined_at", DateTime, nullable=False),
            Column("resolved_batch_id", String(36)),
            Column("resolved_at", DateTime),
        )

        # Device and web-app events land here exactly as uploaded, duplicates
        # and all. De-duplication happens in dbt.
        self.app_events = Table(
            "app_events",
            self.metadata,
            Column("event_id", String(36), nullable=False),
            Column("tenant_id", String(40), nullable=False),
            Column("device_id", String(60), nullable=False),
            Column("device_seq", Integer, nullable=False),
            Column("event_type", String(60), nullable=False),
            Column("occurred_at", DateTime, nullable=False),
            Column("received_at", DateTime, nullable=False),
            Column("upload_id", String(36), nullable=False),
            Column("payload", Text, nullable=False),
        )

    def create_tables(self) -> None:
        self.metadata.create_all(self.engine)

    def already_ingested(self, tenant_id: str, feed: str, sha256: str) -> bool:
        query = select(self.batches.c.batch_id).where(
            self.batches.c.tenant_id == tenant_id,
            self.batches.c.feed == feed,
            self.batches.c.file_sha256 == sha256,
        )
        with self.engine.connect() as conn:
            return conn.execute(query.limit(1)).first() is not None

    def known_keys(self, tenant_id: str, feed: str, field: str) -> set[str]:
        table = self.feeds[feed]
        query = select(table.c[field]).where(table.c.tenant_id == tenant_id).distinct()
        with self.engine.connect() as conn:
            return {str(v) for (v,) in conn.execute(query) if v is not None}

    def held_keys(self, tenant_id: str, feed: str) -> set[str]:
        """Keys of rows in quarantine that nothing has resolved yet."""
        q = self.quarantine
        query = (
            select(q.c.record_key)
            .where(
                q.c.tenant_id == tenant_id,
                q.c.feed == feed,
                q.c.resolved_batch_id.is_(None),
                q.c.record_key.is_not(None),
            )
            .distinct()
        )
        with self.engine.connect() as conn:
            return {v for (v,) in conn.execute(query)}

    def write_batch(
        self,
        batch: BatchRecord,
        contract: Contract,
        rows: list[tuple[int, dict]],
        quarantined: list[QuarantinedRow],
        resolved_keys: list[str],
    ) -> int:
        """Loads a batch in one transaction and returns how many earlier
        quarantined rows it resolved."""
        now = utcnow()
        table = self.feeds[batch.feed]
        resolved = 0
        with self.engine.begin() as conn:
            conn.execute(self.batches.insert(), [batch.__dict__])
            if rows:
                conn.execute(
                    table.insert(),
                    [
                        {
                            **record,
                            "tenant_id": batch.tenant_id,
                            "_batch_id": batch.batch_id,
                            "_source_file": batch.source_file,
                            "_source_row": source_row,
                            "_contract_version": contract.version,
                            "_loaded_at": now,
                        }
                        for source_row, record in rows
                    ],
                )
            if quarantined:
                conn.execute(
                    self.quarantine.insert(),
                    [
                        {
                            "batch_id": batch.batch_id,
                            "tenant_id": batch.tenant_id,
                            "feed": batch.feed,
                            "source_file": batch.source_file,
                            "source_row": q.source_row,
                            "record_key": q.record_key,
                            "record": json.dumps(q.record, default=str, ensure_ascii=False),
                            "violations": json.dumps(q.violations, default=str, ensure_ascii=False),
                            "quarantined_at": now,
                        }
                        for q in quarantined
                    ],
                )
            for start in range(0, len(resolved_keys), 1000):
                chunk = resolved_keys[start : start + 1000]
                result = conn.execute(
                    update(self.quarantine)
                    .where(
                        and_(
                            self.quarantine.c.tenant_id == batch.tenant_id,
                            self.quarantine.c.feed == batch.feed,
                            self.quarantine.c.resolved_batch_id.is_(None),
                            self.quarantine.c.batch_id != batch.batch_id,
                            self.quarantine.c.record_key.in_(chunk),
                        )
                    )
                    .values(resolved_batch_id=batch.batch_id, resolved_at=now)
                )
                resolved += result.rowcount
        return resolved

    def append_events(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self.engine.begin() as conn:
            conn.execute(self.app_events.insert(), rows)
        return len(rows)

    def open_quarantine(self, tenant_id: str | None = None) -> list[dict]:
        q = self.quarantine
        query = select(q).where(q.c.resolved_batch_id.is_(None)).order_by(q.c.quarantined_at)
        if tenant_id:
            query = query.where(q.c.tenant_id == tenant_id)
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(query)]
