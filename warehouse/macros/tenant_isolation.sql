{#
    Every mart and monitoring table has a tenant_id column. These macros make
    sure a camp's reader role can only ever see its own rows, on either
    warehouse:

      Postgres   row level security policy on each table
      Snowflake  one row access policy, attached to each table

    Both read security.tenant_access (a seed), so the rule lives in one place.
    platform_admin sees everything.
#}

{% macro apply_tenant_isolation() -%}
    {# Shared, tenant-less tables like dim_date opt out with
       config(meta={'tenant_scoped': false}). #}
    {% if model.config.meta.get('tenant_scoped', true) %}
        {{ return(adapter.dispatch('apply_tenant_isolation')()) }}
    {% endif %}
{%- endmacro %}

{% macro postgres__apply_tenant_isolation() -%}
    alter table {{ this }} enable row level security;
    drop policy if exists tenant_isolation on {{ this }};
    create policy tenant_isolation on {{ this }}
        for select
        using (
            pg_has_role(current_user, 'platform_admin', 'member')
            or tenant_id in (
                select access.tenant_id
                from {{ ref('tenant_access') }} as access
                where access.role_name = current_user
            )
        );
{%- endmacro %}

{% macro snowflake__apply_tenant_isolation() -%}
    {# A table rebuilt with create-or-replace loses its policy, and an
       incremental table still has it, so always drop and re-add. #}
    {% do run_query("alter table " ~ this ~ " drop all row access policies") %}
    alter table {{ this }}
        add row access policy {{ tenant_policy_name() }} on (tenant_id)
{%- endmacro %}


{% macro create_tenant_policy() -%}
    {{ return(adapter.dispatch('create_tenant_policy')()) }}
{%- endmacro %}

{% macro default__create_tenant_policy() -%}
{%- endmacro %}

{# Runs as the post-hook of the tenant_access seed, so `this` is the
   mapping table. #}
{% macro snowflake__create_tenant_policy() -%}
    create row access policy if not exists {{ tenant_policy_name() }}
        as (row_tenant_id varchar) returns boolean ->
            is_role_in_session('PLATFORM_ADMIN')
            or exists (
                select 1
                from {{ this }} as access
                where upper(access.role_name) = current_role()
                    and access.tenant_id = row_tenant_id
            )
{%- endmacro %}

{% macro tenant_policy_name() -%}
    {{ target.database }}.security.tenant_isolation
{%- endmacro %}


{% macro grant_tenant_access(schemas) -%}
    {{ return(adapter.dispatch('grant_tenant_access')(schemas)) }}
{%- endmacro %}

{% macro postgres__grant_tenant_access(schemas) -%}
    {% for schema in schemas if schema in ['security', 'core', 'reporting', 'monitoring'] %}
        grant usage on schema {{ schema }} to platform_admin, tenant_reader;
    {% endfor %}
{%- endmacro %}

{% macro snowflake__grant_tenant_access(schemas) -%}
    {% for schema in schemas if schema | lower in ['security', 'core', 'reporting', 'monitoring'] %}
        {% do run_query("grant usage on schema " ~ target.database ~ "." ~ schema ~ " to role platform_admin") %}
        {% do run_query("grant usage on schema " ~ target.database ~ "." ~ schema ~ " to role tenant_reader") %}
    {% endfor %}
{%- endmacro %}
