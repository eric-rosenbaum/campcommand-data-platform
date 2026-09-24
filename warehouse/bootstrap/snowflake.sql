-- One-time setup for the Snowflake account. Run as ACCOUNTADMIN (or split
-- between SYSADMIN / SECURITYADMIN / USERADMIN if the account is set up that
-- way). Service users authenticate with key pairs; set RSA_PUBLIC_KEY on
-- each after running this.

use role accountadmin;

create warehouse if not exists loading
    warehouse_size = xsmall auto_suspend = 60 auto_resume = true initially_suspended = true;
create warehouse if not exists transforming
    warehouse_size = xsmall auto_suspend = 60 auto_resume = true initially_suspended = true;
create warehouse if not exists reporting
    warehouse_size = xsmall auto_suspend = 60 auto_resume = true initially_suspended = true;

create database if not exists campcommand;
create schema if not exists campcommand.raw;

create role if not exists loader;
create role if not exists transformer;
create role if not exists platform_admin;
create role if not exists tenant_reader;
create role if not exists tall_pines_reader;
create role if not exists lakeview_reader;
create role if not exists chene_rouge_reader;

grant role tenant_reader to role tall_pines_reader;
grant role tenant_reader to role lakeview_reader;
grant role tenant_reader to role chene_rouge_reader;
grant role loader to role sysadmin;
grant role transformer to role sysadmin;
grant role platform_admin to role sysadmin;

grant usage on warehouse loading to role loader;
grant usage on warehouse transforming to role transformer;
grant usage on warehouse reporting to role platform_admin;
grant usage on warehouse reporting to role tenant_reader;

grant usage on database campcommand to role loader;
grant usage, create table on schema campcommand.raw to role loader;

grant usage, create schema on database campcommand to role transformer;
grant usage on schema campcommand.raw to role transformer;
grant select on all tables in schema campcommand.raw to role transformer;
grant select on future tables in schema campcommand.raw to role transformer;

-- No policy grants needed: dbt creates the security schema, so transformer
-- owns the tenant_isolation row access policy and every table it attaches
-- it to.

grant usage on database campcommand to role platform_admin;
grant usage on database campcommand to role tenant_reader;

create user if not exists svc_campcommand_loader
    default_role = loader default_warehouse = loading type = service;
create user if not exists svc_campcommand_dbt
    default_role = transformer default_warehouse = transforming type = service;
grant role loader to user svc_campcommand_loader;
grant role transformer to user svc_campcommand_dbt;
