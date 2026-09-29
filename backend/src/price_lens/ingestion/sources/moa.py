import asyncio
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import httpx

from price_lens.ingestion.normalize import format_roc_date, parse_roc_date

logger = logging.getLogger(__name__)


class MoaApiError(RuntimeError):
    pass


class MoaApiTruncationError(MoaApiError):
    pass


@dataclass(frozen=True)
class OfficialMarket:
    code: str
    name: str


class MoaApiClient:
    """Async adapter for official Ministry of Agriculture v1 APIs.

    Unauthenticated callers cannot request page 2. Transaction extraction therefore
    partitions by one Gregorian day and one official vegetable/fruit market. Any
    remaining `Next=true` is treated as a hard error instead of silently truncating.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 30.0,
        max_concurrency: int = 5,
        max_retries: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._transport = transport

    async def fetch_official_markets(self) -> list[OfficialMarket]:
        markets: dict[str, OfficialMarket] = {}
        async with self._client() as client:
            for market_type in ("Veg", "Fruit"):
                envelope = await self._get_json(
                    client,
                    "/CropMarketType/",
                    {"CropMarketType": market_type},
                )
                self._assert_complete(envelope, context=f"market reference type={market_type}")
                for item in envelope.get("Data", []):
                    code = str(item.get("MarketCode", "")).strip()
                    name = str(item.get("MarketName", "")).strip()
                    if not code or not name:
                        raise MoaApiError(f"Market reference missing code/name: {item!r}")
                    # Vegetable and fruit reference lists overlap. MarketName is
                    # the only supported transaction filter, so it is the query
                    # partition key. The reference code is retained for audit but
                    # is not assumed to equal the transaction code: the official
                    # APIs currently disagree for at least one Taipei market.
                    markets.setdefault(name, OfficialMarket(code=code, name=name))
        return sorted(markets.values(), key=lambda market: market.name)

    async def fetch_transactions(
        self,
        start: date,
        end: date,
        markets: list[OfficialMarket] | None = None,
    ) -> list[dict[str, Any]]:
        official_markets = markets or await self.fetch_official_markets()
        tasks = [self._fetch_market_window(start, end, market) for market in official_markets]
        results = await asyncio.gather(*tasks)
        records = [record for batch in results for record in batch]
        logger.info(
            "moa_fetch_complete",
            extra={
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
                "market_partitions": len(tasks),
                "records_received": len(records),
            },
        )
        return records

    async def fetch_product_codes(
        self, start: date, end: date, product_codes: list[str]
    ) -> list[dict[str, Any]]:
        tasks = [
            self._fetch_product_window(start, end, product_code)
            for product_code in sorted(set(product_codes))
        ]
        results = await asyncio.gather(*tasks)
        records = [record for batch in results for record in batch]
        logger.info(
            "moa_product_fetch_complete",
            extra={
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
                "product_code_partitions": len(tasks),
                "records_received": len(records),
            },
        )
        return records

    async def _fetch_market_window(
        self, start: date, end: date, market: OfficialMarket
    ) -> list[dict[str, Any]]:
        params = {
            "Start_time": format_roc_date(start),
            "End_time": format_roc_date(end),
            "MarketName": market.name,
        }
        async with self._semaphore, self._client() as client:
            envelope = await self._get_json(client, "/AgriProductsTransType/", params)
        context = f"window={start.isoformat()}..{end.isoformat()} market={market.name}"
        if envelope.get("Next") is True:
            if start == end:
                raise MoaApiTruncationError(
                    f"Official API returned Next=true for {context}; "
                    "the smallest safe date partition is still truncated"
                )
            left_end = start + timedelta(days=(end - start).days // 2)
            right_start = left_end + timedelta(days=1)
            left, right = await asyncio.gather(
                self._fetch_market_window(start, left_end, market),
                self._fetch_market_window(right_start, end, market),
            )
            return left + right
        data = envelope.get("Data", [])
        if not isinstance(data, list):
            raise MoaApiError(f"Data is not a list for {context}")
        self._validate_market_partition(data, start, end, market, context)
        return data

    async def _fetch_product_window(
        self, start: date, end: date, product_code: str
    ) -> list[dict[str, Any]]:
        params = {
            "Start_time": format_roc_date(start),
            "End_time": format_roc_date(end),
            "CropCode": product_code,
        }
        async with self._semaphore, self._client() as client:
            envelope = await self._get_json(client, "/AgriProductsTransType/", params)
        context = f"window={start.isoformat()}..{end.isoformat()} product={product_code}"
        if envelope.get("Next") is True:
            if start == end:
                raise MoaApiTruncationError(
                    f"Official API returned Next=true for {context}; "
                    "the smallest safe date partition is still truncated"
                )
            left_end = start + timedelta(days=(end - start).days // 2)
            right_start = left_end + timedelta(days=1)
            left, right = await asyncio.gather(
                self._fetch_product_window(start, left_end, product_code),
                self._fetch_product_window(right_start, end, product_code),
            )
            return left + right
        data = envelope.get("Data", [])
        if not isinstance(data, list):
            raise MoaApiError(f"Data is not a list for {context}")
        unexpected_codes = {
            str(item.get("CropCode", "")).strip()
            for item in data
            if str(item.get("CropCode", "")).strip() != product_code
        }
        if unexpected_codes:
            raise MoaApiError(
                f"CropCode partition was not exact for {context}; "
                f"unexpected={sorted(unexpected_codes)}"
            )
        self._validate_dates(data, start, end, context)
        return data

    @staticmethod
    def _validate_market_partition(
        data: list[dict[str, Any]],
        start: date,
        end: date,
        market: OfficialMarket,
        context: str,
    ) -> None:
        codes_by_date: dict[str, set[str]] = {}
        for item in data:
            transaction_date = str(item.get("TransDate", "")).strip()
            codes_by_date.setdefault(transaction_date, set()).add(
                str(item.get("MarketCode", "")).strip()
            )
        invalid = {
            transaction_date: sorted(codes)
            for transaction_date, codes in codes_by_date.items()
            if "" in codes or len(codes) > 1
        }
        if invalid:
            raise MoaApiError(
                "MarketName partition returned multiple or missing MarketCode values "
                f"for {context}; reference_code={market.code!r} returned={invalid}"
            )
        MoaApiClient._validate_dates(data, start, end, context)

    @staticmethod
    def _validate_dates(
        data: list[dict[str, Any]], start: date, end: date, context: str
    ) -> None:
        for item in data:
            raw_date = str(item.get("TransDate", "")).strip()
            try:
                parsed = parse_roc_date(raw_date)
            except ValueError:
                continue
            if not start <= parsed <= end:
                raise MoaApiError(
                    f"Official API returned date {parsed.isoformat()} outside {context}"
                )

    async def _get_json(
        self, client: httpx.AsyncClient, path: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await client.get(path, params=params)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise MoaApiError("Official API response is not a JSON object")
                if payload.get("RS") != "OK":
                    raise MoaApiError(
                        f"Official API returned RS={payload.get('RS')!r}: {payload.get('MSG', '')}"
                    )
                return payload
            except (httpx.HTTPError, ValueError, MoaApiError) as exc:
                last_error = exc
                logger.warning(
                    "moa_request_failed",
                    extra={
                        "path": path,
                        "attempt": attempt,
                        "max_retries": self.max_retries,
                        "error_type": type(exc).__name__,
                    },
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
        raise MoaApiError(
            f"Official API request failed after {self.max_retries} attempts: {last_error}"
        ) from last_error

    @staticmethod
    def _assert_complete(envelope: dict[str, Any], *, context: str) -> None:
        if envelope.get("Next") is True:
            raise MoaApiTruncationError(
                f"Official API returned Next=true for {context}; refusing a truncated load"
            )

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout_seconds),
            follow_redirects=True,
            transport=self._transport,
            headers={"Accept": "application/json", "User-Agent": "Price-Lens/0.1"},
        )
