"""Writes each camp's reference data and store sales the way that camp's own
systems export them, using the client config in reverse: contract fields
become the client's column names and values become the client's labels.

Round 1 is what a new client actually sends: mostly fine, with the kinds of
mistakes that show up in hand-maintained spreadsheets. Round 2 is the same
data after the client fixed what the error report told them to.
"""

import csv
import random
from dataclasses import asdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

from campcommand.clients import Client, FeedConfig
from campcommand.contracts import Contract, ContractRegistry
from campcommand.synthetic.commissary import generate_sales
from campcommand.synthetic.world import World


class Raw(str):
    """A cell value written exactly as given, bypassing formatting."""


FILE_NAMES = {
    "tall_pines": {
        "buildings": "Facilities{suffix}.csv",
        "assets": "Equipment List{suffix}.xlsx",
        "staff": "Staff Roster{suffix}.csv",
        "commissary_transactions": "POS Export {end:%Y-%m-%d}{suffix}.csv",
        "suffix": " (corrected)",
    },
    "lakeview": {
        "buildings": "lakeview_facilities{suffix}.xlsx",
        "assets": "lakeview_assets{suffix}.xlsx",
        "staff": "lakeview_staff{suffix}.xlsx",
        "commissary_transactions": "lakeview_store_{start:%Y%m%d}{suffix}.csv",
        "suffix": "_corrected",
    },
    "chene_rouge": {
        "buildings": "batiments{suffix}.csv",
        "assets": "equipements{suffix}.csv",
        "staff": "personnel{suffix}.csv",
        "commissary_transactions": "ventes_{start:%Y-%m-%d}{suffix}.csv",
        "suffix": "_corrige",
    },
}

# Formatting habits that aren't expressed in the client config because the
# pipeline copes with them anyway.
CURRENCY_PREFIX = {("tall_pines", "commissary_transactions"): "$"}
BOOLEAN_LABELS = {"tall_pines": ("Y", "N")}

SALES_WEEK_WITH_ROW_ERRORS = 2
SALES_WEEK_MISSING_COLUMN = 5


def reference_records(world: World) -> dict[str, list[dict]]:
    return {
        "buildings": [
            {
                "building_code": b.code,
                "building_name": b.name,
                "building_type": b.type,
                "capacity": b.capacity,
                "year_built": b.year_built,
            }
            for b in world.buildings
        ],
        "assets": [
            {
                "asset_tag": a.tag,
                "asset_name": a.name,
                "category": a.category,
                "building_code": a.building_code,
                "purchased_on": a.purchased_on,
                "purchase_cost": a.cost,
                "purchase_price": a.cost,
                "status": a.status,
            }
            for a in world.assets
        ],
        "staff": [asdict(s) | {"staff_code": s.code} for s in world.staff],
    }


def inject_reference_errors(records: dict[str, list[dict]], world: World, rng: random.Random) -> None:
    buildings = records["buildings"]
    cabins = [i for i, b in enumerate(buildings) if b["building_type"] == "cabin"]
    buildings.append(
        {**buildings[cabins[3]], "building_name": "Old " + buildings[cabins[3]]["building_name"]}
    )
    buildings[cabins[5]]["building_name"] = None
    buildings[cabins[-1]]["building_type"] = Raw("Yurt")

    assets = records["assets"]
    picks = rng.sample(range(len(assets)), 5)
    assets[picks[0]]["building_code"] = Raw("ZZ-99")
    assets[picks[1]]["purchase_cost"] = assets[picks[1]]["purchase_price"] = -150
    assets[picks[2]]["purchased_on"] = Raw("sometime in 2019")
    assets[picks[3]]["category"] = Raw("Pool Stuff")
    assets[picks[4]]["asset_tag"] = None

    counselors = [i for i, s in enumerate(records["staff"]) if s["role"] == "counselor"]
    staff = records["staff"]
    staff[counselors[2]]["email"] = Raw("jess.m@")
    staff[counselors[5]]["start_date"] = None
    staff[counselors[8]]["role"] = Raw("Chef")


