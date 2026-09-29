"""Add canonical product slugs and deterministic daily analytics.

Revision ID: 0002_phase2
Revises: 0001_phase1
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_phase2"
down_revision: str | None = "0001_phase1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product_families",
        sa.Column("slug", sa.String(length=80), nullable=True),
        schema="core",
    )
    op.execute(
        """
        UPDATE core.product_families
        SET slug = CASE canonical_name
            WHEN '甘藍' THEN 'cabbage'
            WHEN '球莖甘藍' THEN 'kohlrabi'
            WHEN '包心白菜' THEN 'napa-cabbage'
            WHEN '番茄' THEN 'tomato'
            WHEN '小番茄' THEN 'cherry-tomato'
            WHEN '洋蔥' THEN 'onion'
            WHEN '香蕉' THEN 'banana'
            WHEN '木瓜' THEN 'papaya'
            ELSE 'family-' || id::text
        END
        """
    )
    op.alter_column("product_families", "slug", nullable=False, schema="core")
    op.create_unique_constraint(
        "uq_product_families_slug", "product_families", ["slug"], schema="core"
    )

    op.execute("CREATE SCHEMA IF NOT EXISTS analytics")
    op.create_table(
        "daily_product_metrics",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("scope_key", sa.String(length=100), nullable=False),
        sa.Column("market_id", sa.BigInteger(), nullable=True),
        sa.Column("weighted_avg_price", sa.Numeric(14, 4), nullable=False),
        sa.Column("total_volume_kg", sa.Numeric(18, 2), nullable=False),
        sa.Column("market_count", sa.Integer(), nullable=False),
        sa.Column("product_count", sa.Integer(), nullable=False),
        sa.Column("included_product_codes", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("ma_7d", sa.Numeric(14, 4), nullable=True),
        sa.Column("ma_30d", sa.Numeric(14, 4), nullable=True),
        sa.Column("ma_90d", sa.Numeric(14, 4), nullable=True),
        sa.Column("wow_change_pct", sa.Numeric(12, 4), nullable=True),
        sa.Column("mom_change_pct", sa.Numeric(12, 4), nullable=True),
        sa.Column("percentile_365d", sa.Numeric(7, 3), nullable=True),
        sa.Column("z_score_365d", sa.Numeric(12, 5), nullable=True),
        sa.Column("robust_z_365d", sa.Numeric(12, 5), nullable=True),
        sa.Column("historical_high_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("historical_high_date", sa.Date(), nullable=True),
        sa.Column("historical_low_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("historical_low_date", sa.Date(), nullable=True),
        sa.Column("volume_change_pct", sa.Numeric(12, 4), nullable=True),
        sa.Column("volatility_30d", sa.Numeric(12, 6), nullable=True),
        sa.Column("history_day_count", sa.Integer(), nullable=False),
        sa.Column("classification", sa.String(length=40), nullable=False),
        sa.Column("calculation_version", sa.String(length=50), nullable=False),
        sa.Column("classification_version", sa.String(length=50), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "weighted_avg_price > 0",
            name="ck_daily_product_metrics_weighted_avg_price_positive",
        ),
        sa.CheckConstraint(
            "total_volume_kg > 0",
            name="ck_daily_product_metrics_total_volume_positive",
        ),
        sa.CheckConstraint(
            "market_count > 0", name="ck_daily_product_metrics_market_count_positive"
        ),
        sa.CheckConstraint(
            "product_count > 0", name="ck_daily_product_metrics_product_count_positive"
        ),
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["core.product_families.id"],
            name="fk_daily_product_metrics_family_id_product_families",
        ),
        sa.ForeignKeyConstraint(
            ["market_id"],
            ["core.markets.id"],
            name="fk_daily_product_metrics_market_id_markets",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_daily_product_metrics"),
        sa.UniqueConstraint(
            "trade_date",
            "family_id",
            "scope_key",
            "calculation_version",
            "classification_version",
            name="uq_daily_product_metrics_versioned_natural_key",
        ),
        schema="analytics",
    )
    op.create_index(
        "ix_daily_metrics_family_trade_date",
        "daily_product_metrics",
        ["family_id", "trade_date"],
        schema="analytics",
    )
    op.create_index(
        "ix_daily_metrics_scope_trade_date",
        "daily_product_metrics",
        ["scope_key", "trade_date"],
        schema="analytics",
    )


def downgrade() -> None:
    op.drop_table("daily_product_metrics", schema="analytics")
    op.execute("DROP SCHEMA IF EXISTS analytics")
    op.drop_constraint(
        "uq_product_families_slug", "product_families", schema="core", type_="unique"
    )
    op.drop_column("product_families", "slug", schema="core")
