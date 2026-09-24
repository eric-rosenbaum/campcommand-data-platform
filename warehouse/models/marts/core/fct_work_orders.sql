{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='work_order_key',
        tags=['events'],
    )
}}

-- Accumulating snapshot: one row per work order with a timestamp for each
-- milestone. Events arrive in any order and sometimes days late, so a work
-- order is never patched in place. Whenever anything new arrives for it,
-- its row is rebuilt from all of its events. The result is the same whatever
-- order the events came in.

with touched as (

    select distinct maintenance_events.work_order_key
    from {{ ref('fct_maintenance_events') }} as maintenance_events
    {% if is_incremental() %}
        where maintenance_events._loaded_at > (select max(existing._loaded_at) from {{ this }} as existing)
    {% endif %}

),

events as (

    select events.*
    from {{ ref('fct_maintenance_events') }} as events
    inner join touched
        on events.work_order_key = touched.work_order_key

),

ordered as (

    select
        *,
        row_number() over (
            partition by work_order_key
            order by event_at desc, device_seq desc, event_id desc
        ) as recency
    from events

),

milestones as (

    select
        work_order_key,
        min(tenant_id) as tenant_id,
        min(work_order_id) as work_order_id,
        min(case when event_action = 'opened' then event_at end) as opened_at,
        min(case when event_action = 'assigned' then event_at end) as assigned_at,
        min(case when event_action = 'started' then event_at end) as started_at,
        max(case when event_action = 'completed' then event_at end) as completed_at,
        max(case when event_action = 'opened' then building_key end) as building_key,
        max(case when event_action = 'opened' then asset_key end) as asset_key,
        max(case when event_action = 'opened' then category end) as category,
        max(case when event_action = 'opened' then priority end) as priority,
        max(case when event_action = 'opened' then staff_key end) as reported_by_staff_key,
        max(case when event_action = 'assigned' then staff_key end) as assigned_staff_key,
        sum(labor_minutes) as labor_minutes,
        sum(parts_cost) as parts_cost,
        count(*) as event_count,
        sum(case when is_late_arrival then 1 else 0 end) as late_event_count,
        max(event_at) as last_event_at,
        max(_loaded_at) as _loaded_at
    from events
    group by 1

),

latest as (

    select
        work_order_key,
        event_action as latest_action
    from ordered
    where recency = 1

)

select
    milestones.work_order_key,
    milestones.tenant_id,
    milestones.work_order_id,
    milestones.building_key,
    milestones.asset_key,
    milestones.category,
    milestones.priority,
    milestones.reported_by_staff_key,
    milestones.assigned_staff_key,
    case latest.latest_action
        when 'completed' then 'completed'
        when 'started' then 'in_progress'
        when 'assigned' then 'assigned'
        else 'open'
    end as status,
    milestones.opened_at,
    milestones.assigned_at,
    milestones.started_at,
    milestones.completed_at,
    {{ dbt.datediff('milestones.opened_at', 'milestones.assigned_at', 'minute') }} as minutes_to_assign,
    {{ dbt.datediff('milestones.opened_at', 'milestones.completed_at', 'minute') }} as minutes_to_complete,
    milestones.labor_minutes,
    milestones.parts_cost,
    milestones.event_count,
    milestones.late_event_count,
    milestones.opened_at is null as is_missing_open_event,
    milestones.last_event_at,
    milestones._loaded_at
from milestones
inner join latest
    on milestones.work_order_key = latest.work_order_key
