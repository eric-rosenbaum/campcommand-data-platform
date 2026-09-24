select
    batch_id,
    tenant_id,
    feed,
    contract,
    source_file,
    status as batch_status,
    rows_received,
    rows_loaded,
    rows_quarantined,
    started_at,
    finished_at,
    report_path
from {{ source('raw', 'ingest_batches') }}
