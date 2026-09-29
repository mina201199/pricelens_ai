"""Create Phase 1 provenance, dimensions, raw records, and wholesale observations.

Revision ID: 0001_phase1
Revises:
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_phase1"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS core")
    op.execute("CREATE SCHEMA IF NOT EXISTS raw")

    op.create_table(
        "data_sources",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("publisher", sa.Text(), nullable=False),
        sa.Column("dataset_url", sa.Text(), nullable=False),
        sa.Column("api_url", sa.Text(), nullable=False),
        sa.Column("license_name", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_sources"),
        sa.UniqueConstraint("code", name="uq_data_sources_code"),
        schema="core",
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("request_params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("records_received", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_inserted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_unchanged", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_excluded", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_quarantined", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("code_version", sa.String(length=100), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')", name="ck_ingestion_runs_valid_status"
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["core.data_sources.id"], name="fk_ingestion_runs_source_id_data_sources"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_runs"),
        schema="core",
    )
    op.create_index(
        "ix_core_ingestion_runs_source_id",
        "ingestion_runs",
        ["source_id"],
        schema="core",
    )

    op.create_table(
        "product_families",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column(
            "default_include_imported",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("mapping_version", sa.String(length=50), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_families"),
        sa.UniqueConstraint("canonical_name", name="uq_product_families_canonical_name"),
        schema="core",
    )

    op.create_table(
        "markets",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("source_market_code", sa.String(length=30), nullable=False),
        sa.Column("source_market_name", sa.Text(), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"], ["core.data_sources.id"], name="fk_markets_source_id_data_sources"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_markets"),
        sa.UniqueConstraint(
            "source_id", "source_market_code", name="uq_markets_source_market_code"
        ),
        schema="core",
    )

    op.create_table(
        "product_aliases",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("normalized_alias", sa.Text(), nullable=False),
        sa.Column("locale", sa.String(length=20), server_default="zh-TW", nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="100", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["core.product_families.id"],
            name="fk_product_aliases_family_id_product_families",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_aliases"),
        sa.UniqueConstraint(
            "family_id", "normalized_alias", name="uq_product_aliases_family_normalized_alias"
        ),
        schema="core",
    )
    op.create_index(
        "ix_core_product_aliases_family_id",
        "product_aliases",
        ["family_id"],
        schema="core",
    )

    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=True),
        sa.Column("source_product_code", sa.String(length=30), nullable=False),
        sa.Column("source_product_name", sa.Text(), nullable=False),
        sa.Column("category_code", sa.String(length=30), nullable=False),
        sa.Column("variety", sa.Text(), nullable=True),
        sa.Column("origin_type", sa.String(length=20), nullable=False),
        sa.Column(
            "analytics_included", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("mapping_version", sa.String(length=50), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "origin_type IN ('domestic', 'imported', 'unknown')",
            name="ck_products_valid_origin_type",
        ),
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["core.product_families.id"],
            name="fk_products_family_id_product_families",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["core.data_sources.id"], name="fk_products_source_id_data_sources"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        sa.UniqueConstraint(
            "source_id", "source_product_code", name="uq_products_source_product_code"
        ),
        schema="core",
    )

    op.create_table(
        "market_records",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("ingestion_run_id", sa.BigInteger(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("source_record_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("validation_status", sa.String(length=30), nullable=False),
        sa.Column(
            "validation_errors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "validation_status IN ('valid', 'excluded_closure', 'quarantined')",
            name="ck_market_records_valid_validation_status",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["core.ingestion_runs.id"],
            name="fk_market_records_ingestion_run_id_ingestion_runs",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["core.data_sources.id"], name="fk_market_records_source_id_data_sources"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_market_records"),
        sa.UniqueConstraint(
            "source_id", "source_record_hash", name="uq_market_records_source_record_hash"
        ),
        schema="raw",
    )
    op.create_index(
        "ix_raw_market_records_ingestion_run_id",
        "market_records",
        ["ingestion_run_id"],
        schema="raw",
    )
    op.create_index(
        "ix_raw_market_records_source_id", "market_records", ["source_id"], schema="raw"
    )

    op.create_table(
        "market_price_observations",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("ingestion_run_id", sa.BigInteger(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("market_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("upper_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("middle_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("lower_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("average_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("volume_kg", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("source_record_hash", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "upper_price >= 0", name="ck_market_price_observations_upper_price_nonnegative"
        ),
        sa.CheckConstraint(
            "middle_price >= 0", name="ck_market_price_observations_middle_price_nonnegative"
        ),
        sa.CheckConstraint(
            "lower_price >= 0", name="ck_market_price_observations_lower_price_nonnegative"
        ),
        sa.CheckConstraint(
            "average_price > 0", name="ck_market_price_observations_average_price_positive"
        ),
        sa.CheckConstraint("volume_kg > 0", name="ck_market_price_observations_volume_positive"),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["core.ingestion_runs.id"],
            name="fk_market_price_observations_ingestion_run_id_ingestion_runs",
        ),
        sa.ForeignKeyConstraint(
            ["market_id"],
            ["core.markets.id"],
            name="fk_market_price_observations_market_id_markets",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["core.products.id"],
            name="fk_market_price_observations_product_id_products",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["core.data_sources.id"],
            name="fk_market_price_observations_source_id_data_sources",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_market_price_observations"),
        sa.UniqueConstraint(
            "source_id",
            "trade_date",
            "market_id",
            "product_id",
            name="uq_market_price_observations_natural_key",
        ),
        schema="core",
    )
    op.create_index(
        "ix_core_market_price_observations_ingestion_run_id",
        "market_price_observations",
        ["ingestion_run_id"],
        schema="core",
    )
    op.create_index(
        "ix_observations_market_trade_date",
        "market_price_observations",
        ["market_id", "trade_date"],
        schema="core",
    )
    op.create_index(
        "ix_observations_product_trade_date",
        "market_price_observations",
        ["product_id", "trade_date"],
        schema="core",
    )


def downgrade() -> None:
    op.drop_table("market_price_observations", schema="core")
    op.drop_table("market_records", schema="raw")
    op.drop_table("products", schema="core")
    op.drop_table("product_aliases", schema="core")
    op.drop_table("markets", schema="core")
    op.drop_table("product_families", schema="core")
    op.drop_table("ingestion_runs", schema="core")
    op.drop_table("data_sources", schema="core")
    op.execute("DROP SCHEMA IF EXISTS raw")
    op.execute("DROP SCHEMA IF EXISTS core")
