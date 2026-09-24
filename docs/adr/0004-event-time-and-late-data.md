# 4. Event time, reopened windows, rebuilt snapshots

## Context

Events arrive late and out of order. A work order's "completed" can land
before its "started"; a phone that was offline for four days uploads a
week's worth of checks at once. Reports by arrival date would move activity
into the wrong days. Patching aggregates in place would make the numbers
depend on arrival order.

## Decision

- Facts are dated by `event_at`, in the camp's local time zone for daily
  reporting. Device clocks aren't trusted past the upload time:
  `least(occurred_at, received_at)`, flagged when it applies.
- `rpt_maintenance_daily` is incremental by (camp, day). Each run finds the
  days touched by newly loaded events, and each of those days is recomputed
  from scratch and replaced (`delete+insert`). Days with nothing new aren't
  touched.
- `fct_work_orders` is an accumulating snapshot. Any work order with a new
  event is rebuilt from all of its events. Status is the latest event by
  event time, tie-broken by device sequence.

## Consequences

- A late event lands in the right day and the right work order, however late
  it is.
- Cost scales with how many days and work orders a run touches, not with
  history.
- A work order whose "opened" event hasn't arrived yet has no building or
  priority. It's flagged `is_missing_open_event` rather than guessed at.
