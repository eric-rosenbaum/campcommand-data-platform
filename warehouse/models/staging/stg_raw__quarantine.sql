select
    batch_id,
    tenant_id,
    feed,
    source_file,
    source_row,
    record_key,
    quarantined_at,
    resolved_batch_id,
    resolved_at,
    resolved_batch_id is not null as is_resolved
from {{ source('raw', 'quarantine') }}
