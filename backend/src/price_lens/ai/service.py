import hashlib
import logging
import time
from datetime import date
from functools import lru_cache
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from price_lens.ai.normalization import ProductNormalizer
from price_lens.ai.providers import RulesSqlProvider, UnsupportedQuestionError
from price_lens.ai.router import IntentDecision, IntentRouter
from price_lens.ai.text2sql.executor import Text2SqlExecutionError, Text2SqlExecutor
from price_lens.ai.text2sql.validator import SqlValidationError, SqlValidator
from price_lens.analytics.service import AnalyticsService
from price_lens.config import Settings, get_settings
from price_lens.db.models import DataSource
from price_lens.rag.service import OfficialDocumentRetriever
from price_lens.schemas.ask import (
    AnswerEvidence,
    AnswerMethod,
    AskResponse,
    json_safe_row,
)

logger = logging.getLogger(__name__)

CLASSIFICATION_LABELS = {
    "low": "偏低",
    "normal": "一般區間",
    "high": "偏高",
    "anomalously_high": "異常偏高",
    "insufficient_data": "歷史資料不足，暫不分類",
}


class AskService:
    def __init__(
        self,
        settings: Settings,
        *,
        analytics: AnalyticsService | None = None,
        normalizer: ProductNormalizer | None = None,
        router: IntentRouter | None = None,
        provider: RulesSqlProvider | None = None,
        validator: SqlValidator | None = None,
        executor: Text2SqlExecutor | None = None,
        document_retriever: OfficialDocumentRetriever | None = None,
    ) -> None:
        self.settings = settings
        self.analytics = analytics or AnalyticsService()
        self.normalizer = normalizer or ProductNormalizer()
        self.router = router or IntentRouter()
        self.provider = provider or RulesSqlProvider(settings.ai_model)
        self.validator = validator or SqlValidator(max_rows=settings.text2sql_max_rows)
        self.executor = executor or Text2SqlExecutor(
            settings.text2sql_database_url,
            statement_timeout_ms=settings.text2sql_statement_timeout_ms,
            lock_timeout_ms=settings.text2sql_lock_timeout_ms,
            max_explain_cost=settings.text2sql_max_explain_cost,
        )
        self.document_retriever = document_retriever or OfficialDocumentRetriever(
            settings.rag_retrieval_limit
        )

    def answer(self, session: Session, question: str) -> AskResponse:
        started = time.perf_counter()
        trace_id = uuid4().hex
        decision = self.router.route(question, self.normalizer.normalize(session, question))
        status = "succeeded"
        row_count = 0
        try:
            if decision.route == "typed_analytics":
                response = self._answer_typed(session, decision, trace_id, question)
            else:
                response = self._answer_text2sql(session, question, decision, trace_id)
                row_count = len(response.data)
        except (UnsupportedQuestionError, SqlValidationError, Text2SqlExecutionError) as exc:
            status = "fallback"
            response = self._fallback(session, decision, trace_id, str(exc))
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "ask_completed",
            extra={
                "trace_id": trace_id,
                "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
                "question_length": len(question),
                "route": response.route,
                "intent": decision.intent,
                "status": status,
                "row_count": row_count,
                "latency_ms": elapsed_ms,
                "provider": response.method.provider,
                "model": response.method.model,
            },
        )
        return response

    def _answer_typed(
        self,
        session: Session,
        decision: IntentDecision,
        trace_id: str,
        question: str,
    ) -> AskResponse:
        evidence = [self._evidence(session)]
        if decision.intent in {"movers_up", "movers_down"}:
            direction = "up" if decision.intent == "movers_up" else "down"
            movers = self.analytics.movers(
                session, direction=direction, period="7d", limit=5
            )
            rows = [
                json_safe_row(
                    {
                        "as_of": item.as_of,
                        "product_slug": item.product.slug,
                        "display_name": item.product.display_name,
                        "change_pct": item.change_pct,
                        "current_price_twd_per_kg": item.current_price,
                        "classification": item.classification,
                    }
                )
                for item in movers.items
            ]
            as_of = max((item.as_of for item in movers.items), default=None)
            direction_text = "上漲" if direction == "up" else "下跌"
            if movers.items:
                lead = movers.items[0]
                answer = (
                    f"截至 {as_of.isoformat()}，本週{direction_text}幅度最大的是"
                    f"{lead.product.display_name}（{lead.change_pct}%），目前批發均價為"
                    f" {lead.current_price} 元/公斤。"
                )
            else:
                answer = f"目前沒有可計算的本週{direction_text}商品。"
            return AskResponse(
                answer=answer,
                route="typed_analytics",
                as_of=as_of,
                data=rows,
                evidence=evidence,
                trace_id=trace_id,
                method=self._method(
                    decision.intent, "typed_analytics", "deterministic-tools", "none"
                ),
            )

        if decision.product is None:
            raise UnsupportedQuestionError("問題缺少可辨識的商品")
        summary = self.analytics.summary(session, decision.product.identity.slug)
        classification = CLASSIFICATION_LABELS.get(
            summary.classification.label, summary.classification.label
        )
        answer = (
            f"截至 {summary.as_of.isoformat()}，{summary.product.display_name}在所有回報批發市場的"
            f"交易量加權均價為 {summary.metrics.current_price} 元/公斤，分類為{classification}。"
        )
        warnings = list(summary.warnings)
        possible_factors = []
        if decision.intent in {"product_change", "price_reason"}:
            if summary.metrics.wow_change_pct is not None:
                answer += f"與 7 日前可用交易日相比為 {summary.metrics.wow_change_pct}%。"
            if summary.metrics.mom_change_pct is not None:
                answer += f"與 30 日前可用交易日相比為 {summary.metrics.mom_change_pct}%。"
        if decision.intent == "price_reason":
            possible_factors = self.document_retriever.explain_price_context(
                session,
                product_slug=decision.product.identity.slug,
                product_name=decision.product.identity.display_name,
                question=question,
                as_of=summary.as_of,
            )
            if possible_factors:
                answer += "同時期官方文件提供以下可能相關背景；這些資料不能單獨證明價格變動原因。"
            else:
                answer += "目前沒有時間與品項相符的官方文件可提供背景說明。"
                warnings.append("未找到符合商品與事件日期的官方文件，因此不推測價格原因。")
        return AskResponse(
            answer=answer,
            route="typed_analytics",
            as_of=summary.as_of,
            product=summary.product,
            scope=summary.scope,
            metrics=summary.metrics,
            classification=summary.classification,
            evidence=evidence,
            possible_factors=possible_factors,
            warnings=warnings,
            trace_id=trace_id,
            method=self._method(decision.intent, "typed_analytics", "deterministic-tools", "none"),
        )

    def _answer_text2sql(
        self,
        session: Session,
        question: str,
        decision: IntentDecision,
        trace_id: str,
    ) -> AskResponse:
        proposal = self.provider.generate_sql(
            question,
            product_slug=(decision.product.identity.slug if decision.product else None),
        )
        query = self.validator.validate(proposal.sql)
        result = self.executor.execute(query)
        rows = [json_safe_row(row) for row in result.rows]
        as_of = self._latest_date(rows)
        return AskResponse(
            answer=self._compose_rows(rows, as_of),
            route="text2sql",
            as_of=as_of,
            product=decision.product.identity if decision.product else None,
            data=rows,
            evidence=[self._evidence(session, as_of=as_of)],
            warnings=[
                "探索式結果只讀取受控 analytics views；價格為批發市場資料，不是零售報價。"
            ],
            trace_id=trace_id,
            method=self._method(
                decision.intent,
                "text2sql",
                proposal.provider,
                proposal.model,
                proposal.prompt_version,
            ),
        )

    def _fallback(
        self,
        session: Session,
        decision: IntentDecision,
        trace_id: str,
        detail: str,
    ) -> AskResponse:
        return AskResponse(
            answer="這個問題目前無法用已驗證的查詢回答。你可以詢問特定商品是否偏貴、近期漲跌，或商品價格與成交量排行。",
            route="fallback",
            product=decision.product.identity if decision.product else None,
            evidence=[self._evidence(session)],
            warnings=[detail],
            trace_id=trace_id,
            method=self._method(
                decision.intent, "fallback", self.provider.name, self.provider.model
            ),
        )

    @staticmethod
    def _method(
        intent: str,
        route: str,
        provider: str,
        model: str,
        version: str = "ask-contract-v1",
    ) -> AnswerMethod:
        return AnswerMethod(
            route=route,
            intent=intent,
            provider=provider,
            model=model,
            version=version,
        )

    @staticmethod
    def _evidence(session: Session, *, as_of: date | None = None) -> AnswerEvidence:
        source = session.execute(
            select(DataSource).where(DataSource.active.is_(True)).limit(1)
        ).scalar_one()
        return AnswerEvidence(
            publisher=source.publisher,
            title=source.name,
            source_url=source.dataset_url,
            as_of=as_of,
        )

    @staticmethod
    def _latest_date(rows: list[dict[str, Any]]) -> date | None:
        dates = [
            value
            for row in rows
            for key, value in row.items()
            if key in {"as_of", "trade_date"} and isinstance(value, date)
        ]
        return max(dates, default=None)

    @staticmethod
    def _compose_rows(rows: list[dict[str, Any]], as_of: date | None) -> str:
        if not rows:
            return "查詢成功，但目前沒有符合條件的批發交易資料。"
        first = rows[0]
        name = first.get("display_name") or first.get("market_name") or "第一筆結果"
        if "current_price_twd_per_kg" in first:
            answer = f"{name}為首筆結果，批發均價為 {first['current_price_twd_per_kg']} 元/公斤"
        elif "price_twd_per_kg" in first:
            answer = f"{name}為首筆結果，批發均價為 {first['price_twd_per_kg']} 元/公斤"
        elif "volume_kg" in first:
            answer = f"{name}為首筆結果，成交量為 {first['volume_kg']} 公斤"
        else:
            answer = f"查詢完成，共回傳 {len(rows)} 筆結果"
        if as_of:
            answer += f"，資料日期為 {as_of.isoformat()}"
        return answer + "。"


@lru_cache
def get_ask_service() -> AskService:
    return AskService(get_settings())
