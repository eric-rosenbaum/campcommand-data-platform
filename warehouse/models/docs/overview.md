{% docs __overview__ %}
# CampCommand warehouse

Multi-tenant warehouse for camp operations: maintenance work orders,
waterfront safety checks and camp store sales, for every camp on the
platform. Production runs on Snowflake; this project also runs on Postgres.

- **Reference data and store sales** come in through the onboarding
  framework, already validated against versioned contracts. Staging keeps the
  latest version of each row.
- **App events** land exactly as devices uploaded them, duplicates and all.
  `int_app_events_deduplicated` makes them exactly-once.
- **Marts** share conformed `dim_building`, `dim_asset` and `dim_staff`
  dimensions, with inferred members for codes that arrive before their
  reference rows.
- Every mart is **tenant isolated**: each camp's reader role can only see
  its own rows.

All data here is synthetic.
{% enddocs %}
