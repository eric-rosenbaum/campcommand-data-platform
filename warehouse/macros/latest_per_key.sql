{#
    Clients resend their full reference lists, so raw tables hold every
    version of every row. Keep the most recently loaded one.
#}
{% macro latest_per_key(relation, key_columns) %}
    select *
    from (
        select
            *,
            row_number() over (
                partition by tenant_id, {{ key_columns | join(', ') }}
                order by _loaded_at desc, _source_row desc
            ) as _version_rank
        from {{ relation }}
    ) as versions
    where _version_rank = 1
{% endmacro %}
