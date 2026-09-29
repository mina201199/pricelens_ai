import logging
import os
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from price_lens import __version__
from price_lens.config import Settings
from price_lens.db.models import IngestionRun
from price_lens.ingestion.loader import (
    LoadCounts,
    MarketDataLoader,
    ensure_data_source,
    seed_product_mapping,
)
from price_lens.ingestion.mapping import ProductMappingRegistry
from price_lens.ingestion.normalize import inclusive_dates
from price_lens.ingestion.sources.moa import MoaApiClient

logger = logging.getLogger(__name__)


class MarketEtlJob:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        *,
        client: MoaApiClient | None = None,
        registry: ProductMappingRegistry | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.registry = registry or ProductMappingRegistry.load_default()
        self.client = client or MoaApiClient(
            settings.moa_api_base_url,
            timeout_seconds=settings.moa_request_timeout_seconds,
            max_concurrency=settings.moa_max_concurrency,
            max_retries=settings.moa_max_retries,
        )
        self.loader = MarketDataLoader(self.registry)

    async def run(
        self,
        start: date,
        end: date,
        *,
        job_type: str = "manual",
        mapped_products_only: bool = False,
    ) -> IngestionRun:
        if end < start:
            raise ValueError("end date must not be before start date")

        run_id, source_id = self._start_run(
            start, end, job_type, mapped_products_only=mapped_products_only
        )
        totals = LoadCounts()
        try:
            markets = None
            if not mapped_products_only:
                markets = await self.client.fetch_official_markets()
            for chunk_start in inclusive_dates(start, end)[
                :: self.settings.moa_etl_chunk_days
            ]:
                chunk_end = min(
                    chunk_start + timedelta(days=self.settings.moa_etl_chunk_days - 1),
                    end,
                )
                if mapped_products_only:
                    payloads = await self.client.fetch_product_codes(
                        chunk_start,
                        chunk_end,
                        sorted(self.registry.mapped_codes),
                    )
                else:
                    payloads = await self.client.fetch_transactions(
                        chunk_start, chunk_end, markets=markets
                    )
                with self.session_factory.begin() as session:
                    daily_counts = self.loader.load(
                        session,
                        source_id=source_id,
                        ingestion_run_id=run_id,
                        payloads=payloads,
                    )
                totals += daily_counts
                self._update_progress(run_id, totals)
            return self._finish_run(run_id, totals, status="succeeded")
        except Exception as exc:
            logger.exception("market_etl_failed", extra={"ingestion_run_id": run_id})
            self._finish_run(run_id, totals, status="failed", error_summary=str(exc))
            raise

    def _start_run(
        self,
        start: date,
        end: date,
        job_type: str,
        *,
        mapped_products_only: bool,
    ) -> tuple[int, int]:
        with self.session_factory.begin() as session:
            source = ensure_data_source(session, self.settings.moa_api_base_url)
            seed_product_mapping(session, self.registry)
            run = IngestionRun(
                source_id=source.id,
                job_type=job_type,
                window_start=start,
                window_end=end,
                request_params={
                    "partitioning": (
                        "adaptive_date_window_per_mapped_product_code"
                        if mapped_products_only
                        else "adaptive_date_window_per_official_market_name"
                    ),
                    "data_scope": (
                        "mapped_mvp_products_only"
                        if mapped_products_only
                        else "all_products_in_official_vegetable_and_fruit_markets"
                    ),
                    "market_types": (
                        [] if mapped_products_only else ["Veg", "Fruit"]
                    ),
                    "product_code_count": (
                        len(self.registry.mapped_codes) if mapped_products_only else None
                    ),
                    "chunk_days": self.settings.moa_etl_chunk_days,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                },
                status="running",
                code_version=os.getenv("PRICE_LENS_CODE_VERSION", __version__),
            )
            session.add(run)
            session.flush()
            run_id = run.id
            source_id = source.id
        logger.info(
            "market_etl_started",
            extra={
                "ingestion_run_id": run_id,
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
            },
        )
        return run_id, source_id

    def _update_progress(self, run_id: int, counts: LoadCounts) -> None:
        with self.session_factory.begin() as session:
            run = session.get(IngestionRun, run_id)
            if run is None:
                raise RuntimeError(f"Ingestion run {run_id} disappeared")
            _apply_counts(run, counts)

    def _finish_run(
        self,
        run_id: int,
        counts: LoadCounts,
        *,
        status: str,
        error_summary: str | None = None,
    ) -> IngestionRun:
        with self.session_factory.begin() as session:
            run = session.get(IngestionRun, run_id)
            if run is None:
                raise RuntimeError(f"Ingestion run {run_id} disappeared")
            _apply_counts(run, counts)
            run.status = status
            run.finished_at = datetime.now(UTC)
            run.error_summary = error_summary[:2000] if error_summary else None
        with self.session_factory() as session:
            completed = session.get(IngestionRun, run_id)
            assert completed is not None
            session.expunge(completed)
        logger.info(
            "market_etl_finished",
            extra={"ingestion_run_id": run_id, "status": status, **counts.__dict__},
        )
        return completed


def _apply_counts(run: IngestionRun, counts: LoadCounts) -> None:
    run.records_received = counts.received
    run.records_inserted = counts.inserted
    run.records_updated = counts.updated
    run.records_unchanged = counts.unchanged
    run.records_excluded = counts.excluded
    run.records_quarantined = counts.quarantined
