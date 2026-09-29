import pytest

from price_lens.ai.text2sql.validator import SqlValidationError, SqlValidator


@pytest.fixture
def validator() -> SqlValidator:
    return SqlValidator(max_rows=25)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE analytics.daily_product_metrics",
        "DELETE FROM analytics.v_product_daily",
        "UPDATE analytics.v_product_daily SET classification = 'low'",
        "INSERT INTO analytics.v_product_daily (trade_date) VALUES (CURRENT_DATE)",
        "ALTER TABLE analytics.v_product_daily ADD COLUMN hacked int",
        "COPY analytics.v_product_daily TO STDOUT",
        "CALL dangerous_proc()",
        "DO $$ BEGIN RAISE NOTICE 'x'; END $$",
        "BEGIN; SELECT * FROM analytics.v_product_daily",
        "SELECT * FROM analytics.v_product_daily; DROP TABLE core.products",
        "WITH changed AS (DELETE FROM core.products RETURNING *) SELECT * FROM changed",
        "SELECT * FROM core.products",
        "SELECT * FROM pg_catalog.pg_roles",
        "SELECT pg_read_file('/etc/passwd') FROM analytics.v_product_daily",
        "SELECT * FROM analytics.v_product_daily, LATERAL generate_series(1, 1000000)",
        "SELECT 1",
        "SELECT * FROM analytics.v_product_daily LIMIT ALL",
    ],
)
def test_rejects_unsafe_or_unbounded_sql(validator: SqlValidator, sql: str) -> None:
    with pytest.raises(SqlValidationError):
        validator.validate(sql)


def test_accepts_select_cte_and_injects_limit(validator: SqlValidator) -> None:
    result = validator.validate(
        """
        WITH recent AS (
            SELECT product_slug, price_twd_per_kg
            FROM analytics.v_product_daily
            WHERE trade_date >= CURRENT_DATE - INTERVAL '30 days'
        )
        SELECT product_slug, MAX(price_twd_per_kg) AS peak
        FROM recent
        GROUP BY product_slug
        ORDER BY peak DESC
        """
    )
    assert result.row_limit == 25
    assert result.relations == ("v_product_daily",)
    assert "LIMIT 25" in result.sql


def test_caps_existing_limit(validator: SqlValidator) -> None:
    result = validator.validate(
        "SELECT * FROM analytics.v_latest_product_status LIMIT 500"
    )
    assert result.row_limit == 25
    assert "LIMIT 25" in result.sql
