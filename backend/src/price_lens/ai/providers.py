from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SqlProposal:
    sql: str
    provider: str
    model: str
    prompt_version: str


class SqlGenerationProvider(Protocol):
    name: str
    model: str

    def generate_sql(self, question: str, *, product_slug: str | None) -> SqlProposal: ...


class UnsupportedQuestionError(ValueError):
    pass


class RulesSqlProvider:
    """Reproducible baseline provider used when no hosted model is configured."""

    name = "rules"
    prompt_version = "text2sql-rules-v1"

    def __init__(self, model: str = "price-lens-rules-v1") -> None:
        self.model = model

    def generate_sql(self, question: str, *, product_slug: str | None) -> SqlProposal:
        compact = "".join(question.casefold().split())
        sql: str | None = None
        if "市場" in compact and product_slug and any(
            token in compact for token in ("最高", "最貴", "比較")
        ):
            sql = f"""
                WITH latest AS (
                    SELECT MAX(trade_date) AS trade_date
                    FROM analytics.v_market_product_daily
                    WHERE product_slug = '{product_slug}'
                )
                SELECT market_code, market_name, trade_date, price_twd_per_kg, volume_kg
                FROM analytics.v_market_product_daily
                WHERE product_slug = '{product_slug}'
                  AND trade_date = (SELECT trade_date FROM latest)
                ORDER BY price_twd_per_kg DESC
                LIMIT 10
            """
        elif any(token in compact for token in ("最貴", "最高價", "價格最高")):
            sql = """
                SELECT as_of, product_slug, display_name, current_price_twd_per_kg,
                       classification, market_count
                FROM analytics.v_latest_product_status
                ORDER BY current_price_twd_per_kg DESC
                LIMIT 5
            """
        elif any(token in compact for token in ("最便宜", "最低價", "價格最低")):
            sql = """
                SELECT as_of, product_slug, display_name, current_price_twd_per_kg,
                       classification, market_count
                FROM analytics.v_latest_product_status
                ORDER BY current_price_twd_per_kg ASC
                LIMIT 5
            """
        elif any(token in compact for token in ("成交量最大", "交易量最大", "成交量最多")):
            sql = """
                SELECT as_of, product_slug, display_name, volume_kg,
                       current_price_twd_per_kg, market_count
                FROM analytics.v_latest_product_status
                ORDER BY volume_kg DESC
                LIMIT 5
            """
        if sql is None:
            raise UnsupportedQuestionError(
                "目前可回答商品價格、漲跌榜、最高／最低價格與成交量排行。"
            )
        return SqlProposal(
            sql=sql.strip(),
            provider=self.name,
            model=self.model,
            prompt_version=self.prompt_version,
        )
