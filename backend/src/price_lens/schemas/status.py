from datetime import date, datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    database: str


class DataStatusResponse(BaseModel):
    dataset: str
    publisher: str
    price_semantics: str
    unit: str
    observation_count: int
    earliest_trade_date: date | None
    latest_trade_date: date | None
    product_count: int
    market_count: int
    latest_successful_ingestion_at: datetime | None
    analytics_metric_count: int
    analytics_latest_trade_date: date | None
    analytics_last_computed_at: datetime | None
    analytics_calculation_version: str
    analytics_classification_version: str
