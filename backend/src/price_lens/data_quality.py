from datetime import date, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from price_lens.analytics.calculator import (
    ALL_MARKETS_SCOPE,
    CALCULATION_VERSION,
    CLASSIFICATION_VERSION,
)
from price_lens.db.models import (
    DailyProductMetric,
    IngestionRun,
    Market,
    MarketPriceObservation,
    Product,
    ProductFamily,
    RawMarketRecord,
)


def build_data_quality_report(session: Session) -> dict[str, Any]:
    observation_summary = session.execute(
        select(
            func.count(MarketPriceObservation.id),
            func.min(MarketPriceObservation.trade_date),
            func.max(MarketPriceObservation.trade_date),
            func.count(func.distinct(MarketPriceObservation.product_id)),
            func.count(func.distinct(MarketPriceObservation.market_id)),
        )
    ).one()

    duplicate_groups = session.execute(
        select(func.count()).select_from(
            select(
                MarketPriceObservation.source_id,
                MarketPriceObservation.trade_date,
                MarketPriceObservation.market_id,
                MarketPriceObservation.product_id,
            )
            .group_by(
                MarketPriceObservation.source_id,
                MarketPriceObservation.trade_date,
                MarketPriceObservation.market_id,
                MarketPriceObservation.product_id,
            )
            .having(func.count() > 1)
            .subquery()
        )
    ).scalar_one()

    invalid_price_count = session.execute(
        select(func.count(MarketPriceObservation.id)).where(
            or_(
                MarketPriceObservation.average_price.is_(None),
                MarketPriceObservation.volume_kg.is_(None),
                MarketPriceObservation.average_price <= 0,
                MarketPriceObservation.volume_kg <= 0,
                MarketPriceObservation.lower_price < 0,
                MarketPriceObservation.middle_price < 0,
                MarketPriceObservation.upper_price < 0,
                MarketPriceObservation.lower_price > MarketPriceObservation.middle_price,
                MarketPriceObservation.middle_price > MarketPriceObservation.upper_price,
                MarketPriceObservation.average_price < MarketPriceObservation.lower_price,
                MarketPriceObservation.average_price > MarketPriceObservation.upper_price,
            )
        )
    ).scalar_one()

    raw_status_rows = session.execute(
        select(RawMarketRecord.validation_status, func.count(RawMarketRecord.id)).group_by(
            RawMarketRecord.validation_status
        )
    ).all()
    raw_status = {status: count for status, count in raw_status_rows}

    unmapped_products = session.execute(
        select(func.count(Product.id)).where(Product.family_id.is_(None))
    ).scalar_one()
    total_products = session.execute(select(func.count(Product.id))).scalar_one()
    total_markets = session.execute(select(func.count(Market.id))).scalar_one()

    cabbage_rows = session.execute(
        select(
            Product.source_product_code,
            Product.source_product_name,
            Product.origin_type,
            Product.analytics_included,
            Product.mapping_version,
            ProductFamily.canonical_name,
        )
        .outerjoin(ProductFamily, Product.family_id == ProductFamily.id)
        .where(
            or_(
                Product.source_product_name.contains("甘藍"),
                ProductFamily.canonical_name.in_(["甘藍", "球莖甘藍"]),
            )
        )
        .order_by(Product.source_product_code)
    ).all()

    latest_run = session.execute(
        select(IngestionRun)
        .where(IngestionRun.status == "succeeded")
        .order_by(IngestionRun.finished_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    analytics_summary = session.execute(
        select(
            func.count(DailyProductMetric.id),
            func.min(DailyProductMetric.trade_date),
            func.max(DailyProductMetric.trade_date),
            func.count(func.distinct(DailyProductMetric.family_id)),
            func.count(func.distinct(DailyProductMetric.scope_key)),
        ).where(
            DailyProductMetric.calculation_version == CALCULATION_VERSION,
            DailyProductMetric.classification_version == CLASSIFICATION_VERSION,
        )
    ).one()

    latest_metric_dates = (
        select(
            DailyProductMetric.family_id,
            func.max(DailyProductMetric.trade_date).label("latest_date"),
        )
        .where(
            DailyProductMetric.scope_key == ALL_MARKETS_SCOPE,
            DailyProductMetric.calculation_version == CALCULATION_VERSION,
            DailyProductMetric.classification_version == CLASSIFICATION_VERSION,
        )
        .group_by(DailyProductMetric.family_id)
        .subquery()
    )
    latest_classifications = session.execute(
        select(DailyProductMetric.classification, func.count())
        .join(
            latest_metric_dates,
            (DailyProductMetric.family_id == latest_metric_dates.c.family_id)
            & (DailyProductMetric.trade_date == latest_metric_dates.c.latest_date),
        )
        .where(
            DailyProductMetric.scope_key == ALL_MARKETS_SCOPE,
            DailyProductMetric.calculation_version == CALCULATION_VERSION,
            DailyProductMetric.classification_version == CLASSIFICATION_VERSION,
        )
        .group_by(DailyProductMetric.classification)
    ).all()

    report = {
        "dataset_semantics": "Taiwan agricultural wholesale market transactions",
        "price_unit": "TWD/kg wholesale",
        "observation_count": observation_summary[0],
        "trade_date_min": _serialize(observation_summary[1]),
        "trade_date_max": _serialize(observation_summary[2]),
        "observed_product_count": observation_summary[3],
        "observed_market_count": observation_summary[4],
        "dimension_product_count": total_products,
        "dimension_market_count": total_markets,
        "duplicate_natural_key_groups": duplicate_groups,
        "null_or_invalid_price_count": invalid_price_count,
        "raw_record_status": {
            "valid": raw_status.get("valid", 0),
            "excluded_closure": raw_status.get("excluded_closure", 0),
            "quarantined": raw_status.get("quarantined", 0),
        },
        "unmapped_product_count": unmapped_products,
        "cabbage_source_samples": [
            {
                "source_product_code": row.source_product_code,
                "source_product_name": row.source_product_name,
                "canonical_family": row.canonical_name,
                "origin_type": row.origin_type,
                "analytics_included": row.analytics_included,
                "mapping_version": row.mapping_version,
            }
            for row in cabbage_rows
        ],
        "latest_successful_run": _run_payload(latest_run),
        "analytics": {
            "calculation_version": CALCULATION_VERSION,
            "classification_version": CLASSIFICATION_VERSION,
            "metric_count": analytics_summary[0],
            "trade_date_min": _serialize(analytics_summary[1]),
            "trade_date_max": _serialize(analytics_summary[2]),
            "family_count": analytics_summary[3],
            "scope_count": analytics_summary[4],
            "latest_classification_counts": {
                label: count for label, count in latest_classifications
            },
        },
    }
    return report


def _serialize(value: date | datetime | None) -> str | None:
    return value.isoformat() if value else None


def _run_payload(run: IngestionRun | None) -> dict[str, Any] | None:
    if run is None:
        return None
    return {
        "id": run.id,
        "window_start": run.window_start.isoformat(),
        "window_end": run.window_end.isoformat(),
        "records_received": run.records_received,
        "records_inserted": run.records_inserted,
        "records_updated": run.records_updated,
        "records_unchanged": run.records_unchanged,
        "records_excluded": run.records_excluded,
        "records_quarantined": run.records_quarantined,
        "finished_at": _serialize(run.finished_at),
        "code_version": run.code_version,
    }
