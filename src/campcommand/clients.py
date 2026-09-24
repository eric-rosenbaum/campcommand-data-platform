from dataclasses import dataclass
from pathlib import Path

import yaml

from campcommand.coercion import ParseOptions


@dataclass(frozen=True)
class SourceFormat:
    type: str
    encoding: str = "utf-8"
    delimiter: str = ","
    sheet: str | None = None
    header_row: int = 1


@dataclass(frozen=True)
class FeedConfig:
    feed: str
    contract: str
    files: str
    format: SourceFormat
    columns: dict[str, str]
    values: dict[str, dict[str, str]]
    parse: ParseOptions

    @property
    def labels(self) -> dict[str, str]:
        """Contract field -> the client's own column header."""
        return {field: header for header, field in self.columns.items()}


@dataclass(frozen=True)
class Client:
    tenant_id: str
    name: str
    timezone: str
    contact_name: str
    contact_email: str
    feeds: dict[str, FeedConfig]


def load_client(path: Path) -> Client:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    defaults = raw.get("defaults", {})
    feeds = {}
    for feed, spec in raw["feeds"].items():
        fmt = {**defaults.get("format", {}), **spec.get("format", {})}
        parse = {**defaults.get("parse", {}), **spec.get("parse", {})}
        feeds[feed] = FeedConfig(
            feed=feed,
            contract=spec["contract"],
            files=spec["files"],
            format=SourceFormat(**fmt),
            columns={str(k): v for k, v in spec["columns"].items()},
            values={
                field: {str(k): str(v) for k, v in mapping.items()}
                for field, mapping in (spec.get("values") or {}).items()
            },
            parse=ParseOptions(
                date_formats=tuple(parse.get("date_formats", ())),
                timestamp_formats=tuple(parse.get("timestamp_formats", ())),
                decimal_separator=parse.get("decimal_separator", "."),
                timezone=raw["timezone"],
            ),
        )
    return Client(
        tenant_id=raw["tenant_id"],
        name=raw["name"],
        timezone=raw["timezone"],
        contact_name=raw["contact"]["name"],
        contact_email=raw["contact"]["email"],
        feeds=feeds,
    )


def load_clients(clients_dir: Path) -> dict[str, Client]:
    clients = [load_client(p) for p in sorted(clients_dir.glob("*.yml"))]
    return {c.tenant_id: c for c in clients}
