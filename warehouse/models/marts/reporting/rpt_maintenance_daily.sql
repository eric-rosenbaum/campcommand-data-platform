{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key=['tenant_id', 'activity_date'],
        tags=['events'],
    )
}}

-- Daily maintenance activity per building, in each camp's local time.
--
-- Windows are by event date. A late event reopens the day it belongs to:
-- every (tenant, day) touched by newly arrived events is recomputed in full
-- and replaced. Days nothing new arrived for are left alone.

with events as (

    select * from {{ ref('fct_maintenance_events') }}

),

{% if is_incremental() %}
    touched_days as (

        select distinct
            tenant_id,
            event_date_local
        from events
        where events._loaded_at > (select max(existing._refreshed_at) from {{ this }} as existing)

    ),
{% endif %}

in_scope as (

    select events.*
    from events
    {% if is_incremental() %}
        inner join touched_days
            on
                events.tenant_id = touched_days.tenant_id
                and events.event_date_local = touched_days.event_date_local
    {% endif %}

)

select
    tenant_id,
    event_date_local as activity_date,
    building_key,
    sum(case when event_action = 'opened' then 1 else 0 end) as work_orders_opened,
    sum(case when event_action = 'completed' then 1 else 0 end) as work_orders_completed,
    sum(case when event_action = 'opened' and priority = 'urgent' then 1 else 0 end) as urgent_opened,
    coalesce(sum(labor_minutes), 0) as labor_minutes,
    coalesce(sum(parts_cost), 0) as parts_cost,
    sum(case when is_late_arrival then 1 else 0 end) as late_events,
    {{ run_timestamp() }} as _refreshed_at
from in_scope
group by 1, 2, 3
