-- Work orders not yet completed, with how long each has been waiting.

with open_orders as (

    select * from {{ ref('fct_work_orders') }}
    where status != 'completed'

),

buildings as (

    select * from {{ ref('dim_building') }}

)

select
    open_orders.tenant_id,
    open_orders.work_order_id,
    open_orders.status,
    open_orders.priority,
    open_orders.category,
    buildings.building_name,
    buildings.building_type,
    open_orders.opened_at,
    {{ dbt.datediff('open_orders.opened_at', 'open_orders.last_event_at', 'hour') }} as hours_open_at_last_activity,
    open_orders.is_missing_open_event
from open_orders
left join buildings
    on open_orders.building_key = buildings.building_key
