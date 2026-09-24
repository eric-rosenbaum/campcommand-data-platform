"""Landing for app events.

The sync endpoint accepts whatever a device uploads and appends it to
raw.app_events without trying to de-duplicate. That keeps ingestion
at-least-once and cheap; exactly-once is the warehouse's job (see
int_app_events_deduplicated).
"""

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from campcommand.synthetic.events import Upload
from campcommand.warehouse import Warehouse


def read_uploads(path: Path) -> list[Upload]:
    with path.open(encoding="utf-8") as fh:
        return [Upload.from_json(line) for line in fh if line.strip()]


def write_uploads(path: Path, uploads: Iterable[Upload]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for upload in uploads:
            fh.write(upload.to_json() + "\n")


def deliver(warehouse: Warehouse, uploads: Iterable[Upload], until: datetime | None = None) -> int:
    """Append every upload received up to `until` that isn't already landed."""
    table = warehouse.app_events
    with warehouse.engine.connect() as conn:
        landed = {row[0] for row in conn.execute(select(table.c.upload_id).distinct())}
    rows = []
    for upload in uploads:
        if upload.upload_id in landed or (until and upload.received_at > until):
            continue
        rows.extend(upload.rows())
    return warehouse.append_events(rows)
