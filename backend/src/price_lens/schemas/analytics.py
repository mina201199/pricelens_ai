from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class ProductIdentity(BaseModel):
    slug: str
    canonical_name: str
    display_name: str
    category: str


class ProductListItem(ProductIdentity):
    latest_available_trade_date: date | None
    latest_classification: str | None


class ScopeInfo(BaseModel):
    key: str
    type: Literal["all_reporting_markets", "market"]
    market_code: str | None = None
    market_count: int


class MetricValues(BaseModel):
    current_price: Decimal
    ma_7d: Decimal | None
    ma_30d: Decimal | None
    ma_90d: Decimal | None
    wow_change_pct: Decimal | None
    mom_change_pct: Decimal | None
    percentile_365d: Decimal | None
    z_score_365d: Decimal | None
    robust_z_365d: Decimal | None
    historical_high_price: Decimal | None
    historical_high_date: date | None
    historical_low_price: Decimal | None
    historical_low_date: date | None
    total_volume_kg: Decimal
    volume_change_pct: Decimal | None
    volatility_30d: Decimal | None
    history_day_count: int


class ClassificationInfo(BaseModel):
    label: str
    version: str


class PriceSummaryResponse(BaseModel):
    as_of: date
    product: ProductIdentity
    scope: ScopeInfo
    unit: Literal["TWD/kg wholesale"] = "TWD/kg wholesale"
    price_semantics: Literal["wholesale market transaction price"] = (
        "wholesale market transaction price"
    )
    included_source_product_codes: list[str]
    metrics: MetricValues
    classification: ClassificationInfo
    calculation_version: str
    computed_at: datetime
    source: str = "農業部農產品交易行情"
    warnings: list[str]


class HistoryPoint(BaseModel):
    trade_date: date
    weighted_avg_price: Decimal
    total_volume_kg: Decimal
    market_count: int
    ma_7d: Decimal | None
    ma_30d: Decimal | None
    ma_90d: Decimal | None
    percentile_365d: Decimal | None
    classification: str


class ProductHistoryResponse(BaseModel):
    product: ProductIdentity
    scope: ScopeInfo
    unit: Literal["TWD/kg wholesale"] = "TWD/kg wholesale"
    range: str
    points: list[HistoryPoint]


class MoverItem(BaseModel):
    product: ProductIdentity
    as_of: date
    change_pct: Decimal
    current_price: Decimal
    classification: str
    market_count: int


class MoversResponse(BaseModel):
    direction: Literal["up", "down"]
    period: Literal["7d", "30d"]
    unit: Literal["TWD/kg wholesale"] = "TWD/kg wholesale"
    items: list[MoverItem]

