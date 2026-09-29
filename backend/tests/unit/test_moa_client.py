from datetime import date

import httpx
import pytest

from price_lens.ingestion.sources.moa import (
    MoaApiClient,
    MoaApiError,
    MoaApiTruncationError,
    OfficialMarket,
)


def _record(
    market_name: str = "台北一",
    market_code: str = "109",
    trans_date: str = "115.09.24",
    crop_code: str = "LA1",
) -> dict[str, object]:
    return {
        "TransDate": trans_date,
        "TcType": "N04",
        "CropCode": crop_code,
        "CropName": "甘藍-初秋",
        "MarketCode": market_code,
        "MarketName": market_name,
        "Upper_Price": 50.0,
        "Middle_Price": 30.0,
        "Lower_Price": 20.0,
        "Avg_Price": 32.0,
        "Trans_Quantity": 1000.0,
    }


@pytest.mark.asyncio
async def test_fetch_market_day_builds_partitioned_query() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/AgriProductsTransType/")
        assert request.url.params["Start_time"] == "115.09.24"
        assert request.url.params["End_time"] == "115.09.24"
        assert request.url.params["MarketName"] == "台北一"
        return httpx.Response(200, json={"RS": "OK", "Data": [_record()], "Next": False})

    client = MoaApiClient(
        "https://data.moa.gov.tw/api/v1",
        transport=httpx.MockTransport(handler),
    )
    rows = await client.fetch_transactions(
        date(2026, 9, 24),
        date(2026, 9, 24),
        markets=[OfficialMarket(code="109", name="台北一")],
    )
    assert rows == [_record()]


@pytest.mark.asyncio
async def test_next_true_is_rejected_as_truncated() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"RS": "OK", "Data": [_record()], "Next": True})

    client = MoaApiClient(
        "https://data.moa.gov.tw/api/v1",
        max_retries=1,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(MoaApiTruncationError):
        await client.fetch_transactions(
            date(2026, 9, 24),
            date(2026, 9, 24),
            markets=[OfficialMarket(code="109", name="台北一")],
        )


@pytest.mark.asyncio
async def test_api_error_envelope_is_retried_then_raised() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"RS": "ERROR", "MSG": "temporary"})

    client = MoaApiClient(
        "https://data.moa.gov.tw/api/v1",
        max_retries=2,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(MoaApiError):
        await client.fetch_transactions(
            date(2026, 9, 24),
            date(2026, 9, 24),
            markets=[OfficialMarket(code="109", name="台北一")],
        )
    assert calls == 2


@pytest.mark.asyncio
async def test_reference_and_transaction_market_code_may_differ() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"RS": "OK", "Data": [_record("台北市場", "105")], "Next": False},
        )

    client = MoaApiClient(
        "https://data.moa.gov.tw/api/v1",
        transport=httpx.MockTransport(handler),
    )
    rows = await client.fetch_transactions(
        date(2026, 9, 24),
        date(2026, 9, 24),
        markets=[OfficialMarket(code="100", name="台北市")],
    )
    assert rows[0]["MarketCode"] == "105"


@pytest.mark.asyncio
async def test_market_partition_with_multiple_codes_is_rejected() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "RS": "OK",
                "Data": [_record("台北一", "109"), _record("台北二", "104")],
                "Next": False,
            },
        )

    client = MoaApiClient(
        "https://data.moa.gov.tw/api/v1",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(MoaApiError, match="multiple or missing MarketCode"):
        await client.fetch_transactions(
            date(2026, 9, 24),
            date(2026, 9, 24),
            markets=[OfficialMarket(code="100", name="台北市")],
        )


@pytest.mark.asyncio
async def test_next_true_date_window_is_split_until_complete() -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        start = request.url.params["Start_time"]
        end = request.url.params["End_time"]
        calls.append((start, end))
        if start != end:
            return httpx.Response(200, json={"RS": "OK", "Data": [], "Next": True})
        return httpx.Response(
            200,
            json={"RS": "OK", "Data": [_record(trans_date=start)], "Next": False},
        )

    client = MoaApiClient(
        "https://data.moa.gov.tw/api/v1",
        transport=httpx.MockTransport(handler),
    )
    rows = await client.fetch_transactions(
        date(2026, 9, 23),
        date(2026, 9, 24),
        markets=[OfficialMarket(code="109", name="台北一")],
    )

    assert len(rows) == 2
    assert calls == [
        ("115.09.23", "115.09.24"),
        ("115.09.23", "115.09.23"),
        ("115.09.24", "115.09.24"),
    ]


@pytest.mark.asyncio
async def test_product_code_partition_is_exact() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["CropCode"] == "LA1"
        return httpx.Response(200, json={"RS": "OK", "Data": [_record()], "Next": False})

    client = MoaApiClient(
        "https://data.moa.gov.tw/api/v1",
        transport=httpx.MockTransport(handler),
    )
    rows = await client.fetch_product_codes(
        date(2026, 9, 24), date(2026, 9, 24), ["LA1"]
    )
    assert rows == [_record()]


@pytest.mark.asyncio
async def test_product_code_partition_rejects_unexpected_code() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "RS": "OK",
                "Data": [_record(crop_code="SW1")],
                "Next": False,
            },
        )

    client = MoaApiClient(
        "https://data.moa.gov.tw/api/v1",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(MoaApiError, match="CropCode partition was not exact"):
        await client.fetch_product_codes(
            date(2026, 9, 24), date(2026, 9, 24), ["LA1"]
        )
