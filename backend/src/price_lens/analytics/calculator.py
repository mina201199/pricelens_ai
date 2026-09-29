import math
import statistics
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

CALCULATION_VERSION = "daily-canonical-v1"
CLASSIFICATION_VERSION = "price-classification-v1"
ALL_MARKETS_SCOPE = "all_reporting_markets"
MIN_CLASSIFICATION_HISTORY_DAYS = 120


@dataclass(frozen=True)
class DailyAggregate:
    trade_date: date
    family_id: int
    scope_key: str
    market_id: int | None
    weighted_avg_price: Decimal
    total_volume_kg: Decimal
    market_count: int
    product_count: int
    included_product_codes: tuple[str, ...]


def compute_series_metrics(points: list[DailyAggregate]) -> list[dict[str, Any]]:
    """Compute metrics for one family/scope series ordered by calendar date.

    Moving averages use the arithmetic mean of available daily canonical prices
    inside a calendar-day window. The daily canonical prices themselves are
    volume-weighted upstream.
    """

    ordered = sorted(points, key=lambda point: point.trade_date)
    dates = [point.trade_date for point in ordered]
    results: list[dict[str, Any]] = []

    for index, point in enumerate(ordered):
        window_7 = _calendar_window(ordered, index, 7)
        window_30 = _calendar_window(ordered, index, 30)
        window_90 = _calendar_window(ordered, index, 90)
        window_365 = _calendar_window(ordered, index, 365)
        previous_7 = _previous_comparable(ordered, dates, index, 7)
        previous_30 = _previous_comparable(ordered, dates, index, 30)

        prices_365 = [item.weighted_avg_price for item in window_365]
        percentile = _midpoint_percentile(point.weighted_avg_price, prices_365)
        z_score = _z_score(point.weighted_avg_price, prices_365)
        robust_z = _robust_z_score(point.weighted_avg_price, prices_365)
        high = _historical_extreme(window_365, high=True)
        low = _historical_extreme(window_365, high=False)
        ma_30 = _mean_price(window_30)

        results.append(
            {
                "trade_date": point.trade_date,
                "family_id": point.family_id,
                "scope_key": point.scope_key,
                "market_id": point.market_id,
                "weighted_avg_price": point.weighted_avg_price,
                "total_volume_kg": point.total_volume_kg,
                "market_count": point.market_count,
                "product_count": point.product_count,
                "included_product_codes": list(point.included_product_codes),
                "ma_7d": _mean_price(window_7),
                "ma_30d": ma_30,
                "ma_90d": _mean_price(window_90),
                "wow_change_pct": _change_pct(
                    point.weighted_avg_price,
                    previous_7.weighted_avg_price if previous_7 else None,
                ),
                "mom_change_pct": _change_pct(
                    point.weighted_avg_price,
                    previous_30.weighted_avg_price if previous_30 else None,
                ),
                "percentile_365d": percentile,
                "z_score_365d": z_score,
                "robust_z_365d": robust_z,
                "historical_high_price": high.weighted_avg_price,
                "historical_high_date": high.trade_date,
                "historical_low_price": low.weighted_avg_price,
                "historical_low_date": low.trade_date,
                "volume_change_pct": _volume_change_pct(ordered, index),
                "volatility_30d": _log_return_volatility(window_30),
                "history_day_count": len(window_365),
                "classification": classify_price(
                    history_day_count=len(window_365),
                    current=point.weighted_avg_price,
                    ma_30d=ma_30,
                    percentile_365d=percentile,
                    robust_z_365d=robust_z,
                ),
                "calculation_version": CALCULATION_VERSION,
                "classification_version": CLASSIFICATION_VERSION,
            }
        )
    return results


