from datetime import date, timedelta
from decimal import Decimal

import pytest

from price_lens.analytics.calculator import (
    ALL_MARKETS_SCOPE,
    DailyAggregate,
    classify_price,
    compute_series_metrics,
)


def _point(day: date, price: int | str, volume: int | str = 100) -> DailyAggregate:
    return DailyAggregate(
        trade_date=day,
        family_id=1,
        scope_key=ALL_MARKETS_SCOPE,
        market_id=None,
        weighted_avg_price=Decimal(price),
        total_volume_kg=Decimal(volume),
        market_count=2,
        product_count=1,
        included_product_codes=("LA1",),
    )


def test_calendar_windows_and_comparable_day_changes() -> None:
    start = date(2026, 1, 1)
    points = [
        _point(start, 10),
        _point(start + timedelta(days=6), 20),
        _point(start + timedelta(days=7), 30),
    ]

    latest = compute_series_metrics(points)[-1]

    assert latest["ma_7d"] == Decimal(25)
    assert latest["ma_30d"] == Decimal(20)
    assert latest["wow_change_pct"] == Decimal(200)
    assert latest["history_day_count"] == 3
    assert latest["classification"] == "insufficient_data"


def test_volume_change_compares_adjacent_calendar_weeks() -> None:
    start = date(2026, 1, 1)
    points = [
        _point(start + timedelta(days=offset), 100, 100 if offset < 7 else 200)
        for offset in range(14)
    ]

    latest = compute_series_metrics(points)[-1]

    assert latest["volume_change_pct"] == Decimal(100)
    assert latest["percentile_365d"] == Decimal(50)
    assert latest["z_score_365d"] is None
    assert latest["robust_z_365d"] is None


def test_outlier_classification_uses_percentile_and_robust_z() -> None:
    start = date(2026, 1, 1)
    points = [
        _point(start + timedelta(days=offset), offset + 1) for offset in range(119)
    ]
    points.append(_point(start + timedelta(days=119), 500))

    latest = compute_series_metrics(points)[-1]

    assert latest["history_day_count"] == 120
    assert latest["percentile_365d"] == pytest.approx(Decimal("99.583333"))
    assert latest["robust_z_365d"] > Decimal(2)
    assert latest["classification"] == "anomalously_high"
    assert latest["historical_high_price"] == Decimal(500)
    assert latest["historical_high_date"] == start + timedelta(days=119)


@pytest.mark.parametrize(
    ("history", "current", "ma_30", "percentile", "robust_z", "expected"),
    [
        (119, "200", "100", "99", "5", "insufficient_data"),
        (120, "200", "100", "96", "3", "anomalously_high"),
        (120, "116", "100", "50", "0", "high"),
        (120, "84", "100", "50", "0", "low"),
        (120, "100", "100", "50", "0", "normal"),
    ],
)
def test_classification_boundaries(
    history: int,
    current: str,
    ma_30: str,
    percentile: str,
    robust_z: str,
    expected: str,
) -> None:
    assert (
        classify_price(
            history_day_count=history,
            current=Decimal(current),
            ma_30d=Decimal(ma_30),
            percentile_365d=Decimal(percentile),
            robust_z_365d=Decimal(robust_z),
        )
        == expected
    )
