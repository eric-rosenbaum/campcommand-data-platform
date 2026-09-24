{{
    config(
        materialized='incremental',
        incremental_strategy='append',
        tags=['events'],
    )
}}

-- Exactly one row per event_id, no matter how many times it was uploaded or
-- in what order the uploads landed.
--
-- The first copy received wins. On an incremental run that means: take new
-- uploads (with some lookback in case an upload landed slightly out of
-- received_at order), keep the earliest copy of each event within them, and
-- skip any event already in the table. A full refresh applies the same rule
-- to all of raw, so the two always agree (tests/integration/test_event_reconciliation.py).

with uploaded as (

    select * from {{ ref('stg_raw__app_events') }}
    {% if is_incremental() %}
        where received_at >= (
                select {{ dbt.dateadd('day', -var('event_lookback_days'), 'max(received_at)') }}
                from {{ this }}
            )
    {% endif %}

),

ranked as (

    select
        *,
        row_number() over (
            partition by event_id
            order by received_at, upload_id
        ) as copy_number
    from uploaded

)

select
    ranked.event_id,
    ranked.tenant_id,
    ranked.device_id,
    ranked.device_seq,
    ranked.event_type,
    ranked.event_entity,
    ranked.event_action,
    ranked.device_occurred_at,
    ranked.received_at,
    ranked.event_at,
    ranked.is_clock_corrected,
    {{ dbt.datediff('ranked.event_at', 'ranked.received_at', 'minute') }} as arrival_lag_minutes,
    ranked.work_order_id,
    ranked.check_id,
    ranked.building_code,
    ranked.asset_tag,
    ranked.staff_code,
    ranked.reported_by_staff_code,
    ranked.category,
    ranked.priority,
    ranked.labor_minutes,
    ranked.parts_cost,
    ranked.chlorine_ppm,
    ranked.ph,
    ranked.water_temp_f,
    {{ run_timestamp() }} as _loaded_at
from ranked
where
    ranked.copy_number = 1
    {% if is_incremental() %}
        and not exists (
            select 1
            from {{ this }} as existing
            where existing.event_id = ranked.event_id
        )
    {% endif %}
