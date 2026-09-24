-- Same inferred-member approach as dim_building.

with reported as (

    select * from {{ ref('stg_raw__assets') }}

),

referenced as (

    select
        tenant_id,
        asset_tag,
        max(building_code) as building_code
    from {{ ref('int_app_events_deduplicated') }}
    where asset_tag is not null
    group by 1, 2

),

inferred as (

    select referenced.*
    from referenced
    left join reported
        on
            referenced.tenant_id = reported.tenant_id
            and referenced.asset_tag = reported.asset_tag
    where reported.asset_tag is null

),

combined as (

    select
        tenant_id,
        asset_tag,
        asset_name,
        asset_category,
        asset_status,
        building_code,
        purchased_on,
        purchase_cost,
        false as is_inferred
    from reported

    union all

    select
        tenant_id,
        asset_tag,
        'Unknown asset ' || asset_tag as asset_name,
        'unknown' as asset_category,
        'unknown' as asset_status,
        building_code,
        cast(null as date) as purchased_on,
        cast(null as {{ dbt.type_numeric() }}) as purchase_cost,
        true as is_inferred
    from inferred

)

select
    {{ dbt_utils.generate_surrogate_key(['combined.tenant_id', 'combined.asset_tag']) }} as asset_key,
    {{ dbt_utils.generate_surrogate_key(['combined.tenant_id', 'combined.building_code']) }} as building_key,
    combined.*
from combined
inner join {{ ref('dim_tenant') }} as tenants
    on combined.tenant_id = tenants.tenant_id
