select
    tenant_id,
    camp_name,
    country,
    region,
    timezone,
    onboarded_on
from {{ ref('tenants') }}
