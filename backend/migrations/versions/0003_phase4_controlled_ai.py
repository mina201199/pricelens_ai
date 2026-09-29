"""Add Phase 4 Text2SQL semantic views and database role.

Revision ID: 0003_phase4
Revises: 0002_phase2
Create Date: 2026-09-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_phase4"
down_revision: str | None = "0002_phase2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'price_lens_text2sql') THEN
                CREATE ROLE price_lens_text2sql NOLOGIN NOSUPERUSER NOCREATEDB
                    NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
            END IF;
        END
        $$
        """
    )
    op.execute(
        """
        ALTER ROLE price_lens_text2sql SET default_transaction_read_only = on;
        ALTER ROLE price_lens_text2sql SET statement_timeout = '2s';
        ALTER ROLE price_lens_text2sql SET lock_timeout = '500ms';
        ALTER ROLE price_lens_text2sql SET search_path = analytics;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW analytics.v_product_daily AS
        SELECT
            metric.trade_date,
            family.slug AS product_slug,
            family.canonical_name AS product_name,
            family.display_name,
            family.category,
            metric.weighted_avg_price AS price_twd_per_kg,
            metric.total_volume_kg AS volume_kg,
            metric.market_count,
            metric.product_count AS included_variety_count,
            metric.ma_7d,
            metric.ma_30d,
            metric.ma_90d,
            metric.wow_change_pct,
            metric.mom_change_pct,
            metric.percentile_365d,
            metric.historical_high_price,
            metric.historical_high_date,
            metric.historical_low_price,
            metric.historical_low_date,
            metric.classification,
            metric.calculation_version,
            metric.classification_version
        FROM analytics.daily_product_metrics AS metric
        JOIN core.product_families AS family ON family.id = metric.family_id
        WHERE metric.scope_key = 'all_reporting_markets' AND family.active = true
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW analytics.v_latest_product_status AS
        SELECT DISTINCT ON (product_slug)
            trade_date AS as_of,
            product_slug,
            product_name,
            display_name,
            category,
            price_twd_per_kg AS current_price_twd_per_kg,
            volume_kg,
            market_count,
            ma_7d,
            ma_30d,
            ma_90d,
            wow_change_pct,
            mom_change_pct,
            percentile_365d,
            historical_high_price,
            historical_high_date,
            historical_low_price,
            historical_low_date,
            classification,
            calculation_version,
            classification_version
        FROM analytics.v_product_daily
        ORDER BY product_slug, trade_date DESC
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW analytics.v_weekly_movers AS
        SELECT
            as_of,
            product_slug,
            product_name,
            display_name,
            current_price_twd_per_kg,
            wow_change_pct,
            classification,
            market_count
        FROM analytics.v_latest_product_status
        WHERE wow_change_pct IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW analytics.v_market_product_daily AS
        SELECT
            metric.trade_date,
            market.source_market_code AS market_code,
            market.canonical_name AS market_name,
            family.slug AS product_slug,
            family.canonical_name AS product_name,
            family.display_name,
            metric.weighted_avg_price AS price_twd_per_kg,
            metric.total_volume_kg AS volume_kg,
            metric.product_count AS included_variety_count,
            metric.wow_change_pct,
            metric.mom_change_pct,
            metric.classification,
            metric.calculation_version,
            metric.classification_version
        FROM analytics.daily_product_metrics AS metric
        JOIN core.product_families AS family ON family.id = metric.family_id
        JOIN core.markets AS market ON market.id = metric.market_id
        WHERE metric.scope_key LIKE 'market:%' AND family.active = true
        """
    )
    op.execute(
        """
        COMMENT ON VIEW analytics.v_product_daily IS
            'Canonical all-market daily wholesale price series in TWD/kg.';
        COMMENT ON VIEW analytics.v_latest_product_status IS
            'Latest available wholesale price and classification by canonical product.';
        COMMENT ON VIEW analytics.v_weekly_movers IS
            'Latest products with a computed seven-day price change.';
        COMMENT ON VIEW analytics.v_market_product_daily IS
            'Canonical daily wholesale price series by official reporting market.';
        GRANT USAGE ON SCHEMA analytics TO price_lens_text2sql;
        GRANT SELECT ON analytics.v_product_daily TO price_lens_text2sql;
        GRANT SELECT ON analytics.v_latest_product_status TO price_lens_text2sql;
        GRANT SELECT ON analytics.v_weekly_movers TO price_lens_text2sql;
        GRANT SELECT ON analytics.v_market_product_daily TO price_lens_text2sql;
        REVOKE CREATE ON SCHEMA public FROM price_lens_text2sql;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format(
                'GRANT CONNECT ON DATABASE %I TO price_lens_text2sql',
                current_database()
            );
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS analytics.v_market_product_daily")
    op.execute("DROP VIEW IF EXISTS analytics.v_weekly_movers")
    op.execute("DROP VIEW IF EXISTS analytics.v_latest_product_status")
    op.execute("DROP VIEW IF EXISTS analytics.v_product_daily")
    op.execute("REVOKE USAGE ON SCHEMA analytics FROM price_lens_text2sql")
