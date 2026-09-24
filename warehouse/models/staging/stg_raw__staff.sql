with latest as (
    {{ latest_per_key(source('raw', 'staff'), ['staff_code']) }}
)

select
    tenant_id,
    staff_code,
    first_name,
    last_name,
    role as staff_role,
    email,
    start_date,
    is_active,
    _loaded_at as loaded_at
from latest
