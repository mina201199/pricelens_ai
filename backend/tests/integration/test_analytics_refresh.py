import hashlib
import os
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from price_lens.ai.text2sql.executor import Text2SqlExecutor
from price_lens.ai.text2sql.validator import SqlValidator
from price_lens.analytics.calculator import ALL_MARKETS_SCOPE
from price_lens.analytics.refresh import AnalyticsRefresher
from price_lens.api.app import app
from price_lens.config import Settings, get_settings
from price_lens.db.models import (
    DailyProductMetric,
    OfficialDocument,
    OfficialDocumentChunk,
    ProductFamily,
)
from price_lens.db.session import get_db_session
from price_lens.ingestion.jobs.market_etl import MarketEtlJob
from price_lens.ingestion.sources.moa import OfficialMarket
from price_lens.rag.documents import embed_text, ingest_url

pytestmark = pytest.mark.integration


def _record(
    *,
    crop_code: str,
    crop_name: str,
    market_code: str,
    market_name: str,
    average_price: int,
    volume: int,
) -> dict[str, object]:
    return {
        "TransDate": "115.09.24",
        "TcType": "N04",
        "CropCode": crop_code,
        "CropName": crop_name,
        "MarketCode": market_code,
        "MarketName": market_name,
        "Upper_Price": average_price + 2,
        "Middle_Price": average_price,
        "Lower_Price": average_price - 2,
        "Avg_Price": average_price,
        "Trans_Quantity": volume,
    }


SAMPLES = [
    _record(
        crop_code="LA1",
        crop_name="甘藍-初秋",
        market_code="109",
        market_name="台北一",
        average_price=10,
        volume=100,
    ),
    _record(
        crop_code="LA2",
        crop_name="甘藍-改良種",
        market_code="104",
        market_name="台北二",
        average_price=20,
        volume=300,
    ),
    _record(
        crop_code="A1",
        crop_name="香蕉",
        market_code="109",
        market_name="台北一",
        average_price=30,
        volume=200,
    ),
]


class FakeMoaClient:
    async def fetch_official_markets(self) -> list[OfficialMarket]:
        return [
            OfficialMarket(code="109", name="台北一"),
            OfficialMarket(code="104", name="台北二"),
        ]

    async def fetch_transactions(self, start, end, markets=None):
        return SAMPLES


