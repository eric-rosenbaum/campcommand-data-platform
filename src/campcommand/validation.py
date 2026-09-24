"""Check mapped rows against a contract.

A row either passes every rule and comes out typed, or it's rejected with
one Violation per problem. Messages are written for the camp's staff, using
their own column names, since they end up in the client error report.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from campcommand.coercion import CoercionError, ParseOptions, coerce
from campcommand.contracts import Contract, Field
from campcommand.mapping import MappedFile

MISSING_COLUMN = "missing_column"
REQUIRED = "required"
INVALID_TYPE = "invalid_type"
NOT_ALLOWED = "not_allowed"
OUT_OF_RANGE = "out_of_range"
BAD_FORMAT = "bad_format"
DUPLICATE_KEY = "duplicate_key"
UNKNOWN_REFERENCE = "unknown_reference"
HELD_REFERENCE = "held_reference"


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str
    source_row: int | None = None
    field: str | None = None
    column: str | None = None
    value: object = None


@dataclass
class Row:
    source_row: int
    raw: dict[str, object]
    record: dict[str, object] = field(default_factory=dict)
    violations: list[Violation] = field(default_factory=list)


@dataclass
class ValidationResult:
    accepted: list[Row]
    rejected: list[Row]
    file_violations: list[Violation]

    @property
    def rows_received(self) -> int:
        return len(self.accepted) + len(self.rejected)


def validate(
    mapped: MappedFile,
    contract: Contract,
    opts: ParseOptions,
    known_keys: Mapping[tuple[str, str], set[str]],
    held_keys: Mapping[tuple[str, str], set[str]] | None = None,
) -> ValidationResult:
    labels = mapped.labels
    missing = _missing_required_columns(mapped, contract, labels)
    if missing:
        # Without a required column every row would fail the same way. Reject
        # the file as a whole and say so once.
        # Still work out each row's key, so that when the corrected file
        # arrives its rows can close these out.
        rows = []
        for source_row, raw in zip(mapped.row_numbers, mapped.rows, strict=True):
            row = Row(source_row, raw)
            for name in contract.primary_key:
                f = contract.fields[name]
                row.record[name], _ = _check_field(f, raw.get(name), opts, labels, source_row)
            rows.append(row)
        return ValidationResult(accepted=[], rejected=rows, file_violations=missing)

    rows = []
    for source_row, raw in zip(mapped.row_numbers, mapped.rows, strict=True):
        row = Row(source_row, raw)
        for f in contract.fields.values():
            value, violation = _check_field(f, raw.get(f.name), opts, labels, source_row)
            row.record[f.name] = value
            if violation:
                row.violations.append(violation)
        rows.append(row)

    _check_duplicates(rows, contract, labels)
    _check_references(rows, contract, labels, known_keys, held_keys or {})

    return ValidationResult(
        accepted=[r for r in rows if not r.violations],
        rejected=[r for r in rows if r.violations],
        file_violations=[],
    )


def _missing_required_columns(mapped, contract, labels) -> list[Violation]:
    missing_headers = set(mapped.missing_columns)
    return [
        Violation(
            rule=MISSING_COLUMN,
            field=f.name,
            column=labels.get(f.name, f.name),
            message=(
                f"The file has no '{labels.get(f.name, f.name)}' column. "
                f"It's required, so nothing in this file was loaded."
            ),
        )
        for f in contract.fields.values()
        if f.required and (f.name not in labels or labels[f.name] in missing_headers)
    ]


def _check_field(f: Field, raw_value, opts, labels, source_row):
    column = labels.get(f.name, f.name)

    def violation(rule: str, message: str) -> Violation:
        return Violation(rule, message, source_row, f.name, column, raw_value)

    try:
        value = coerce(raw_value, f.type, opts)
    except CoercionError as exc:
        return None, violation(INVALID_TYPE, f"'{raw_value}' in {column}: {exc}.")

    if value is None:
        if f.required:
            return None, violation(REQUIRED, f"{column} is blank, and every row needs one.")
        return None, None

    if f.allowed is not None and value not in f.allowed:
        return None, violation(
            NOT_ALLOWED, f"'{raw_value}' isn't a recognised {column}. Check the spelling or ask us to add it."
        )

    is_number = isinstance(value, int | Decimal) and not isinstance(value, bool)
    if is_number and ((f.min is not None and value < f.min) or (f.max is not None and value > f.max)):
        return None, violation(OUT_OF_RANGE, f"{column} is {raw_value}; {_range_text(f)}.")

    if f.pattern and isinstance(value, str) and not re.fullmatch(f.pattern, value):
        return None, violation(BAD_FORMAT, f"'{raw_value}' doesn't look like a valid {f.display_name}.")

    return value, None


def _check_duplicates(rows: list[Row], contract: Contract, labels) -> None:
    first_seen: dict[str, int] = {}
    key_columns = ", ".join(labels.get(k, k) for k in contract.primary_key)
    for row in rows:
        key = contract.key_of(row.record)
        if key is None or row.violations:
            continue
        if key in first_seen:
            row.violations.append(
                Violation(
                    rule=DUPLICATE_KEY,
                    source_row=row.source_row,
                    field=contract.primary_key[0],
                    column=key_columns,
                    value=key,
                    message=(
                        f"{key_columns} '{key}' already appears on row {first_seen[key]}. "
                        f"We kept row {first_seen[key]}."
                    ),
                )
            )
        else:
            first_seen[key] = row.source_row


def _check_references(rows, contract, labels, known_keys, held_keys) -> None:
    for f in contract.references:
        ref_feed, ref_field = f.references
        known = known_keys.get((ref_feed, ref_field), set())
        held = held_keys.get((ref_feed, ref_field), set())
        column = labels.get(f.name, f.name)
        list_name = ref_feed.replace("_", " ")
        for row in rows:
            value = row.record.get(f.name)
            if value is None or str(value) in known:
                continue
            if str(value) in held:
                # The code is right; the row it points at is itself waiting on
                # a fix. Saying "doesn't match" would send them hunting for a typo.
                row.violations.append(
                    Violation(
                        rule=HELD_REFERENCE,
                        source_row=row.source_row,
                        field=f.name,
                        column=column,
                        value=value,
                        message=(
                            f"{column} '{value}' is on your {list_name} list, but that row was held "
                            f"back with its own problem. This row will load once it's fixed."
                        ),
                    )
                )
                continue
            row.violations.append(
                Violation(
                    rule=UNKNOWN_REFERENCE,
                    source_row=row.source_row,
                    field=f.name,
                    column=column,
                    value=value,
                    message=(
                        f"{column} '{value}' doesn't match anything in your "
                        f"{ref_feed.replace('_', ' ')} list. Fix the code, or send the "
                        f"{ref_feed.replace('_', ' ')} list first."
                    ),
                )
            )


def _range_text(f: Field) -> str:
    if f.min is not None and f.max is not None:
        return f"it has to be between {f.min:g} and {f.max:g}"
    if f.min is not None:
        return f"it can't be less than {f.min:g}"
    return f"it can't be more than {f.max:g}"
