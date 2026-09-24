-- Onboarding health per camp and feed: what they've sent, what loaded, and
-- what's still waiting on them to fix.

with batches as (

    select * from {{ ref('stg_raw__ingest_batches') }}

),

quarantine as (

    select * from {{ ref('stg_raw__quarantine') }}

),

batch_totals as (

    select
        tenant_id,
        feed,
        count(*) as batches,
        sum(case when batch_status = 'rejected' then 1 else 0 end) as files_rejected,
        sum(rows_received) as rows_received,
        sum(rows_loaded) as rows_loaded,
        sum(rows_quarantined) as rows_quarantined,
        max(finished_at) as last_batch_at
    from batches
    group by 1, 2

),

quarantine_totals as (

    select
        tenant_id,
        feed,
        sum(case when is_resolved then 1 else 0 end) as rows_resolved,
        sum(case when not is_resolved then 1 else 0 end) as rows_open,
        min(case when not is_resolved then quarantined_at end) as oldest_open_since
    from quarantine
    group by 1, 2

)

select
    batch_totals.tenant_id,
    tenants.camp_name,
    batch_totals.feed,
    batch_totals.batches,
    batch_totals.files_rejected,
    batch_totals.rows_received,
    batch_totals.rows_loaded,
    batch_totals.rows_quarantined,
    coalesce(quarantine_totals.rows_resolved, 0) as rows_resolved,
    coalesce(quarantine_totals.rows_open, 0) as rows_open,
    quarantine_totals.oldest_open_since,
    batch_totals.last_batch_at
from batch_totals
inner join {{ ref('dim_tenant') }} as tenants
    on batch_totals.tenant_id = tenants.tenant_id
left join quarantine_totals
    on
        batch_totals.tenant_id = quarantine_totals.tenant_id
        and batch_totals.feed = quarantine_totals.feed
