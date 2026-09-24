# 6. Shared tables with row-level policies, not a schema per tenant

## Context

Every camp's staff read reports and must only ever see their own camp.
Options: a schema (or database) per tenant, or shared tables filtered per
reader.

## Decision

Shared tables with a `tenant_id` on every mart, and a row-level policy
applied by a dbt post-hook to every table it builds. The role-to-tenant
mapping is one seed, `tenant_access`, read by both implementations: row level
security policies on Postgres, and a single row access policy on Snowflake.
Shared tables without tenant data (`dim_date`) opt out explicitly.

## Consequences

- One dbt build serves every camp. Adding a camp is a client config, a
  reader role and two seed rows, not new schemas.
- Cross-tenant analysis for us is just a `platform_admin` query.
- The policy is re-applied on every build, because a rebuilt table doesn't
  keep it. That's the post-hook's job, and the integration tests check it by
  logging in as each camp's role.
- Forgetting `tenant_id` on a new mart would fail the post-hook, which
  references the column, rather than leak data.
