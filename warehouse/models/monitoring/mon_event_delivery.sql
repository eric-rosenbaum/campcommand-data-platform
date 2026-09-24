-- How events are actually arriving, per device per day. The things to watch:
-- duplicate uploads (retries), late arrivals (devices offline), and clock
-- corrections (a device with the wrong time).

with copies as (

    select
        tenant_id,
        device_id,
        cast(received_at as date) as received_date,
        -- A retry can land days after the original, so number copies across
        -- all of raw, not within a day.
        row_number() over (
            partition by event_id
            order by received_at, upload_id
        ) as copy_number
    from {{ ref('stg_raw__app_events') }}

),

uploaded as (

    select
        tenant_id,
        device_id,
        received_date,
        count(*) as copies_uploaded,
        sum(case when copy_number = 1 then 1 else 0 end) as new_events,
        sum(case when copy_number > 1 then 1 else 0 end) as duplicate_copies
    from copies
    group by 1, 2, 3

),

kept as (

    select
        tenant_id,
        device_id,
        cast(received_at as date) as received_date,
        sum(
            case when arrival_lag_minutes > {{ var('late_arrival_minutes') }} then 1 else 0 end
        ) as late_events,
        max(arrival_lag_minutes) as max_arrival_lag_minutes,
        sum(case when is_clock_corrected then 1 else 0 end) as clock_corrections
    from {{ ref('int_app_events_deduplicated') }}
    group by 1, 2, 3

)

select
    uploaded.tenant_id,
    uploaded.device_id,
    uploaded.received_date,
    uploaded.copies_uploaded,
    uploaded.new_events,
    uploaded.duplicate_copies,
    coalesce(kept.late_events, 0) as late_events,
    kept.max_arrival_lag_minutes,
    coalesce(kept.clock_corrections, 0) as clock_corrections
from uploaded
left join kept
    on
        uploaded.tenant_id = kept.tenant_id
        and uploaded.device_id = kept.device_id
        and uploaded.received_date = kept.received_date
