from types import SimpleNamespace

import pytest

from price_lens.ai.normalization import (
    NormalizedProduct,
    ProductCandidate,
    match_product,
)
from price_lens.ai.router import IntentRouter
from price_lens.schemas.analytics import ProductIdentity


def _product(slug: str = "cabbage") -> NormalizedProduct:
    return NormalizedProduct(
        identity=ProductIdentity(
            slug=slug,
            canonical_name="甘藍",
            display_name="高麗菜（甘藍）",
            category="vegetable",
        ),
        matched_text="高麗菜",
        confidence=1.0,
    )


@pytest.mark.parametrize(
    ("question", "product", "expected"),
    [
        ("高麗菜現在算貴嗎？", _product(), "product_status"),
        ("高麗菜最近漲多少？", _product(), "product_change"),
        ("高麗菜為什麼變貴？", _product(), "price_reason"),
        ("哪些菜本週變便宜？", None, "movers_down"),
        ("哪些商品最近漲最多？", None, "movers_up"),
        ("哪個商品最貴？", None, "exploratory"),
        ("哪個市場的高麗菜最貴？", _product(), "exploratory"),
    ],
)
def test_routes_representative_questions(question, product, expected) -> None:
    assert IntentRouter().route(question, product).intent == expected


def test_product_normalization_prefers_longest_alias() -> None:
    cabbage = SimpleNamespace(
        slug="cabbage",
        canonical_name="甘藍",
        display_name="高麗菜（甘藍）",
        category="vegetable",
    )
    kohlrabi = SimpleNamespace(
        slug="kohlrabi",
        canonical_name="球莖甘藍",
        display_name="球莖甘藍",
        category="vegetable",
    )
    candidates = [
        ProductCandidate(
            ProductIdentity(**cabbage.__dict__), "甘藍", "甘藍", 100
        ),
        ProductCandidate(
            ProductIdentity(**kohlrabi.__dict__), "球莖甘藍", "球莖甘藍", 100
        ),
    ]
    result = match_product("球莖甘藍現在多少錢？", candidates)
    assert result is not None
    assert result.identity.slug == "kohlrabi"
