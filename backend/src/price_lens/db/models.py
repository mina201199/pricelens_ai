from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from price_lens.db.base import Base


class DataSource(Base):
    __tablename__ = "data_sources"
    __table_args__ = {"schema": "core"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    publisher: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_url: Mapped[str] = mapped_column(Text, nullable=False)
    api_url: Mapped[str] = mapped_column(Text, nullable=False)
    license_name: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="valid_status"),
        {"schema": "core"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("core.data_sources.id"), nullable=False, index=True
    )
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    request_params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    records_received: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    records_inserted: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    records_unchanged: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    records_excluded: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    records_quarantined: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_summary: Mapped[str | None] = mapped_column(Text)
    code_version: Mapped[str] = mapped_column(String(100), nullable=False)


class RawMarketRecord(Base):
    __tablename__ = "market_records"
    __table_args__ = (
        UniqueConstraint("source_id", "source_record_hash", name="source_record_hash"),
        CheckConstraint(
            "validation_status IN ('valid', 'excluded_closure', 'quarantined')",
            name="valid_validation_status",
        ),
        {"schema": "raw"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ingestion_run_id: Mapped[int] = mapped_column(
        ForeignKey("core.ingestion_runs.id"), nullable=False, index=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("core.data_sources.id"), nullable=False, index=True
    )
    source_record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(30), nullable=False)
    validation_errors: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )


class Market(Base):
    __tablename__ = "markets"
    __table_args__ = (
        UniqueConstraint("source_id", "source_market_code", name="source_market_code"),
        {"schema": "core"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("core.data_sources.id"), nullable=False)
    source_market_code: Mapped[str] = mapped_column(String(30), nullable=False)
    source_market_name: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProductFamily(Base):
    __tablename__ = "product_families"
    __table_args__ = {"schema": "core"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    default_include_imported: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    mapping_version: Mapped[str] = mapped_column(String(50), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ProductAlias(Base):
    __tablename__ = "product_aliases"
    __table_args__ = (
        UniqueConstraint("family_id", "normalized_alias", name="family_normalized_alias"),
        {"schema": "core"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    family_id: Mapped[int] = mapped_column(
        ForeignKey("core.product_families.id"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_alias: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(String(20), nullable=False, server_default="zh-TW")
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("source_id", "source_product_code", name="source_product_code"),
        CheckConstraint(
            "origin_type IN ('domestic', 'imported', 'unknown')", name="valid_origin_type"
        ),
        {"schema": "core"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("core.data_sources.id"), nullable=False)
    family_id: Mapped[int | None] = mapped_column(ForeignKey("core.product_families.id"))
    source_product_code: Mapped[str] = mapped_column(String(30), nullable=False)
    source_product_name: Mapped[str] = mapped_column(Text, nullable=False)
    category_code: Mapped[str] = mapped_column(String(30), nullable=False)
    variety: Mapped[str | None] = mapped_column(Text)
    origin_type: Mapped[str] = mapped_column(String(20), nullable=False)
    analytics_included: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    mapping_version: Mapped[str] = mapped_column(String(50), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketPriceObservation(Base):
    __tablename__ = "market_price_observations"
    __table_args__ = (
        UniqueConstraint("source_id", "trade_date", "market_id", "product_id", name="natural_key"),
        CheckConstraint("upper_price >= 0", name="upper_price_nonnegative"),
        CheckConstraint("middle_price >= 0", name="middle_price_nonnegative"),
        CheckConstraint("lower_price >= 0", name="lower_price_nonnegative"),
        CheckConstraint("average_price > 0", name="average_price_positive"),
        CheckConstraint("volume_kg > 0", name="volume_positive"),
        Index("ix_observations_product_trade_date", "product_id", "trade_date"),
        Index("ix_observations_market_trade_date", "market_id", "trade_date"),
        {"schema": "core"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("core.data_sources.id"), nullable=False)
    ingestion_run_id: Mapped[int] = mapped_column(
        ForeignKey("core.ingestion_runs.id"), nullable=False, index=True
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    market_id: Mapped[int] = mapped_column(ForeignKey("core.markets.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("core.products.id"), nullable=False)
    upper_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    middle_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    lower_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    average_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    volume_kg: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    source_record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DailyProductMetric(Base):
    __tablename__ = "daily_product_metrics"
    __table_args__ = (
        UniqueConstraint(
            "trade_date",
            "family_id",
            "scope_key",
            "calculation_version",
            "classification_version",
            name="versioned_natural_key",
        ),
        CheckConstraint("weighted_avg_price > 0", name="weighted_avg_price_positive"),
        CheckConstraint("total_volume_kg > 0", name="total_volume_positive"),
        CheckConstraint("market_count > 0", name="market_count_positive"),
        CheckConstraint("product_count > 0", name="product_count_positive"),
        Index("ix_daily_metrics_family_trade_date", "family_id", "trade_date"),
        Index("ix_daily_metrics_scope_trade_date", "scope_key", "trade_date"),
        {"schema": "analytics"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    family_id: Mapped[int] = mapped_column(
        ForeignKey("core.product_families.id"), nullable=False
    )
    scope_key: Mapped[str] = mapped_column(String(100), nullable=False)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("core.markets.id"))
    weighted_avg_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    total_volume_kg: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    market_count: Mapped[int] = mapped_column(Integer, nullable=False)
    product_count: Mapped[int] = mapped_column(Integer, nullable=False)
    included_product_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    ma_7d: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    ma_30d: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    ma_90d: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    wow_change_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    mom_change_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    percentile_365d: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    z_score_365d: Mapped[Decimal | None] = mapped_column(Numeric(12, 5))
    robust_z_365d: Mapped[Decimal | None] = mapped_column(Numeric(12, 5))
    historical_high_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    historical_high_date: Mapped[date | None] = mapped_column(Date)
    historical_low_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    historical_low_date: Mapped[date | None] = mapped_column(Date)
    volume_change_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    volatility_30d: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    history_day_count: Mapped[int] = mapped_column(Integer, nullable=False)
    classification: Mapped[str] = mapped_column(String(40), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(50), nullable=False)
    classification_version: Mapped[str] = mapped_column(String(50), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OfficialDocument(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("source_url", name="source_url"),
        {"schema": "rag"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    publisher: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[date] = mapped_column(Date, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    product_slugs: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    event_start: Mapped[date] = mapped_column(Date, nullable=False)
    event_end: Mapped[date] = mapped_column(Date, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class OfficialDocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="document_chunk_index"),
        {"schema": "rag"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("rag.documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(256), nullable=False)
