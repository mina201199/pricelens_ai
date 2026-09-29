import logging
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from price_lens.analytics.calculator import (
    CALCULATION_VERSION,
    CLASSIFICATION_VERSION,
)
from price_lens.api.routes.analytics import router as analytics_router
from price_lens.api.routes.ask import router as ask_router
from price_lens.config import get_settings
from price_lens.db.models import (
    DailyProductMetric,
    IngestionRun,
    MarketPriceObservation,
)
from price_lens.db.session import get_db_session
from price_lens.logging_config import configure_logging
from price_lens.schemas.status import DataStatusResponse, HealthResponse


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging(get_settings().log_level)
    yield


app = FastAPI(
    title="Price Lens API",
    version="0.1.0",
    description=(
        "Data foundation for Taiwan agricultural wholesale market transactions. "
        "Prices are wholesale TWD/kg, not consumer retail quotes."
    ),
    lifespan=lifespan,
)
app.include_router(analytics_router)
app.include_router(ask_router)
logger = logging.getLogger(__name__)


@app.middleware("http")
async def request_observability(request: Request, call_next):
    request_id = uuid4().hex
    started = perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "http_request_complete",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((perf_counter() - started) * 1000, 2),
        },
    )
    return response

DatabaseSession = Annotated[Session, Depends(get_db_session)]


@app.get("/api/v1/health", response_model=HealthResponse)
def health(session: DatabaseSession) -> HealthResponse:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return HealthResponse(status="ok", database="ok")


@app.get("/api/v1/data-status", response_model=DataStatusResponse)
def data_status(session: DatabaseSession) -> DataStatusResponse:
    summary = session.execute(
        select(
            func.count(MarketPriceObservation.id),
            func.min(MarketPriceObservation.trade_date),
            func.max(MarketPriceObservation.trade_date),
            func.count(func.distinct(MarketPriceObservation.product_id)),
            func.count(func.distinct(MarketPriceObservation.market_id)),
        )
    ).one()
    latest_finished_at = session.execute(
        select(IngestionRun.finished_at)
        .where(IngestionRun.status == "succeeded")
        .order_by(IngestionRun.finished_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    analytics_summary = session.execute(
        select(
            func.count(DailyProductMetric.id),
            func.max(DailyProductMetric.trade_date),
            func.max(DailyProductMetric.computed_at),
        ).where(
            DailyProductMetric.calculation_version == CALCULATION_VERSION,
            DailyProductMetric.classification_version == CLASSIFICATION_VERSION,
        )
    ).one()
    return DataStatusResponse(
        dataset="農產品交易行情",
        publisher="農業部農糧署",
        price_semantics="wholesale market transaction price, not retail price",
        unit="TWD/kg wholesale",
        observation_count=summary[0],
        earliest_trade_date=summary[1],
        latest_trade_date=summary[2],
        product_count=summary[3],
        market_count=summary[4],
        latest_successful_ingestion_at=latest_finished_at,
        analytics_metric_count=analytics_summary[0],
        analytics_latest_trade_date=analytics_summary[1],
        analytics_last_computed_at=analytics_summary[2],
        analytics_calculation_version=CALCULATION_VERSION,
        analytics_classification_version=CLASSIFICATION_VERSION,
    )


@app.get("/", include_in_schema=False)
def root() -> dict[str, Any]:
    return {
        "service": "Price Lens API",
        "phase": 4,
        "data_semantics": "Taiwan agricultural wholesale market prices in TWD/kg",
        "docs": "/docs",
    }
