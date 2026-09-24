{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='event_id',
        tags=['events'],
    )
}}

with checks as (

    select * from {{ ref('int_app_events_deduplicated') }} as events
    where
        events.event_type = 'waterfront.check_logged'
        {% if is_incremental() %}
            and events._loaded_at > (select max(existing._loaded_at) from {{ this }} as existing)
        {% endif %}

),

tenants as (

    select * from {{ ref('dim_tenant') }}

)

select
    checks.event_id,
    checks.tenant_id,
    checks.check_id,
    {{ dbt_utils.generate_surrogate_key(['checks.tenant_id', 'checks.building_code']) }} as building_key,
    {{ dbt_utils.generate_surrogate_key(['checks.tenant_id', 'checks.staff_code']) }} as staff_key,
    checks.event_at as checked_at,
    cast({{ from_utc('checks.event_at', 'tenants.timezone') }} as date) as checked_date_local,
    checks.chlorine_ppm,
    checks.ph,
    checks.water_temp_f,
    checks.chlorine_ppm is not null as is_pool,
    -- Health-code ranges: pools 1-4 ppm free chlorine and pH 7.2-7.8; open
    -- water only has a pH check.
    case
        when checks.chlorine_ppm is not null
            then checks.chlorine_ppm < 1.0 or checks.chlorine_ppm > 4.0 or checks.ph < 7.2 or checks.ph > 7.8
        else checks.ph < 6.5 or checks.ph > 9.0
    end as is_out_of_range,
    checks.device_id,
    checks.arrival_lag_minutes,
    checks._loaded_at
from checks
inner join tenants
    on checks.tenant_id = tenants.tenant_id
