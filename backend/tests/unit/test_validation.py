from copy import deepcopy

from price_lens.ingestion.validation.schemas import validate_market_record

VALID_RECORD = {
    "TransDate": "115.09.24",
    "TcType": "N04",
    "CropCode": "LA1",
    "CropName": "甘藍-初秋",
    "MarketCode": "109",
    "MarketName": "台北一",
    "Upper_Price": 50.0,
    "Middle_Price": 30.0,
    "Lower_Price": 20.0,
    "Avg_Price": 32.0,
    "Trans_Quantity": 1000.0,
}


def test_valid_record() -> None:
    result = validate_market_record(VALID_RECORD)
    assert result.status == "valid"
    assert result.record is not None
    assert result.record.trade_date.isoformat() == "2026-09-24"


def test_closure_is_audited_but_excluded() -> None:
    payload = deepcopy(VALID_RECORD)
    payload.update(
        {
            "CropCode": "rest",
            "CropName": "休市",
            "Upper_Price": 0,
            "Middle_Price": 0,
            "Lower_Price": 0,
            "Avg_Price": 0,
            "Trans_Quantity": 0,
        }
    )
    result = validate_market_record(payload)
    assert result.status == "excluded_closure"
    assert result.errors == []


def test_invalid_price_order_is_quarantined() -> None:
    payload = deepcopy(VALID_RECORD)
    payload["Middle_Price"] = 60
    result = validate_market_record(payload)
    assert result.status == "quarantined"
    assert any(error["type"] == "invalid_price_order" for error in result.errors)


def test_zero_volume_is_quarantined() -> None:
    payload = deepcopy(VALID_RECORD)
    payload["Trans_Quantity"] = 0
    result = validate_market_record(payload)
    assert result.status == "quarantined"
    assert any(error["type"] == "nonpositive_volume" for error in result.errors)


def test_missing_required_field_is_quarantined() -> None:
    payload = deepcopy(VALID_RECORD)
    del payload["Avg_Price"]
    result = validate_market_record(payload)
    assert result.status == "quarantined"
    assert result.record is None
