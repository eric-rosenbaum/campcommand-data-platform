-- Local development only. Mirrors bootstrap/snowflake.sql closely enough that
-- the dbt project runs unchanged against either.

do $$
declare
    r record;
begin
    for r in
        select * from (values
            ('loader', true, 'loader'),
            ('transformer', true, 'transformer'),
            ('platform_admin', false, null),
            ('tenant_reader', false, null),
            ('tall_pines_reader', true, 'reader'),
            ('lakeview_reader', true, 'reader'),
            ('chene_rouge_reader', true, 'reader')
        ) as v (name, can_login, password)
    loop
        if not exists (select from pg_roles where rolname = r.name) then
            if r.can_login then
                execute format('create role %I login password %L', r.name, r.password);
            else
                execute format('create role %I nologin', r.name);
            end if;
        end if;
    end loop;
end
$$;

grant tenant_reader to tall_pines_reader, lakeview_reader, chene_rouge_reader;

create schema if not exists raw authorization loader;
grant usage on schema raw to transformer;
alter default privileges for role loader in schema raw grant select on tables to transformer;

do $$
begin
    execute format('grant create on database %I to transformer', current_database());
end
$$;
