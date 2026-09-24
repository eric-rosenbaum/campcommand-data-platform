# 1. Quarantine bad rows, not whole files

## Context

Camps send reference data (buildings, assets, staff) and weekly store
exports from spreadsheets they maintain by hand. A typical first file has a
handful of problems in a few hundred rows. Rejecting the whole file for one
bad date means nothing loads, and the camp waits on us to explain what's wrong.

## Decision

Validate every row against the feed's contract. Rows that pass load; rows
that don't go to `raw.quarantine` with every problem found, and the client
gets a report in their own column names plus a CSV of just those rows with a
note on each.

The exception is a missing required column. That's a file-shape problem:
every row would fail the same way, so the file is rejected as a whole and the
report says so once, instead of listing 1,400 identical errors.

When a later batch loads a row with the same key as a quarantined row, the
quarantined row is marked resolved by that batch. Camps can send the whole
file again rather than a patch; nothing is duplicated, because raw is
append-only and staging keeps the latest version per key.

## Consequences

- Most of a file is usable the day it arrives.
- Fixing data becomes the camp's job, with a clear list, instead of ours.
  Nobody on our side edits client data by hand.
- A row with no usable key (a blank asset tag) can never be matched to a
  resend and stays open until someone closes it. That's rare, and
  `mon_ingestion_quality` shows it.
- A reference to a quarantined row (an asset in a building that was held
  back) is reported as waiting on the other fix, not as a bad code.
