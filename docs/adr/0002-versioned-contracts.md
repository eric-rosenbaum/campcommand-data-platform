# 2. Versioned contracts with forward upgrades

## Context

Feeds change. Assets needed a category and status so work orders could be
rolled up by system, and `purchase_price` was renamed. Camps update their
exports on their own schedule, some in weeks, some next season.

## Decision

Each feed version is a YAML file. A client config pins a version
(`assets@1`). Rows are validated against the pinned version, then upgraded to
the latest shape with the rules the newer version declares
(`upgrade_from: {1: {rename: ..., defaults: ...}}`) before they're written.
Raw tables always have the latest shape and record `_contract_version`.

## Consequences

- dbt only ever sees one shape per feed.
- Old versions can't be dropped until no client pins them. The client
  config tests make that visible.
- Primary keys have to stay the same across versions, which a unit test
  enforces, because quarantine resolution matches on them.
- Defaults are a judgement call (`category: other`). The `_contract_version`
  column makes upgraded rows easy to find if that ever matters.
