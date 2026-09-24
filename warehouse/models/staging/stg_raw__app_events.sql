-- One row per uploaded copy of an event. Duplicates are still here; they're
-- removed in int_app_events_deduplicated.

with events as (

    select * from {{ source('raw', 'app_events') }}

)

select
    event_id,
    tenant_id,
    device_id,
    device_seq,
    event_type,
    split_part(event_type, '.', 1) as event_entity,
    split_part(event_type, '.', 2) as event_action,
    occurred_at as device_occurred_at,
    received_at,
    -- A device can't report something before it happened. If its clock says
    -- otherwise the clock is wrong, and the upload time is the best bound we have.
    least(occurred_at, received_at) as event_at,
    occurred_at > received_at as is_clock_corrected,
    upload_id,
    {{ json_text('payload', 'work_order_id') }} as work_order_id,
    {{ json_text('payload', 'check_id') }} as check_id,
    {{ json_text('payload', 'building_code') }} as building_code,
    {{ json_text('payload', 'asset_tag') }} as asset_tag,
    {{ json_text('payload', 'staff_code') }} as staff_code,
    {{ json_text('payload', 'reported_by') }} as reported_by_staff_code,
    {{ json_text('payload', 'category') }} as category,
    {{ json_text('payload', 'priority') }} as priority,
    cast({{ json_text('payload', 'labor_minutes') }} as {{ dbt.type_int() }}) as labor_minutes,
    cast({{ json_text('payload', 'parts_cost') }} as {{ dbt.type_numeric() }}) as parts_cost,
    cast({{ json_text('payload', 'chlorine_ppm') }} as {{ dbt.type_numeric() }}) as chlorine_ppm,
    cast({{ json_text('payload', 'ph') }} as {{ dbt.type_numeric() }}) as ph,
    cast({{ json_text('payload', 'water_temp_f') }} as {{ dbt.type_numeric() }}) as water_temp_f
from events
