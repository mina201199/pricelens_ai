from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from price_lens.analytics.calculator import (
    ALL_MARKETS_SCOPE,
    CALCULATION_VERSION,
    CLASSIFICATION_VERSION,
)
from price_lens.db.models import (
    DailyProductMetric,
    ProductAlias,
    ProductFamily,
)
from price_lens.ingestion.mapping import normalize_alias
from price_lens.schemas.analytics import (
    ClassificationInfo,
    HistoryPoint,
    MetricValues,
    MoverItem,
    MoversResponse,
    PriceSummaryResponse,
    ProductHistoryResponse,
    ProductIdentity,
    ProductListItem,
    ScopeInfo,
)

RANGE_DAYS = {"1m": 30, "3m": 90, "6m": 180, "1y": 365, "2y": 730}


class AnalyticsNotFoundError(LookupError):
    pass


class AnalyticsService:
    def list_products(self, session: Session) -> list[ProductListItem]:
        families = session.execute(
            select(ProductFamily).where(ProductFamily.active.is_(True)).order_by(
                ProductFamily.category, ProductFamily.display_name
            )
        ).scalars()
        latest = self._latest_by_family(session)
        return [
            ProductListItem(
                **_identity(family).model_dump(),
                latest_available_trade_date=(
                    latest[family.id].trade_date if family.id in latest else None
                ),
                latest_classification=(
                    latest[family.id].classification if family.id in latest else None
                ),
            )
            for family in families
        ]

    def radar(self, session: Session) -> list[PriceSummaryResponse]:
        families = {
            family.id: family
            for family in session.execute(select(ProductFamily)).scalars()
        }
        latest = self._latest_by_family(session)
        return [
            _summary(families[family_id], metric)
            for family_id, metric in sorted(
                latest.items(), key=lambda item: families[item[0]].display_name
            )
        ]

    def summary(self, session: Session, product_key: str) -> PriceSummaryResponse:
        family = self._resolve_family(session, product_key)
        metric = session.execute(
            select(DailyProductMetric)
            .where(
                DailyProductMetric.family_id == family.id,
                DailyProductMetric.scope_key == ALL_MARKETS_SCOPE,
                DailyProductMetric.calculation_version == CALCULATION_VERSION,
                DailyProductMetric.classification_version == CLASSIFICATION_VERSION,
            )
            .order_by(DailyProductMetric.trade_date.desc())
            .limit(1)
        ).scalar_one_or_none()
        if metric is None:
            raise AnalyticsNotFoundError(
                f"No analytics are available for product {family.slug!r}"
            )
        return _summary(family, metric)

    def history(
        self,
        session: Session,
        product_key: str,
        *,
        range_key: str,
        market: str,
    ) -> ProductHistoryResponse:
        family = self._resolve_family(session, product_key)
        scope_key = ALL_MARKETS_SCOPE if market == "all" else f"market:{market}"
        statement = (
            select(DailyProductMetric)
            .where(
                DailyProductMetric.family_id == family.id,
                DailyProductMetric.scope_key == scope_key,
                DailyProductMetric.calculation_version == CALCULATION_VERSION,
                DailyProductMetric.classification_version == CLASSIFICATION_VERSION,
            )
            .order_by(DailyProductMetric.trade_date)
        )
        if range_key != "all":
            latest_date = session.scalar(
                select(func.max(DailyProductMetric.trade_date)).where(
                    DailyProductMetric.family_id == family.id,
                    DailyProductMetric.scope_key == scope_key,
                    DailyProductMetric.calculation_version == CALCULATION_VERSION,
                    DailyProductMetric.classification_version
                    == CLASSIFICATION_VERSION,
                )
            )
            if latest_date is not None:
                statement = statement.where(
                    DailyProductMetric.trade_date
                    >= latest_date - timedelta(days=RANGE_DAYS[range_key] - 1)
                )
        metrics = list(session.execute(statement).scalars())
        market_code = None if market == "all" else market
        return ProductHistoryResponse(
            product=_identity(family),
            scope=ScopeInfo(
                key=scope_key,
                type="all_reporting_markets" if market == "all" else "market",
                market_code=market_code,
                market_count=(metrics[-1].market_count if metrics else 0),
            ),
            range=range_key,
            points=[
                HistoryPoint(
                    trade_date=metric.trade_date,
                    weighted_avg_price=metric.weighted_avg_price,
                    total_volume_kg=metric.total_volume_kg,
                    market_count=metric.market_count,
                    ma_7d=metric.ma_7d,
                    ma_30d=metric.ma_30d,
                    ma_90d=metric.ma_90d,
                    percentile_365d=metric.percentile_365d,
                    classification=metric.classification,
                )
                for metric in metrics
            ],
        )

    def movers(
        self,
        session: Session,
        *,
        direction: str,
        period: str,
        limit: int,
    ) -> MoversResponse:
        families = {
            family.id: family
            for family in session.execute(select(ProductFamily)).scalars()
        }
        latest = self._latest_by_family(session)
        global_latest_date = max(
            (metric.trade_date for metric in latest.values()), default=None
        )
        items: list[MoverItem] = []
        for family_id, metric in latest.items():
            if (
                global_latest_date is not None
                and metric.trade_date < global_latest_date - timedelta(days=7)
            ):
                continue
            change = metric.wow_change_pct if period == "7d" else metric.mom_change_pct
            if change is None:
                continue
            if direction == "up" and change <= Decimal(0):
                continue
            if direction == "down" and change >= Decimal(0):
                continue
            items.append(
                MoverItem(
                    product=_identity(families[family_id]),
                    as_of=metric.trade_date,
                    change_pct=change,
                    current_price=metric.weighted_avg_price,
                    classification=metric.classification,
                    market_count=metric.market_count,
                )
            )
        items.sort(key=lambda item: item.change_pct, reverse=direction == "up")
        return MoversResponse(
            direction=direction,
            period=period,
            items=items[:limit],
        )

    def _latest_by_family(self, session: Session) -> dict[int, DailyProductMetric]:
        latest_dates = (
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
        metrics = session.execute(
            select(DailyProductMetric).join(
                latest_dates,
                (DailyProductMetric.family_id == latest_dates.c.family_id)
                & (DailyProductMetric.trade_date == latest_dates.c.latest_date),
            )
            .where(
                DailyProductMetric.scope_key == ALL_MARKETS_SCOPE,
                DailyProductMetric.calculation_version == CALCULATION_VERSION,
                DailyProductMetric.classification_version == CLASSIFICATION_VERSION,
            )
        ).scalars()
        return {metric.family_id: metric for metric in metrics}

    @staticmethod
    def _resolve_family(session: Session, product_key: str) -> ProductFamily:
        normalized = normalize_alias(product_key)
        family = session.execute(
            select(ProductFamily)
            .outerjoin(ProductAlias, ProductAlias.family_id == ProductFamily.id)
            .where(
                ProductFamily.active.is_(True),
                or_(
                    ProductFamily.slug == product_key,
                    ProductFamily.canonical_name == product_key,
                    (
                        (ProductAlias.normalized_alias == normalized)
                        & ProductAlias.active.is_(True)
                    ),
                ),
            )
            .limit(1)
        ).scalar_one_or_none()
        if family is None:
            raise AnalyticsNotFoundError(f"Unknown product {product_key!r}")
        return family


def _identity(family: ProductFamily) -> ProductIdentity:
    return ProductIdentity(
        slug=family.slug,
        canonical_name=family.canonical_name,
        display_name=family.display_name,
        category=family.category,
    )


def _summary(
    family: ProductFamily, metric: DailyProductMetric
) -> PriceSummaryResponse:
    market_code = (
        metric.scope_key.removeprefix("market:")
        if metric.scope_key.startswith("market:")
        else None
    )
    warnings = []
    if metric.classification == "insufficient_data":
        warnings.append(
            "Historical coverage is below 120 available trading days; "
            "no price-level label is assigned."
        )
    return PriceSummaryResponse(
        as_of=metric.trade_date,
        product=_identity(family),
        scope=ScopeInfo(
            key=metric.scope_key,
            type=(
                "all_reporting_markets"
                if metric.scope_key == ALL_MARKETS_SCOPE
                else "market"
            ),
            market_code=market_code,
            market_count=metric.market_count,
        ),
        included_source_product_codes=metric.included_product_codes,
        metrics=MetricValues(
            current_price=metric.weighted_avg_price,
            ma_7d=metric.ma_7d,
            ma_30d=metric.ma_30d,
            ma_90d=metric.ma_90d,
            wow_change_pct=metric.wow_change_pct,
            mom_change_pct=metric.mom_change_pct,
            percentile_365d=metric.percentile_365d,
            z_score_365d=metric.z_score_365d,
            robust_z_365d=metric.robust_z_365d,
            historical_high_price=metric.historical_high_price,
            historical_high_date=metric.historical_high_date,
            historical_low_price=metric.historical_low_price,
            historical_low_date=metric.historical_low_date,
            total_volume_kg=metric.total_volume_kg,
            volume_change_pct=metric.volume_change_pct,
            volatility_30d=metric.volatility_30d,
            history_day_count=metric.history_day_count,
        ),
        classification=ClassificationInfo(
            label=metric.classification,
            version=metric.classification_version,
        ),
        calculation_version=metric.calculation_version,
        computed_at=metric.computed_at,
        warnings=warnings,
    )
