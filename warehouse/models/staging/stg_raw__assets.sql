with latest as (
    {{ latest_per_key(source('raw', 'assets'), ['asset_tag']) }}
)

select
    tenant_id,
    asset_tag,
    asset_name,
    category as asset_category,
    building_code,
    purchased_on,
    purchase_cost,
    status as asset_status,
    _contract_version as contract_version,
    _loaded_at as loaded_at
from latest
