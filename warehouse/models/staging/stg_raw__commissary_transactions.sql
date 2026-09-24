-- Weekly store exports overlap by a day, so the same line arrives twice.
-- (tenant, transaction, line) is the natural key.

with latest as (
    {{ latest_per_key(source('raw', 'commissary_transactions'), ['transaction_id', 'line_number']) }}
)

select
    tenant_id,
    transaction_id,
    line_number,
    sold_at,
    store_building_code,
    cashier_staff_code,
    sku,
    item_name,
    item_category,
    quantity,
    unit_price,
    payment_method,
    _loaded_at as loaded_at
from latest
