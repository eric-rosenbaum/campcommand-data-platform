# 5. Inferred members for late-arriving dimensions

## Context

Events reference buildings, assets and staff by code. The camp's lists
arrive separately, sometimes after the events, sometimes with the row
in question sitting in quarantine. Dropping those facts loses real work.
Nulling the key hides where the work happened.

## Decision

Surrogate keys are a hash of (tenant, natural key), so a fact can compute
its key without looking the dimension up. Each dimension unions the rows the
camp reported with any codes that facts reference but the camp hasn't
reported, marked `is_inferred` with placeholder attributes. When the real row
arrives, it replaces the inferred one under the same key.

## Consequences

- Facts never need updating when a dimension row shows up late.
- Relationship tests between facts and dimensions always hold.
- Reports can filter or flag `is_inferred`. The count of inferred members is
  also a data quality signal: a code that stays inferred for weeks is
  probably a typo on a device.
