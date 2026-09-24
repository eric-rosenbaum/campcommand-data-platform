-- Same inferred-member approach as dim_building.

with reported as (

    select * from {{ ref('stg_raw__staff') }}

),

referenced as (

    select
        tenant_id,
        staff_code
    from {{ ref('int_app_events_deduplicated') }}
    where staff_code is not null

    union

    select
        tenant_id,
        reported_by_staff_code
    from {{ ref('int_app_events_deduplicated') }}
    where reported_by_staff_code is not null

),

inferred as (

    select referenced.*
    from referenced
    left join reported
        on
            referenced.tenant_id = reported.tenant_id
            and referenced.staff_code = reported.staff_code
    where reported.staff_code is null

),

combined as (

    select
        tenant_id,
        staff_code,
        first_name,
        last_name,
        staff_role,
        email,
        start_date,
        is_active,
        false as is_inferred
    from reported

    union all

    select
        tenant_id,
        staff_code,
        cast(null as {{ dbt.type_string() }}) as first_name,
        cast(null as {{ dbt.type_string() }}) as last_name,
        'unknown' as staff_role,
        cast(null as {{ dbt.type_string() }}) as email,
        cast(null as date) as start_date,
        cast(null as boolean) as is_active,
        true as is_inferred
    from inferred

)

select
    {{ dbt_utils.generate_surrogate_key(['combined.tenant_id', 'combined.staff_code']) }} as staff_key,
    combined.*
from combined
inner join {{ ref('dim_tenant') }} as tenants
    on combined.tenant_id = tenants.tenant_id