def write_round(
    world: World,
    client: Client,
    registry: ContractRegistry,
    landing_dir: Path,
    season: tuple[date, date],
    round_number: int,
    seed: int,
) -> list[Path]:
    rng = random.Random(f"{world.tenant_id}-exports-{seed}")
    out_dir = landing_dir / world.tenant_id
    out_dir.mkdir(parents=True, exist_ok=True)
    names = FILE_NAMES[world.tenant_id]
    suffix = names["suffix"] if round_number > 1 else ""
    written = []

    records = reference_records(world)
    if round_number == 1:
        inject_reference_errors(records, world, rng)

    for feed in ("buildings", "assets", "staff"):
        cfg = client.feeds[feed]
        path = out_dir / names[feed].format(suffix=suffix)
        _write(path, client, cfg, registry.get(cfg.contract), records[feed], exported=season[0])
        written.append(path)

    cfg = client.feeds["commissary_transactions"]
    contract = registry.get(cfg.contract)
    sales = generate_sales(world, season[0], season[1], seed)
    for week, (start, end) in enumerate(_weeks(*season)):
        if round_number > 1 and week not in (SALES_WEEK_WITH_ROW_ERRORS, SALES_WEEK_MISSING_COLUMN):
            continue
        # Each export repeats the last day of the previous one.
        lines = [dict(line) for line in sales if start - timedelta(days=1) <= line["sold_at"].date() <= end]
        drop = set()
        if round_number == 1 and week == SALES_WEEK_WITH_ROW_ERRORS:
            for i in rng.sample(range(len(lines)), 3):
                lines[i]["quantity"] = 0
            for i in rng.sample(range(len(lines)), 2):
                lines[i]["store_building_code"] = Raw("OLD-STORE")
            lines[rng.randrange(len(lines))]["unit_price"] = Raw("free")
        if round_number == 1 and week == SALES_WEEK_MISSING_COLUMN:
            drop.add("payment_method")
        path = out_dir / names["commissary_transactions"].format(start=start, end=end, suffix=suffix)
        _write(path, client, cfg, contract, lines, exported=end, drop=drop)
        written.append(path)
    return written


def _weeks(season_start: date, season_end: date):
    start = season_start - timedelta(days=season_start.weekday())
    while start <= season_end:
        end = start + timedelta(days=6)
        yield max(start, season_start), min(end, season_end)
        start = end + timedelta(days=1)


def _write(path, client, cfg: FeedConfig, contract: Contract, records, exported: date, drop=frozenset()):
    columns = [(header, field) for header, field in cfg.columns.items() if field not in drop]
    reverse_values = {field: {} for field in cfg.values}
    for field, mapping in cfg.values.items():
        for label, canonical in mapping.items():
            reverse_values[field].setdefault(canonical, label)

    excel = cfg.format.type == "excel"
    rows = [
        [_render(client, cfg, contract, field, rec.get(field), reverse_values, excel) for _, field in columns]
        for rec in records
    ]
    headers = [header for header, _ in columns]

    if excel:
        wb = Workbook()
        ws = wb.active
        ws.title = cfg.format.sheet or "Sheet1"
        preamble = [[f"{client.name}: {cfg.feed.replace('_', ' ')}"], [f"Exported {exported:%B %-d, %Y}"]]
        for line in preamble[: cfg.format.header_row - 1]:
            ws.append(line)
        ws.append(headers)
        for row in rows:
            ws.append(row)
        wb.save(path)
    else:
        with path.open("w", newline="", encoding=cfg.format.encoding) as fh:
            writer = csv.writer(fh, delimiter=cfg.format.delimiter)
            writer.writerow(headers)
            writer.writerows(rows)


def _render(client, cfg, contract, field, value, reverse_values, excel):
    if value is None:
        return None if excel else ""
    if isinstance(value, Raw):
        return str(value)
    f = contract.fields[field]
    if field in reverse_values:
        key = "true" if value is True else "false" if value is False else value
        value = reverse_values[field].get(key, value)
        if isinstance(value, str):
            return value

    if f.type == "boolean":
        yes, no = BOOLEAN_LABELS.get(client.tenant_id, ("true", "false"))
        return yes if value else no
    if f.type == "date":
        if excel:
            return value
        fmt = cfg.parse.date_formats[0] if cfg.parse.date_formats else "%Y-%m-%d"
        return value.strftime(fmt)
    if f.type == "timestamp":
        if excel:
            return value
        if cfg.parse.timestamp_formats:
            text = value.strftime(cfg.parse.timestamp_formats[0])
            return text.replace(" 0", " ", 1) if "%I" in cfg.parse.timestamp_formats[0] else text
        return value.isoformat(timespec="seconds")
    if f.type == "decimal":
        if excel:
            return float(value)
        text = f"{Decimal(str(value)):.2f}"
        if cfg.parse.decimal_separator == ",":
            text = text.replace(".", ",")
        return CURRENCY_PREFIX.get((client.tenant_id, cfg.feed), "") + text
    return value if excel else str(value)


def season_for(today: date) -> tuple[date, date]:
    """The most recent camp season that has fully ended."""
    year = today.year if today >= date(today.year, 8, 25) else today.year - 1
    return date(year, 6, 22), date(year, 8, 21)


def local_naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None)