@pytest.fixture(scope="module")
def analytics_database():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    parsed = make_url(url)
    if not parsed.database or not parsed.database.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL database name must end with _test")

    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS rag CASCADE"))
        connection.execute(text("DROP SCHEMA IF EXISTS analytics CASCADE"))
        connection.execute(text("DROP SCHEMA IF EXISTS raw CASCADE"))
        connection.execute(text("DROP SCHEMA IF EXISTS core CASCADE"))
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    engine.dispose()

    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    backend_dir = Path(__file__).resolve().parents[2]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "migrations"))
    command.upgrade(config, "head")

    yield url

    if previous_url is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous_url
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_weighted_refresh_and_typed_api(analytics_database: str) -> None:
    engine = create_engine(analytics_database)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(database_url=analytics_database)
    job = MarketEtlJob(settings, factory, client=FakeMoaClient())
    await job.run(date(2026, 9, 24), date(2026, 9, 24), job_type="analytics-test")

    with factory.begin() as session:
        result = AnalyticsRefresher().refresh(session)
    assert result == {
        "source_daily_aggregates": 5,
        "series_count": 5,
        "metrics_written": 5,
    }
    with factory.begin() as session:
        assert AnalyticsRefresher().refresh(session) == result

    with factory() as session:
        metric = session.scalar(
            select(DailyProductMetric)
            .join(ProductFamily, ProductFamily.id == DailyProductMetric.family_id)
            .where(
                DailyProductMetric.scope_key == ALL_MARKETS_SCOPE,
                ProductFamily.slug == "cabbage",
            )
        )
        assert metric is not None
        assert metric.weighted_avg_price == Decimal("17.5000")
        assert metric.total_volume_kg == Decimal("400.00")
        assert metric.market_count == 2
        assert metric.product_count == 2
        assert metric.included_product_codes == ["LA1", "LA2"]
        assert metric.classification == "insufficient_data"

    with factory.begin() as session:
        latest_metrics = {
            slug: metric
            for slug, metric in session.execute(
                select(ProductFamily.slug, DailyProductMetric)
                .join(
                    DailyProductMetric,
                    DailyProductMetric.family_id == ProductFamily.id,
                )
                .where(DailyProductMetric.scope_key == ALL_MARKETS_SCOPE)
            )
        }
        latest_metrics["cabbage"].wow_change_pct = Decimal("10")
        latest_metrics["banana"].wow_change_pct = Decimal("-5")

    def override_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    try:
        client = TestClient(app)
        products = client.get("/api/v1/products")
        assert products.status_code == 200
        assert any(item["slug"] == "cabbage" for item in products.json())

        summary = client.get("/api/v1/products/cabbage/summary")
        assert summary.status_code == 200
        payload = summary.json()
        assert payload["unit"] == "TWD/kg wholesale"
        assert payload["metrics"]["current_price"] == "17.5000"
        assert payload["classification"]["label"] == "insufficient_data"
        assert payload["scope"]["market_count"] == 2

        alias_summary = client.get("/api/v1/products/高麗菜/summary")
        assert alias_summary.status_code == 200

        history = client.get(
            "/api/v1/products/cabbage/history",
            params={"range": "1y", "market": "all"},
        )
        assert history.status_code == 200
        assert len(history.json()["points"]) == 1

        movers_up = client.get("/api/v1/movers", params={"direction": "up"})
        assert [item["product"]["slug"] for item in movers_up.json()["items"]] == [
            "cabbage"
        ]
        movers_down = client.get("/api/v1/movers", params={"direction": "down"})
        assert [
            item["product"]["slug"] for item in movers_down.json()["items"]
        ] == ["banana"]

        missing = client.get("/api/v1/products/not-a-product/summary")
        assert missing.status_code == 404

        ask = client.post("/api/v1/ask", json={"question": "高麗菜現在算貴嗎？"})
        assert ask.status_code == 200
        assert ask.json()["route"] == "typed_analytics"
        assert ask.json()["as_of"] == "2026-09-24"
        assert ask.json()["unit"] == "TWD/kg wholesale"
        assert ask.json()["scope"]["market_count"] == 2

        reason = client.post("/api/v1/ask", json={"question": "高麗菜為什麼變貴？"})
        assert reason.status_code == 200
        assert "沒有時間與品項相符的官方文件" in reason.json()["answer"]
        assert reason.json()["warnings"]

        with factory.begin() as session:
            product_name = session.scalar(
                select(ProductFamily.display_name).where(ProductFamily.slug == "cabbage")
            )
            document = OfficialDocument(
                publisher="農業部農糧署",
                title="高麗菜產地供應說明",
                source_url="https://www.afa.gov.tw/news/phase5-test",
                published_at=date(2026, 9, 20),
                retrieved_at=datetime.now(UTC),
                content_hash="a" * 64,
                product_slugs=["cabbage"],
                event_start=date(2026, 9, 18),
                event_end=date(2026, 9, 24),
                metadata_json={},
            )
            session.add(document)
            session.flush()
            session.add(
                OfficialDocumentChunk(
                    document_id=document.id,
                    chunk_index=0,
                    content="高麗菜供應與產地採收受到天候影響。",
                    embedding=embed_text(f"{product_name} 高麗菜為什麼變貴？"),
                )
            )

        grounded_reason = client.post(
            "/api/v1/ask", json={"question": "高麗菜為什麼變貴？"}
        )
        assert grounded_reason.status_code == 200
        factors = grounded_reason.json()["possible_factors"]
        assert len(factors) == 1
        assert factors[0]["statement"] == "高麗菜供應與產地採收受到天候影響。"
        assert factors[0]["evidence"]["published_at"] == "2026-09-20"
        assert factors[0]["evidence"]["source_url"].startswith("https://www.afa.gov.tw/")
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_text2sql_role_is_database_enforced_read_only(
    analytics_database: str,
) -> None:
    admin_url = make_url(analytics_database)
    password = "test-only-text2sql-password"
    with psycopg.connect(
        host=admin_url.host,
        port=admin_url.port,
        dbname=admin_url.database,
        user=admin_url.username,
        password=admin_url.password,
        autocommit=True,
    ) as connection:
        connection.execute(
            sql.SQL("ALTER ROLE price_lens_text2sql WITH LOGIN PASSWORD {}").format(
                sql.Literal(password)
            )
        )

    readonly_url: URL = admin_url.set(
        username="price_lens_text2sql",
        password=password,
    )
    executor = Text2SqlExecutor(
        readonly_url.render_as_string(hide_password=False),
        statement_timeout_ms=2000,
        lock_timeout_ms=500,
        max_explain_cost=100000,
    )
    query = SqlValidator(max_rows=10).validate(
        "SELECT product_slug, current_price_twd_per_kg "
        "FROM analytics.v_latest_product_status ORDER BY current_price_twd_per_kg DESC"
    )
    result = executor.execute(query)
    assert result.rows
    assert len(result.rows) <= 10

    with executor.engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SHOW default_transaction_read_only"
        ).scalar_one() == "on"
        with pytest.raises(DBAPIError):
            connection.exec_driver_sql("DELETE FROM analytics.daily_product_metrics")
        connection.rollback()
        with pytest.raises(DBAPIError):
            connection.exec_driver_sql("CREATE TABLE public.forbidden_write (id int)")
        connection.rollback()
    executor.engine.dispose()


def test_document_reingest_refreshes_metadata_without_duplicate_chunks(
    analytics_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = "高麗菜供應說明。" * 30
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    monkeypatch.setattr(
        "price_lens.rag.documents.fetch_official_document",
        lambda _: ("更新標題", content),
    )
    engine = create_engine(analytics_database)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    url = "https://www.afa.gov.tw/news/idempotent-test"

    with factory.begin() as session:
        product_name = session.scalar(
            select(ProductFamily.display_name).where(ProductFamily.slug == "cabbage")
        )
        document = OfficialDocument(
            publisher="舊 publisher",
            title="舊標題",
            source_url=url,
            published_at=date(2026, 9, 19),
            retrieved_at=datetime.now(UTC),
            content_hash=content_hash,
            product_slugs=["tomato"],
            event_start=date(2026, 9, 1),
            event_end=date(2026, 9, 10),
            metadata_json={},
        )
        session.add(document)
        session.flush()
        session.add(
            OfficialDocumentChunk(
                document_id=document.id,
                chunk_index=0,
                content=content,
                embedding=embed_text(f"{product_name} 新供應說明"),
            )
        )

    with factory.begin() as session:
        document, inserted = ingest_url(
            session,
            url,
            published_at=date(2026, 9, 20),
            event_start=date(2026, 9, 18),
            event_end=date(2026, 9, 24),
            product_slugs=["cabbage"],
        )
        assert not inserted
        assert document.publisher == "農業部農糧署"
        assert document.title == "更新標題"
        assert document.product_slugs == ["cabbage"]
        assert document.published_at == date(2026, 9, 20)

    with factory() as session:
        chunks = session.scalars(
            select(OfficialDocumentChunk).where(OfficialDocumentChunk.document_id == document.id)
        ).all()
        assert len(chunks) == 1
    engine.dispose()
