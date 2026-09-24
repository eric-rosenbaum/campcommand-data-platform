"""Per-batch error reports written for the client, not for us.

Each report is an HTML page plus a CSV of the rejected rows in the client's
own column layout with a "What to fix" column. They fix the CSV or their
source spreadsheet and send it back; rows that come back clean are marked
resolved in the quarantine automatically.
"""

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, select_autoescape

from campcommand import validation as rules
from campcommand.clients import Client
from campcommand.contracts import Contract

if TYPE_CHECKING:
    from campcommand.pipeline import BatchResult

RULE_TITLES = {
    "unreadable": "We couldn't open the file",
    rules.MISSING_COLUMN: "A required column is missing",
    rules.REQUIRED: "Required values left blank",
    rules.INVALID_TYPE: "Values we couldn't read",
    rules.NOT_ALLOWED: "Values we don't recognise",
    rules.OUT_OF_RANGE: "Numbers outside the allowed range",
    rules.BAD_FORMAT: "Codes in the wrong format",
    rules.DUPLICATE_KEY: "Rows that appear twice",
    rules.UNKNOWN_REFERENCE: "Codes that don't match your other lists",
    rules.HELD_REFERENCE: "Rows waiting on a fix somewhere else",
}

MAX_EXAMPLES = 12

_env = Environment(
    loader=PackageLoader("campcommand", "templates"),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def write_report(
    reports_dir: Path,
    client: Client,
    contract: Contract,
    batch: "BatchResult",
    result: rules.ValidationResult,
    unmapped_columns: list[str],
) -> Path:
    out_dir = reports_dir / client.tenant_id
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{datetime.now():%Y%m%d-%H%M%S}_{batch.feed}_{batch.batch_id[:8]}"
    labels = client.feeds[batch.feed].labels

    csv_path = out_dir / f"{stem}_rows_to_fix.csv"
    if result.rejected and not result.file_violations:
        _write_rejected_csv(csv_path, result.rejected, contract, labels)
    else:
        csv_path = None

    html = _env.get_template("error_report.html.j2").render(
        client=client,
        batch=batch,
        feed_title=batch.feed.replace("_", " "),
        file_problems=result.file_violations,
        groups=_group(result.rejected) if not result.file_violations else [],
        unmapped_columns=unmapped_columns,
        csv_name=csv_path.name if csv_path else None,
        generated_at=datetime.now(),
        rule_titles=RULE_TITLES,
    )
    html_path = out_dir / f"{stem}.html"
    html_path.write_text(html, encoding="utf-8")
    return html_path


def _group(rejected: list[rules.Row]) -> list[dict]:
    groups: dict[tuple[str, str], list[rules.Violation]] = defaultdict(list)
    for row in rejected:
        for v in row.violations:
            groups[(v.rule, v.column or "")].append(v)
    # Biggest problems first, except rows that are only waiting on another
    # file: there's nothing to fix in them, so they go last.
    ordered = sorted(
        groups.items(),
        key=lambda item: (item[0][0] == rules.HELD_REFERENCE, -len(item[1]), item[0]),
    )
    return [
        {
            "title": RULE_TITLES.get(rule, rule),
            "column": column,
            "count": len(violations),
            "examples": violations[:MAX_EXAMPLES],
            "more": max(0, len(violations) - MAX_EXAMPLES),
        }
        for (rule, column), violations in ordered
    ]


def _write_rejected_csv(path: Path, rejected, contract: Contract, labels: dict[str, str]) -> None:
    fields = list(contract.fields)
    headers = ["Row in your file", *[labels.get(f, f) for f in fields], "What to fix"]
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        for row in rejected:
            writer.writerow(
                [
                    row.source_row,
                    *[_cell(row.raw.get(f)) for f in fields],
                    " ".join(v.message for v in row.violations),
                ]
            )


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return (
            value.strftime("%Y-%m-%d %H:%M") if value.time() != datetime.min.time() else f"{value:%Y-%m-%d}"
        )
    return str(value)
