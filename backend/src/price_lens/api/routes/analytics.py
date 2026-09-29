from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from price_lens.analytics.service import (
    RANGE_DAYS,
    AnalyticsNotFoundError,
    AnalyticsService,
)
from price_lens.db.session import get_db_session
from price_lens.schemas.analytics import (
    MoversResponse,
    PriceSummaryResponse,
    ProductHistoryResponse,
    ProductListItem,
)

router = APIRouter(prefix="/api/v1", tags=["price analytics"])
DatabaseSession = Annotated[Session, Depends(get_db_session)]
service = AnalyticsService()


@router.get("/products", response_model=list[ProductListItem])
def products(session: DatabaseSession) -> list[ProductListItem]:
    return service.list_products(session)


@router.get("/radar", response_model=list[PriceSummaryResponse])
def radar(session: DatabaseSession) -> list[PriceSummaryResponse]:
    return service.radar(session)


@router.get("/movers", response_model=MoversResponse)
def movers(
    session: DatabaseSession,
    direction: Literal["up", "down"],
    period: Literal["7d", "30d"] = "7d",
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> MoversResponse:
    return service.movers(
        session,
        direction=direction,
        period=period,
        limit=limit,
    )


@router.get(
    "/products/{product_key}/summary",
    response_model=PriceSummaryResponse,
)
def product_summary(
    product_key: str, session: DatabaseSession
) -> PriceSummaryResponse:
    try:
        return service.summary(session, product_key)
    except AnalyticsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/products/{product_key}/history",
    response_model=ProductHistoryResponse,
)
def product_history(
    product_key: str,
    session: DatabaseSession,
    range_key: Annotated[
        Literal["1m", "3m", "6m", "1y", "2y", "all"],
        Query(alias="range"),
    ] = "1y",
    market: str = "all",
) -> ProductHistoryResponse:
    assert range_key == "all" or range_key in RANGE_DAYS
    try:
        return service.history(
            session,
            product_key,
            range_key=range_key,
            market=market,
        )
    except AnalyticsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
