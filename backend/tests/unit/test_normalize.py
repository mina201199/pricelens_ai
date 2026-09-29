from datetime import date

import pytest

from price_lens.ingestion.normalize import (
    format_roc_date,
    inclusive_dates,
    parse_roc_date,
    source_record_hash,
)


def test_roc_date_round_trip() -> None:
    value = date(2026, 9, 28)
    assert format_roc_date(value) == "115.09.28"
    assert parse_roc_date("115.09.28") == value


@pytest.mark.parametrize("value", ["2026-09-28", "foo", "115.13.01", ""])
def test_invalid_roc_date_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        parse_roc_date(value)


def test_inclusive_dates_and_invalid_range() -> None:
    assert inclusive_dates(date(2026, 9, 27), date(2026, 9, 28)) == [
        date(2026, 9, 27),
        date(2026, 9, 28),
    ]
    with pytest.raises(ValueError):
        inclusive_dates(date(2026, 9, 28), date(2026, 9, 27))


def test_source_hash_is_order_independent() -> None:
    assert source_record_hash({"b": 2, "a": 1}) == source_record_hash({"a": 1, "b": 2})
