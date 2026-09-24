from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from campcommand.coercion import CoercionError, ParseOptions, coerce

US = ParseOptions(
    date_formats=("%m/%d/%Y",), timestamp_formats=("%m/%d/%Y %I:%M %p",), timezone="America/New_York"
)
QC = ParseOptions(
    date_formats=("%d/%m/%Y",),
    timestamp_formats=("%d/%m/%Y %H:%M",),
    decimal_separator=",",
    timezone="America/Toronto",
)

money = st.decimals(min_value=Decimal("0"), max_value=Decimal("999999.99"), places=2)
days = st.dates(min_value=date(1960, 1, 1), max_value=date(2090, 12, 31))


@given(money)
def test_us_currency_round_trips(amount):
    assert coerce(f"${amount:,.2f}", "decimal", US) == amount


@given(money)
def test_decimal_comma_round_trips(amount):
    text = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    assert coerce(text, "decimal", QC) == amount


@given(st.integers(min_value=-(10**9), max_value=10**9))
def test_integers_with_thousands_separators(n):
    assert coerce(f"{n:,}", "integer", US) == n
    assert coerce(f"{n:,}".replace(",", "."), "integer", QC) == n


@given(days)
def test_dates_in_the_clients_format(d):
    assert coerce(d.strftime("%m/%d/%Y"), "date", US) == d
    assert coerce(d.strftime("%d/%m/%Y"), "date", QC) == d


@given(days)
def test_excel_serial_dates(d):
    serial = (d - date(1899, 12, 30)).days
    assert coerce(serial, "date") == d
    assert coerce(float(serial), "date") == d


@given(st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31)))
def test_local_timestamps_are_stored_as_utc(local):
    # Skip the hour around DST changes, where wall-clock time is ambiguous.
    local = local.replace(hour=max(local.hour, 4), second=0, microsecond=0)
    text = local.strftime("%m/%d/%Y %I:%M %p")
    utc = coerce(text, "timestamp", US)
    offset = local - utc
    assert offset in (timedelta(hours=-4), timedelta(hours=-5))


def test_iso_timestamp_with_offset_ignores_client_zone():
    assert coerce("2026-07-04T12:00:00-07:00", "timestamp", US) == datetime(2026, 7, 4, 19, 0)


def test_excel_integer_codes_come_back_without_decimal():
    assert coerce(101.0, "string") == "101"


@pytest.mark.parametrize("text", ["Y", "yes", "TRUE", "1", " x "])
def test_truthy(text):
    assert coerce(text, "boolean") is True


@pytest.mark.parametrize("text", ["N", "no", "False", "0"])
def test_falsy(text):
    assert coerce(text, "boolean") is False


@pytest.mark.parametrize(
    ("value", "type_"),
    [
        ("free", "decimal"),
        ("12.5", "integer"),
        ("sometime in 2019", "date"),
        ("maybe", "boolean"),
        (5, "date"),
    ],
)
def test_unreadable_values_raise(value, type_):
    with pytest.raises(CoercionError):
        coerce(value, type_, US)


def test_accounting_negatives():
    assert coerce("($12.50)", "decimal", US) == Decimal("-12.50")


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_blanks_are_none(blank):
    assert coerce(blank, "integer") is None


def test_error_message_shows_expected_format():
    with pytest.raises(CoercionError, match="like 07/04/2026"):
        coerce("July 4th", "date", US)
