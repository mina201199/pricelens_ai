import os
from datetime import date

import pytest

from price_lens.config import get_settings
from price_lens.ingestion.sources.moa import MoaApiClient
from price_lens.ingestion.validation.schemas import validate_market_record


@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_CONTRACT_TESTS") != "1",
    reason="set RUN_LIVE_CONTRACT_TESTS=1 to call the official API",
)
async def test_official_api_contract() -> None:
    settings = get_settings()
    client = MoaApiClient(
        settings.moa_api_base_url,
        timeout_seconds=settings.moa_request_timeout_seconds,
        max_concurrency=1,
        max_retries=settings.moa_max_retries,
    )
    markets = await client.fetch_official_markets()
    assert markets
    rows = await client.fetch_transactions(
        date(2026, 9, 24), date(2026, 9, 24), markets=markets[:1]
    )
    assert rows
    assert all(validate_market_record(row).record is not None for row in rows)

    cabbage_rows = await client.fetch_product_codes(
        date(2026, 9, 24), date(2026, 9, 24), ["LA1"]
    )
    assert cabbage_rows
    assert all(row["CropCode"] == "LA1" for row in cabbage_rows)
