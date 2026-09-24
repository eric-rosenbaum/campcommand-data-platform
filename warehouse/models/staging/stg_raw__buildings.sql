with latest as (
    {{ latest_per_key(source('raw', 'buildings'), ['building_code']) }}
)

select
    tenant_id,
    building_code,
    building_name,
    building_type,
    capacity,
    year_built,
    _contract_version as contract_version,
    _loaded_at as loaded_at
from latest
