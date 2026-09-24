{#
    The handful of things that differ between Snowflake (production) and
    Postgres (local and CI). Everything else in the project sticks to SQL
    both accept, plus dbt's own cross-database macros.

    All timestamps in the warehouse are naive UTC.
#}

{% macro json_text(column, key) -%}
    {{ return(adapter.dispatch('json_text')(column, key)) }}
{%- endmacro %}

{% macro postgres__json_text(column, key) -%}
    ({{ column }}::jsonb ->> '{{ key }}')
{%- endmacro %}

{% macro snowflake__json_text(column, key) -%}
    strip_null_value(parse_json({{ column }}):"{{ key }}")::varchar
{%- endmacro %}


{% macro from_utc(column, timezone) -%}
    {{ return(adapter.dispatch('from_utc')(column, timezone)) }}
{%- endmacro %}

{% macro postgres__from_utc(column, timezone) -%}
    (({{ column }} at time zone 'UTC') at time zone {{ timezone }})
{%- endmacro %}

{% macro snowflake__from_utc(column, timezone) -%}
    convert_timezone('UTC', {{ timezone }}, {{ column }})
{%- endmacro %}


{% macro utc_now() -%}
    {{ return(adapter.dispatch('utc_now')()) }}
{%- endmacro %}

{% macro postgres__utc_now() -%}
    (now() at time zone 'UTC')
{%- endmacro %}

{% macro snowflake__utc_now() -%}
    sysdate()
{%- endmacro %}


{# The same value for every model in an invocation, so a downstream
   incremental model can ask "what did upstream add in this run?" #}
{% macro run_timestamp() -%}
    cast('{{ run_started_at.strftime("%Y-%m-%d %H:%M:%S.%f") }}' as {{ dbt.type_timestamp() }})
{%- endmacro %}
