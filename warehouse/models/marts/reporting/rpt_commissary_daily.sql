select
    tenant_id,
    sold_date_local,
    item_category,
    count(distinct transaction_id) as transactions,
    sum(quantity) as units,
    sum(line_amount) as revenue,
    sum(case when payment_method = 'camper_account' then line_amount else 0 end) as camper_account_revenue
from {{ ref('fct_commissary_sales') }}
group by 1, 2, 3
