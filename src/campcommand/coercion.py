"""Turn whatever a client's spreadsheet produced into typed values.

Every function takes the raw cell (a string from a CSV, or a str / int /
float / datetime from openpyxl) and returns a Python value or raises
CoercionError with a message a camp director can act on.
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

TRUE_VALUES = {"true", "t", "yes", "y", "1", "x"}
FALSE_VALUES = {"false", "f", "no", "n", "0"}

EXCEL_EPOCH = datetime(1899, 12, 30)
# Serial numbers Excel would display as dates between ~1954 and ~2119.
EXCEL_SERIAL_RANGE = (20000, 80000)

_CURRENCY = re.compile(r"[$€£¢]|CAD|USD", re.IGNORECASE)
_INTEGER = re.compile(r"^-?\d+(\.0+)?$")


class CoercionError(ValueError):
    pass


@dataclass(frozen=True)
class ParseOptions:
    date_formats: tuple[str, ...] = ()
    timestamp_formats: tuple[str, ...] = ()
    decimal_separator: str = "."
    timezone: str = "UTC"


DEFAULT_OPTIONS = ParseOptions()


def is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def coerce(value: object, type_: str, opts: ParseOptions = DEFAULT_OPTIONS) -> object:
    if is_blank(value):
        return None
    return _COERCERS[type_](value, opts)


def to_string(value: object, opts: ParseOptions) -> str:
    # Excel hands back 101.0 for a cell that says 101.
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return " ".join(str(value).split())


def to_integer(value: object, opts: ParseOptions) -> int:
    if isinstance(value, bool):
        raise CoercionError("expected a whole number")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise CoercionError("expected a whole number")
    text = _strip_thousands(str(value).strip(), opts.decimal_separator)
    if opts.decimal_separator == ",":
        text = text.replace(",", ".")
    if not _INTEGER.match(text):
        raise CoercionError("expected a whole number")
    return int(Decimal(text))


def to_decimal(value: object, opts: ParseOptions) -> Decimal:
    if isinstance(value, bool):
        raise CoercionError("expected a number")
    if isinstance(value, int | float):
        return Decimal(str(value))
    text = _CURRENCY.sub("", str(value)).strip()
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").strip()
    text = _strip_thousands(text, opts.decimal_separator)
    if opts.decimal_separator == ",":
        text = text.replace(",", ".")
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise CoercionError("expected a number") from None
    if not number.is_finite():
        raise CoercionError("expected a number")
    return -number if negative else number


def to_date(value: object, opts: ParseOptions) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        return _from_excel_serial(value).date()
    text = str(value).strip()
    for fmt in opts.date_formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    raise CoercionError(_expected_format("a date", opts.date_formats))


def to_timestamp(value: object, opts: ParseOptions) -> datetime:
    """Returns a naive UTC datetime. Values without an offset are read in the
    client's local time zone."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, int | float) and not isinstance(value, bool):
        parsed = _from_excel_serial(value)
    else:
        parsed = _parse_timestamp_text(str(value).strip(), opts)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(opts.timezone))
    return parsed.astimezone(UTC).replace(tzinfo=None)


def to_boolean(value: object, opts: ParseOptions) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    raise CoercionError("expected yes or no")


def _parse_timestamp_text(text: str, opts: ParseOptions) -> datetime:
    for fmt in opts.timestamp_formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise CoercionError(_expected_format("a date and time", opts.timestamp_formats)) from None


def _from_excel_serial(value: float) -> datetime:
    low, high = EXCEL_SERIAL_RANGE
    if not low <= value <= high:
        raise CoercionError("expected a date")
    return EXCEL_EPOCH + timedelta(days=float(value))


def _strip_thousands(text: str, decimal_separator: str) -> str:
    text = text.replace(" ", "").replace(" ", "")
    return text.replace(".", "") if decimal_separator == "," else text.replace(",", "")


def _expected_format(what: str, formats: tuple[str, ...]) -> str:
    if not formats:
        return f"expected {what}"
    example = datetime(2026, 7, 4, 14, 30).strftime(formats[0])
    return f"expected {what} like {example}"


_COERCERS = {
    "string": to_string,
    "integer": to_integer,
    "decimal": to_decimal,
    "date": to_date,
    "timestamp": to_timestamp,
    "boolean": to_boolean,
}
