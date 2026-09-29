from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from price_lens.ingestion.normalize import parse_roc_date


class MoaMarketRecord(BaseModel):
    """Validated shape of one AgriProductsTransType record."""

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False, str_strip_whitespace=True)

    transaction_date_roc: str = Field(alias="TransDate", min_length=8, max_length=10)
    category_code: str = Field(alias="TcType", min_length=1, max_length=30)
    source_product_code: str = Field(alias="CropCode", min_length=1, max_length=30)
    source_product_name: str = Field(alias="CropName", min_length=1)
    source_market_code: str = Field(alias="MarketCode", min_length=1, max_length=30)
    source_market_name: str = Field(alias="MarketName", min_length=1)
    upper_price: Decimal = Field(alias="Upper_Price")
    middle_price: Decimal = Field(alias="Middle_Price")
    lower_price: Decimal = Field(alias="Lower_Price")
    average_price: Decimal = Field(alias="Avg_Price")
    volume_kg: Decimal = Field(alias="Trans_Quantity")

    @field_validator(
        "source_product_code",
        "source_product_name",
        "source_market_code",
        "source_market_name",
        "category_code",
    )
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @property
    def trade_date(self) -> date:
        return parse_roc_date(self.transaction_date_roc)

    @property
    def is_closure(self) -> bool:
        return self.source_product_code.casefold() == "rest" or self.source_product_name == "休市"


ValidationStatus = Literal["valid", "excluded_closure", "quarantined"]


@dataclass(frozen=True)
class RecordValidationResult:
    status: ValidationStatus
    record: MoaMarketRecord | None
    errors: list[dict[str, Any]]


def validate_market_record(payload: dict[str, Any]) -> RecordValidationResult:
    try:
        record = MoaMarketRecord.model_validate(payload)
        _ = record.trade_date
    except (ValidationError, ValueError) as exc:
        errors = (
            exc.errors(include_url=False)
            if isinstance(exc, ValidationError)
            else [{"type": "invalid_roc_date", "msg": str(exc)}]
        )
        return RecordValidationResult("quarantined", None, errors)

    if record.is_closure:
        return RecordValidationResult("excluded_closure", record, [])

    errors: list[dict[str, Any]] = []
    price_fields = {
        "upper_price": record.upper_price,
        "middle_price": record.middle_price,
        "lower_price": record.lower_price,
        "average_price": record.average_price,
    }
    for field_name, value in price_fields.items():
        if value < 0:
            errors.append({"type": "negative_price", "field": field_name, "value": str(value)})

    if record.average_price <= 0:
        errors.append(
            {
                "type": "nonpositive_average_price",
                "field": "average_price",
                "value": str(record.average_price),
            }
        )
    if record.volume_kg <= 0:
        errors.append(
            {"type": "nonpositive_volume", "field": "volume_kg", "value": str(record.volume_kg)}
        )
    if record.lower_price > record.middle_price or record.middle_price > record.upper_price:
        errors.append(
            {
                "type": "invalid_price_order",
                "values": {
                    "lower": str(record.lower_price),
                    "middle": str(record.middle_price),
                    "upper": str(record.upper_price),
                },
            }
        )
    if not record.lower_price <= record.average_price <= record.upper_price:
        errors.append(
            {
                "type": "average_outside_range",
                "values": {
                    "lower": str(record.lower_price),
                    "average": str(record.average_price),
                    "upper": str(record.upper_price),
                },
            }
        )

    if errors:
        return RecordValidationResult("quarantined", record, errors)
    return RecordValidationResult("valid", record, [])
