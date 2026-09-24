-- Conformed building dimension shared by work orders, waterfront checks and
-- store sales.
--
-- Events can reference a building before the camp's building list includes
-- it (or while that row is sitting in quarantine). Those get an inferred
-- member so the fact rows still join. The key is a hash of the natural key,
-- so when the real row arrives it replaces the inferred one under the same
-- key and nothing in the facts has to change.

with reported as (

    select * from {{ ref('stg_raw__buildings') }}

),

referenced as (

    select distinct
        tenant_id,
        building_code
    from {{ ref('int_app_events_deduplicated') }}
    where building_code is not null

),

inferred as (

    select
        referenced.tenant_id,
        referenced.building_code
    from referenced
    left join reported
        on
            referenced.tenant_id = reported.tenant_id
            and referenced.building_code = reported.building_code
    where reported.building_code is null

),

combined as (

    select
        tenant_id,
        building_code,
        building_name,
        building_type,
        capacity,
        year_built,
        false as is_inferred
    from reported

    union all

    select
        tenant_id,
        building_code,
        'Unknown building ' || building_code as building_name,
        'unknown' as building_type,
        cast(null as {{ dbt.type_int() }}) as capacity,
        cast(null as {{ dbt.type_int() }}) as year_built,
        true as is_inferred
    from inferred

)

select
    {{ dbt_utils.generate_surrogate_key(['combined.tenant_id', 'combined.building_code']) }} as building_key,
    combined.*
from combined
inner join {{ ref('dim_tenant') }} as tenants
    on combined.tenant_id = tenants.tenant_id
