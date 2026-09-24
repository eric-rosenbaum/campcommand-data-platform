"""Rename a client's columns and values into contract fields."""

from dataclasses import dataclass

from campcommand.clients import FeedConfig
from campcommand.readers import SourceFile


def normalize(text: str) -> str:
    return " ".join(str(text).split()).casefold()


@dataclass
class MappedFile:
    rows: list[dict[str, object]]
    row_numbers: list[int]
    labels: dict[str, str]
    missing_columns: list[str]
    unmapped_columns: list[str]


def map_columns(source: SourceFile, feed: FeedConfig) -> MappedFile:
    by_normalized = {normalize(h): h for h in source.headers if h}
    header_for_field: dict[str, str] = {}
    missing = []
    for client_header, field in feed.columns.items():
        actual = by_normalized.get(normalize(client_header))
        if actual is None:
            missing.append(client_header)
        else:
            header_for_field[field] = actual

    mapped_headers = set(header_for_field.values())
    unmapped = [h for h in source.headers if h and h not in mapped_headers]

    value_maps = {
        field: {normalize(k): v for k, v in mapping.items()} for field, mapping in feed.values.items()
    }

    rows = []
    for raw in source.rows:
        row = {}
        for field, header in header_for_field.items():
            value = raw.get(header)
            mapping = value_maps.get(field)
            if mapping and isinstance(value, str | int | float) and not isinstance(value, bool):
                # Unrecognised values pass through untouched so validation can
                # report the client's original text.
                value = mapping.get(normalize(value), value)
            row[field] = value
        rows.append(row)

    return MappedFile(
        rows=rows,
        row_numbers=source.row_numbers,
        labels=feed.labels,
        missing_columns=missing,
        unmapped_columns=unmapped,
    )
