from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from price_lens.schemas.analytics import (
    ClassificationInfo,
    MetricValues,
    ProductIdentity,
    ScopeInfo,
)


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class AnswerEvidence(BaseModel):
    publisher: str
    title: str
    source_url: str
    as_of: date | None = None
    published_at: date | None = None
    event_start: date | None = None
    event_end: date | None = None
    document_id: int | None = None


class PossibleFactor(BaseModel):
    statement: str
    evidence: AnswerEvidence


class AnswerMethod(BaseModel):
    route: Literal["typed_analytics", "text2sql", "fallback"]
    intent: str
    provider: str
    model: str
    version: str


class AnswerRow(BaseModel):
    model_config = {"extra": "allow"}


class AskResponse(BaseModel):
    answer: str
    route: Literal["typed_analytics", "text2sql", "fallback"]
    as_of: date | None = None
    unit: Literal["TWD/kg wholesale"] = "TWD/kg wholesale"
    price_semantics: Literal["wholesale market transaction price"] = (
        "wholesale market transaction price"
    )
    product: ProductIdentity | None = None
    scope: ScopeInfo | None = None
    metrics: MetricValues | None = None
    classification: ClassificationInfo | None = None
    data: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[AnswerEvidence]
    possible_factors: list[PossibleFactor] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    trace_id: str
    method: AnswerMethod


def json_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: str(value) if isinstance(value, Decimal) else value
        for key, value in row.items()
    }
