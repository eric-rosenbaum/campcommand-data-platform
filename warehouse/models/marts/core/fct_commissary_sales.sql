-- Transaction-line fact for the camp store.

with sales as (

    select * from {{ ref('stg_raw__commissary_transactions') }}

),

tenants as (

    select * from {{ ref('dim_tenant') }}

)

select
    {{ dbt_utils.generate_surrogate_key(['sales.tenant_id', 'sales.transaction_id', 'sales.line_number']) }}
        as sale_line_key,
    sales.tenant_id,
    sales.transaction_id,
    sales.line_number,
    sales.sold_at,
    cast({{ from_utc('sales.sold_at', 'tenants.timezone') }} as date) as sold_date_local,
    {{ dbt_utils.generate_surrogate_key(['sales.tenant_id', 'sales.store_building_code']) }} as building_key,
    case when sales.cashier_staff_code is not null
            then {{ dbt_utils.generate_surrogate_key(['sales.tenant_id', 'sales.cashier_staff_code']) }}
    end as staff_key,
    sales.sku,
    sales.item_name,
    sales.item_category,
    sales.quantity,
    sales.unit_price,
    sales.quantity * sales.unit_price as line_amount,
    sales.payment_method
from sales
inner join tenants
    on sales.tenant_id = tenants.tenant_id