def classify_price(
    *,
    history_day_count: int,
    current: Decimal,
    ma_30d: Decimal | None,
    percentile_365d: Decimal | None,
    robust_z_365d: Decimal | None,
) -> str:
    if history_day_count < MIN_CLASSIFICATION_HISTORY_DAYS:
        return "insufficient_data"
    if (
        percentile_365d is not None
        and percentile_365d >= Decimal("95")
        and robust_z_365d is not None
        and robust_z_365d >= Decimal("2")
    ):
        return "anomalously_high"
    price_to_ma = current / ma_30d if ma_30d and ma_30d > 0 else None
    if (percentile_365d is not None and percentile_365d >= Decimal("75")) or (
        price_to_ma is not None and price_to_ma >= Decimal("1.15")
    ):
        return "high"
    if (percentile_365d is not None and percentile_365d <= Decimal("25")) or (
        price_to_ma is not None and price_to_ma <= Decimal("0.85")
    ):
        return "low"
    return "normal"


def _calendar_window(
    points: list[DailyAggregate], index: int, calendar_days: int
) -> list[DailyAggregate]:
    current_date = points[index].trade_date
    start = current_date - timedelta(days=calendar_days - 1)
    return [point for point in points[: index + 1] if point.trade_date >= start]


def _previous_comparable(
    points: list[DailyAggregate], dates: list[date], index: int, days_ago: int
) -> DailyAggregate | None:
    target = points[index].trade_date - timedelta(days=days_ago)
    comparable_index = bisect_right(dates, target, hi=index) - 1
    if comparable_index < 0:
        return None
    candidate = points[comparable_index]
    if candidate.trade_date < target - timedelta(days=7):
        return None
    return candidate


def _mean_price(points: list[DailyAggregate]) -> Decimal | None:
    if not points:
        return None
    return sum((point.weighted_avg_price for point in points), Decimal(0)) / Decimal(
        len(points)
    )


def _change_pct(current: Decimal, previous: Decimal | None) -> Decimal | None:
    if previous is None or previous <= 0:
        return None
    return (current / previous - Decimal(1)) * Decimal(100)


def _midpoint_percentile(current: Decimal, values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    less = sum(value < current for value in values)
    equal = sum(value == current for value in values)
    return (
        (Decimal(less) + Decimal(equal) / Decimal(2))
        / Decimal(len(values))
        * Decimal(100)
    )


def _z_score(current: Decimal, values: list[Decimal]) -> Decimal | None:
    if len(values) < 2:
        return None
    float_values = [float(value) for value in values]
    deviation = statistics.pstdev(float_values)
    if deviation == 0:
        return None
    return Decimal(str((float(current) - statistics.fmean(float_values)) / deviation))


def _robust_z_score(current: Decimal, values: list[Decimal]) -> Decimal | None:
    if len(values) < 2:
        return None
    median = statistics.median(values)
    mad = statistics.median(abs(value - median) for value in values)
    if mad == 0:
        return None
    return Decimal("0.6745") * (current - median) / mad


def _historical_extreme(
    points: list[DailyAggregate], *, high: bool
) -> DailyAggregate:
    ordered = sorted(points, key=lambda point: point.trade_date)
    extreme_price = (max if high else min)(point.weighted_avg_price for point in ordered)
    return next(point for point in ordered if point.weighted_avg_price == extreme_price)


def _volume_change_pct(points: list[DailyAggregate], index: int) -> Decimal | None:
    current_date = points[index].trade_date
    current_start = current_date - timedelta(days=6)
    previous_start = current_date - timedelta(days=13)
    previous_end = current_date - timedelta(days=7)
    current_volume = sum(
        (
            point.total_volume_kg
            for point in points[: index + 1]
            if current_start <= point.trade_date <= current_date
        ),
        Decimal(0),
    )
    previous_volume = sum(
        (
            point.total_volume_kg
            for point in points[: index + 1]
            if previous_start <= point.trade_date <= previous_end
        ),
        Decimal(0),
    )
    if previous_volume <= 0:
        return None
    return (current_volume / previous_volume - Decimal(1)) * Decimal(100)


def _log_return_volatility(points: list[DailyAggregate]) -> Decimal | None:
    if len(points) < 3:
        return None
    returns = [
        math.log(float(current.weighted_avg_price / previous.weighted_avg_price))
        for previous, current in zip(points, points[1:], strict=False)
    ]
    if len(returns) < 2:
        return None
    return Decimal(str(statistics.pstdev(returns)))
