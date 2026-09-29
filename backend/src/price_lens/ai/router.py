from dataclasses import dataclass
from typing import Literal

from price_lens.ai.normalization import NormalizedProduct

Intent = Literal[
    "product_status",
    "product_change",
    "price_reason",
    "movers_up",
    "movers_down",
    "exploratory",
]


@dataclass(frozen=True)
class IntentDecision:
    intent: Intent
    route: Literal["typed_analytics", "text2sql"]
    product: NormalizedProduct | None


class IntentRouter:
    def route(
        self, question: str, product: NormalizedProduct | None
    ) -> IntentDecision:
        compact = "".join(question.casefold().split())
        if product is not None and any(
            token in compact for token in ("為什麼", "為何", "原因", "怎麼會")
        ):
            return IntentDecision("price_reason", "typed_analytics", product)

        asks_market_comparison = "市場" in compact and any(
            token in compact for token in ("哪個", "最高", "最低", "比較")
        )
        if product is not None and not asks_market_comparison:
            if any(
                token in compact
                for token in ("漲", "跌", "變貴", "變便宜", "變化", "最近", "本週", "本月")
            ):
                return IntentDecision("product_change", "typed_analytics", product)
            return IntentDecision("product_status", "typed_analytics", product)

        asks_group = any(token in compact for token in ("哪些", "排行", "排名", "最多"))
        asks_recent = any(token in compact for token in ("本週", "最近", "7天", "七天"))
        if asks_group and asks_recent and any(
            token in compact for token in ("跌", "便宜", "降")
        ):
            return IntentDecision("movers_down", "typed_analytics", None)
        if asks_group and asks_recent and any(
            token in compact for token in ("漲", "貴", "升")
        ):
            return IntentDecision("movers_up", "typed_analytics", None)
        return IntentDecision("exploratory", "text2sql", product)
