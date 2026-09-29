import os
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from price_lens.config import Settings, get_settings
from price_lens.db.models import (
    IngestionRun,
    MarketPriceObservation,
    ProductAlias,
    ProductFamily,
    RawMarketRecord,
)
from price_lens.ingestion.jobs.market_etl import MarketEtlJob
from price_lens.ingestion.sources.moa import OfficialMarket

pytestmark = pytest.mark.integration


SAMPLE = {
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


class FakeMoaClient:
    async def fetch_official_markets(self) -> list[OfficialMarket]:
        return [OfficialMarket(code="109", name="台北一")]

    async def fetch_transactions(self, start, end, markets=None):
        return [SAMPLE]


class FailingMoaClient:
    async def fetch_official_markets(self) -> list[OfficialMarket]:
        raise RuntimeError("official API unavailable")


@pytest.fixture(scope="module")
def postgres_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    parsed = make_url(url)
    if not parsed.database or not parsed.database.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL database name must end with _test")
    return url


@pytest.fixture(scope="module")
def migrated_database(postgres_url: str):
    engine = create_engine(postgres_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS rag CASCADE"))
        connection.execute(text("DROP SCHEMA IF EXISTS analytics CASCADE"))
        connection.execute(text("DROP SCHEMA IF EXISTS raw CASCADE"))
        connection.execute(text("DROP SCHEMA IF EXISTS core CASCADE"))
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    engine.dispose()

    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = postgres_url
    get_settings.cache_clear()
    backend_dir = Path(__file__).resolve().parents[2]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "migrations"))
    command.upgrade(config, "head")
    yield postgres_url
    if previous_url is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous_url
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_repeated_load_is_idempotent(migrated_database: str) -> None:
    engine = create_engine(migrated_database)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(database_url=migrated_database)
    job = MarketEtlJob(settings, factory, client=FakeMoaClient())

    first = await job.run(date(2026, 9, 24), date(2026, 9, 24), job_type="test")

    with factory.begin() as session:
        cabbage_id = session.scalar(
            select(ProductFamily.id).where(ProductFamily.canonical_name == "甘藍")
        )
        session.add(
            ProductAlias(
                family_id=cabbage_id,
                alias="已移除別名",
                normalized_alias="已移除別名",
                locale="zh-TW",
                source="manual",
                priority=999,
                active=True,
            )
        )

    second = await job.run(date(2026, 9, 24), date(2026, 9, 24), job_type="test")

    assert first.records_inserted == 1
    assert second.records_inserted == 0
    assert second.records_updated == 0
    assert second.records_unchanged == 1

    with factory() as session:
        assert session.scalar(select(func.count(MarketPriceObservation.id))) == 1
        assert session.scalar(select(func.count(RawMarketRecord.id))) == 1
        assert session.scalar(
            select(func.count(IngestionRun.id)).where(IngestionRun.job_type == "test")
        ) == 2
        assert session.scalar(
            select(ProductAlias.active).where(
                ProductAlias.normalized_alias == "已移除別名"
            )
        ) is False
    engine.dispose()


@pytest.mark.asyncio
async def test_failed_source_call_is_recorded(migrated_database: str) -> None:
    engine = create_engine(migrated_database)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(database_url=migrated_database)
    job = MarketEtlJob(settings, factory, client=FailingMoaClient())

    with pytest.raises(RuntimeError, match="official API unavailable"):
        await job.run(
            date(2026, 9, 24),
            date(2026, 9, 24),
            job_type="test-failure",
        )

    with factory() as session:
        failed_run = session.scalar(
            select(IngestionRun).where(IngestionRun.job_type == "test-failure")
        )
        assert failed_run is not None
        assert failed_run.status == "failed"
        assert failed_run.finished_at is not None
        assert failed_run.error_summary == "official API unavailable"
    engine.dispose()
