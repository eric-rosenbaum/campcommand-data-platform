{{ config(meta={'tenant_scoped': false}) }}

with spine as (

    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2024-01-01' as date)",
        end_date="cast(" ~ dbt.dateadd('year', 2, 'current_date') ~ " as date)"
    ) }}

)

select
    cast(date_day as date) as date_day,
    extract(year from date_day) as year,
    extract(month from date_day) as month,
    extract(dow from date_day) as day_of_week,
    extract(dow from date_day) in (0, 6) as is_weekend
from spine
