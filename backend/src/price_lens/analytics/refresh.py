import logging
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, distinct, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from price_lens.analytics.calculator import (
    ALL_MARKETS_SCOPE,
    CALCULATION_VERSION,
    CLASSIFICATION_VERSION,
    DailyAggregate,
    compute_series_metrics,
)
from price_lens.db.models import (
    DailyProductMetric,
    Market,
    MarketPriceObservation,
    Product,
)

logger = logging.getLogger(__name__)


class AnalyticsRefresher:
    def refresh(self, session: Session) -> dict[str, int]:
        aggregates = self._daily_aggregates(session)
        grouped: dict[tuple[int, str], list[DailyAggregate]] = defaultdict(list)
        for point in aggregates:
            grouped[(point.family_id, point.scope_key)].append(point)

        computed_at = datetime.now(UTC)
        rows: list[dict[str, Any]] = []
        for points in grouped.values():
            for row in compute_series_metrics(points):
                row["computed_at"] = computed_at
                rows.append(row)

        session.execute(
            delete(DailyProductMetric).where(
                DailyProductMetric.calculation_version == CALCULATION_VERSION,
                DailyProductMetric.classification_version == CLASSIFICATION_VERSION,
            )
        )
        for offset in range(0, len(rows), 1000):
            batch = rows[offset : offset + 1000]
            if batch:
                session.execute(pg_insert(DailyProductMetric).values(batch))

        result = {
            "source_daily_aggregates": len(aggregates),
            "series_count": len(grouped),
            "metrics_written": len(rows),
        }
        logger.info("analytics_refresh_complete", extra=result)
        return result

    def _daily_aggregates(self, session: Session) -> list[DailyAggregate]:
        all_market_rows = session.execute(
            select(
                MarketPriceObservation.trade_date,
                Product.family_id,
                (
                    func.sum(
                        MarketPriceObservation.average_price
                        * MarketPriceObservation.volume_kg
                    )
                    / func.sum(MarketPriceObservation.volume_kg)
                ).label("weighted_avg_price"),
                func.sum(MarketPriceObservation.volume_kg).label("total_volume_kg"),
                func.count(distinct(MarketPriceObservation.market_id)).label(
                    "market_count"
                ),
                func.count(distinct(MarketPriceObservation.product_id)).label(
                    "product_count"
                ),
                func.array_agg(distinct(Product.source_product_code)).label("codes"),
            )
            .join(Product, MarketPriceObservation.product_id == Product.id)
            .where(Product.analytics_included.is_(True), Product.family_id.is_not(None))
            .group_by(MarketPriceObservation.trade_date, Product.family_id)
            .order_by(Product.family_id, MarketPriceObservation.trade_date)
        ).all()

        market_rows = session.execute(
            select(
                MarketPriceObservation.trade_date,
                Product.family_id,
                Market.id.label("market_id"),
                Market.source_market_code,
                (
                    func.sum(
                        MarketPriceObservation.average_price
                        * MarketPriceObservation.volume_kg
                    )
                    / func.sum(MarketPriceObservation.volume_kg)
                ).label("weighted_avg_price"),
                func.sum(MarketPriceObservation.volume_kg).label("total_volume_kg"),
                func.count(distinct(MarketPriceObservation.product_id)).label(
                    "product_count"
                ),
                func.array_agg(distinct(Product.source_product_code)).label("codes"),
            )
            .join(Product, MarketPriceObservation.product_id == Product.id)
            .join(Market, MarketPriceObservation.market_id == Market.id)
            .where(Product.analytics_included.is_(True), Product.family_id.is_not(None))
            .group_by(
                MarketPriceObservation.trade_date,
                Product.family_id,
                Market.id,
                Market.source_market_code,
            )
            .order_by(
                Product.family_id,
                Market.id,
                MarketPriceObservation.trade_date,
            )
        ).all()

        aggregates = [
            DailyAggregate(
                trade_date=row.trade_date,
                family_id=row.family_id,
                scope_key=ALL_MARKETS_SCOPE,
                market_id=None,
                weighted_avg_price=Decimal(row.weighted_avg_price),
                total_volume_kg=Decimal(row.total_volume_kg),
                market_count=row.market_count,
                product_count=row.product_count,
                included_product_codes=tuple(sorted(row.codes)),
            )
            for row in all_market_rows
        ]
        aggregates.extend(
            DailyAggregate(
                trade_date=row.trade_date,
                family_id=row.family_id,
                scope_key=f"market:{row.source_market_code}",
                market_id=row.market_id,
                weighted_avg_price=Decimal(row.weighted_avg_price),
                total_volume_kg=Decimal(row.total_volume_kg),
                market_count=1,
                product_count=row.product_count,
                included_product_codes=tuple(sorted(row.codes)),
            )
            for row in market_rows
        )
        return aggregates
