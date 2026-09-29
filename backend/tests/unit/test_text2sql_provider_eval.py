import pytest

from price_lens.ai.providers import RulesSqlProvider, UnsupportedQuestionError
from price_lens.ai.text2sql.validator import SqlValidator


@pytest.mark.parametrize(
    ("question", "product_slug", "expected_fragment"),
    [
        ("哪個商品最貴？", None, "DESC"),
        ("目前價格最高的五種農產品", None, "DESC"),
        ("哪個商品最便宜？", None, "ASC"),
        ("列出價格最低的農產品", None, "ASC"),
        ("目前成交量最大的商品", None, "volume_kg DESC"),
        ("哪個商品交易量最大？", None, "volume_kg DESC"),
        ("哪個市場的高麗菜最貴？", "cabbage", "v_market_product_daily"),
        ("比較各市場高麗菜價格", "cabbage", "v_market_product_daily"),
    ],
)
def test_representative_sql_generation_executes_safe_path(
    question: str, product_slug: str | None, expected_fragment: str
) -> None:
    proposal = RulesSqlProvider().generate_sql(question, product_slug=product_slug)
    validated = SqlValidator(max_rows=100).validate(proposal.sql)
    assert expected_fragment in validated.sql


def test_unsupported_question_abstains() -> None:
    with pytest.raises(UnsupportedQuestionError):
        RulesSqlProvider().generate_sql("明天會下雨嗎？", product_slug=None)
