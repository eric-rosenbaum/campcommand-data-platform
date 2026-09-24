{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='event_id',
        tags=['events'],
    )
}}

-- Event-grain fact for work orders: one row per lifecycle event. Keyed and
-- dated by when the event happened, not when it arrived.

with events as (

    select * from {{ ref('int_work_order_events') }} as work_order_events
    {% if is_incremental() %}
        where work_order_events._loaded_at > (select max(existing._loaded_at) from {{ this }} as existing)
    {% endif %}

),

tenants as (

    select * from {{ ref('dim_tenant') }}

)

select
    events.event_id,
    events.tenant_id,
    {{ dbt_utils.generate_surrogate_key(['events.tenant_id', 'events.work_order_id']) }} as work_order_key,
    events.work_order_id,
    events.event_action,
    events.event_at,
    cast({{ from_utc('events.event_at', 'tenants.timezone') }} as date) as event_date_local,
    case when events.building_code is not null
            then {{ dbt_utils.generate_surrogate_key(['events.tenant_id', 'events.building_code']) }}
    end as building_key,
    case when events.asset_tag is not null
            then {{ dbt_utils.generate_surrogate_key(['events.tenant_id', 'events.asset_tag']) }}
    end as asset_key,
    case when coalesce(events.staff_code, events.reported_by_staff_code) is not null
            then {{ dbt_utils.generate_surrogate_key(
            ['events.tenant_id', 'coalesce(events.staff_code, events.reported_by_staff_code)']
        ) }}
    end as staff_key,
    events.category,
    events.priority,
    events.labor_minutes,
    events.parts_cost,
    events.device_id,
    events.device_seq,
    events.received_at,
    events.arrival_lag_minutes,
    events.arrival_lag_minutes > {{ var('late_arrival_minutes') }} as is_late_arrival,
    events.is_clock_corrected,
    events._loaded_at
from events
inner join tenants
    on events.tenant_id = tenants.tenant_id
