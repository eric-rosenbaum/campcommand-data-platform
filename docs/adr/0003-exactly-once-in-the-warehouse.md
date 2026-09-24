# 3. At-least-once landing, exactly-once in the warehouse

## Context

Devices retry uploads when they don't get a response, sometimes days later.
Deduplicating at the sync endpoint would mean a lookup per event on the
write path, and it would still miss duplicates that arrive through a
different upload.

## Decision

The endpoint appends every upload to `raw.app_events` as is. Each event
carries a UUID generated on the device. `int_app_events_deduplicated` is an
append-only incremental model that, on each run:

1. reads raw events received since the last run, with a lookback of a few days,
2. keeps the first-received copy of each `event_id` in that slice, and
3. skips any `event_id` already in the table.

A full refresh applies the same "first copy wins" rule to all of raw, so an
incremental history and a rebuild always agree.

## Consequences

- Ingest stays cheap and never drops data.
- Raw still has every copy, which is what `mon_event_delivery` reports on.
- The lookback bounds how out of order uploads can land (not how late
  events can be). An event received a month late is still a new
  `received_at`, so it's picked up.
- The equality of incremental and full-refresh output is tested directly,
  with deliveries cut at random points.
