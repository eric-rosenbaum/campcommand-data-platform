"""Client onboarding: landing file -> contract validation -> raw tables,
quarantine, and an error report for the client."""

import hashlib
import logging
import uuid
from dataclasses import dataclass
from graphlib import TopologicalSorter
from pathlib import Path

from campcommand.clients import Client, load_clients
from campcommand.config import Settings
from campcommand.contracts import ContractRegistry
from campcommand.mapping import map_columns
from campcommand.readers import SourceReadError, read_source
from campcommand.reports import write_report
from campcommand.validation import ValidationResult, Violation, validate
from campcommand.warehouse import BatchRecord, QuarantinedRow, Warehouse, utcnow

log = logging.getLogger(__name__)

UNREADABLE = "unreadable"


@dataclass
class BatchResult:
    batch_id: str
    tenant_id: str
    feed: str
    source_file: str
    status: str
    rows_received: int = 0
    rows_loaded: int = 0
    rows_quarantined: int = 0
    rows_resolved: int = 0
    report_path: Path | None = None


def load_order(registry: ContractRegistry) -> list[str]:
    """Feeds ordered so that anything a feed references is loaded first."""
    graph = {feed: {f.references[0] for f in registry.latest(feed).references} for feed in registry.feeds}
    return list(TopologicalSorter(graph).static_order())


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Pipeline:
    def __init__(self, settings: Settings, warehouse: Warehouse | None = None):
        self.settings = settings
        self.registry = ContractRegistry(settings.contracts_dir)
        self.clients: dict[str, Client] = load_clients(settings.clients_dir)
        self.warehouse = warehouse or Warehouse(settings.warehouse_url, self.registry)

    def discover(self, tenant_id: str) -> list[tuple[str, Path]]:
        client = self.clients[tenant_id]
        tenant_dir = self.settings.landing_dir / tenant_id
        found = []
        for feed in load_order(self.registry):
            cfg = client.feeds.get(feed)
            if cfg is None:
                continue
            paths = sorted(tenant_dir.glob(cfg.files), key=lambda p: (p.stat().st_mtime, p.name))
            found.extend((feed, p) for p in paths)
        return found

    def ingest_tenant(self, tenant_id: str) -> list[BatchResult]:
        return [self.ingest_file(tenant_id, feed, path) for feed, path in self.discover(tenant_id)]

    def ingest_file(self, tenant_id: str, feed: str, path: Path) -> BatchResult:
        client = self.clients[tenant_id]
        cfg = client.feeds[feed]
        contract = self.registry.get(cfg.contract)
        sha = sha256_of(path)
        batch_id = str(uuid.uuid4())

        if self.warehouse.already_ingested(tenant_id, feed, sha):
            log.info("skip %s/%s: already ingested", tenant_id, path.name)
            return BatchResult(batch_id, tenant_id, feed, path.name, "skipped")

        started = utcnow()
        try:
            source = read_source(path, cfg.format)
        except SourceReadError as exc:
            result = ValidationResult(
                accepted=[], rejected=[], file_violations=[Violation(UNREADABLE, str(exc))]
            )
            mapped_unmapped: list[str] = []
        else:
            mapped = map_columns(source, cfg)
            mapped_unmapped = mapped.unmapped_columns
            known = {
                f.references: self.warehouse.known_keys(tenant_id, *f.references) for f in contract.references
            }
            # Single-column keys only; that covers every reference today.
            held = {
                f.references: self.warehouse.held_keys(tenant_id, f.references[0])
                for f in contract.references
            }
            result = validate(mapped, contract, cfg.parse, known, held)

        if result.file_violations:
            status = "rejected"
        elif result.rejected:
            status = "loaded_with_errors"
        else:
            status = "loaded"

        rows = (
            [(r.source_row, self.registry.upgrade(r.record, contract)) for r in result.accepted]
            if status != "rejected"
            else []
        )
        quarantined = [
            QuarantinedRow(
                source_row=r.source_row,
                record_key=contract.key_of(r.record),
                record=r.raw,
                violations=[v.__dict__ for v in r.violations or result.file_violations],
            )
            for r in result.rejected
        ]

        batch = BatchRecord(
            batch_id=batch_id,
            tenant_id=tenant_id,
            feed=feed,
            contract=contract.ref,
            source_file=path.name,
            file_sha256=sha,
            rows_received=result.rows_received,
            rows_loaded=len(rows),
            rows_quarantined=len(quarantined),
            status=status,
            started_at=started,
        )
        outcome = BatchResult(
            batch_id,
            tenant_id,
            feed,
            path.name,
            status,
            rows_received=batch.rows_received,
            rows_loaded=batch.rows_loaded,
            rows_quarantined=batch.rows_quarantined,
        )

        if status != "loaded" or mapped_unmapped:
            outcome.report_path = write_report(
                self.settings.reports_dir,
                client,
                contract,
                outcome,
                result,
                unmapped_columns=mapped_unmapped,
            )
            batch.report_path = str(outcome.report_path.relative_to(self.settings.reports_dir))

        batch.finished_at = utcnow()
        resolved_keys = [key for _, rec in rows if (key := contract.key_of(rec)) is not None]
        outcome.rows_resolved = self.warehouse.write_batch(batch, contract, rows, quarantined, resolved_keys)
        log.info(
            "%s/%s: %s (%d loaded, %d quarantined, %d resolved)",
            tenant_id,
            path.name,
            status,
            outcome.rows_loaded,
            outcome.rows_quarantined,
            outcome.rows_resolved,
        )
        return outcome
