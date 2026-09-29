#!/usr/bin/env python3

import json
import platform
import time
from argparse import ArgumentParser
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from price_lens.ai.normalization import ProductCandidate, match_product
from price_lens.ai.providers import RulesSqlProvider
from price_lens.ai.router import IntentRouter
from price_lens.ai.text2sql.executor import Text2SqlExecutor
from price_lens.ai.text2sql.validator import SqlValidationError, SqlValidator
from price_lens.config import get_settings
from price_lens.ingestion.mapping import ProductMappingRegistry, normalize_alias
from price_lens.schemas.analytics import ProductIdentity

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / "evals" / "datasets"


def _read(name: str) -> list[dict[str, Any]]:
    path = DATASETS / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _candidates() -> tuple[list[ProductCandidate], dict[str, ProductIdentity]]:
    registry = ProductMappingRegistry.load_default()
    candidates: list[ProductCandidate] = []
    identities: dict[str, ProductIdentity] = {}
    for family in registry.families:
        identity = ProductIdentity(
            slug=family.slug,
            canonical_name=family.canonical_name,
            display_name=family.display_name,
            category=family.category,
        )
        identities[family.slug] = identity
        for alias in family.aliases:
            candidates.append(
                ProductCandidate(
                    identity=identity,
                    alias=alias,
                    normalized_alias=normalize_alias(alias),
                    priority=100,
                )
            )
    return candidates, identities


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    started = time.perf_counter()
    candidates, identities = _candidates()
    router = IntentRouter()
    provider = RulesSqlProvider()
    validator = SqlValidator(max_rows=100)

    normalization_rows = _read("normalization.v1.jsonl")
    normalization_correct = 0
    for row in normalization_rows:
        result = match_product(row["question"], candidates)
        actual = result.identity.slug if result else None
        normalization_correct += actual == row["expected_slug"]

    intent_rows = _read("intent.v1.jsonl")
    intent_correct = 0
    for row in intent_rows:
        product = None
        if row["product_slug"]:
            identity = identities[row["product_slug"]]
            product = match_product(identity.display_name, candidates)
        result = router.route(row["question"], product)
        intent_correct += (
            result.intent == row["expected_intent"]
            and result.route == row["expected_route"]
        )

    text2sql_rows = _read("text2sql.v1.jsonl")
    text2sql_correct = 0
    execution_correct = 0
    executor = None
    if args.execute:
        settings = get_settings()
        executor = Text2SqlExecutor(
            settings.text2sql_database_url,
            statement_timeout_ms=settings.text2sql_statement_timeout_ms,
            lock_timeout_ms=settings.text2sql_lock_timeout_ms,
            max_explain_cost=settings.text2sql_max_explain_cost,
        )
    for row in text2sql_rows:
        proposal = provider.generate_sql(
            row["question"], product_slug=row["product_slug"]
        )
        validated = validator.validate(proposal.sql)
        text2sql_correct += row["expected_fragment"] in validated.sql
        if executor is not None:
            execution_correct += bool(executor.execute(validated).rows)

    adversarial_rows = _read("text2sql-adversarial.v1.jsonl")
    blocked = 0
    for row in adversarial_rows:
        try:
            validator.validate(row["sql"])
        except SqlValidationError:
            blocked += 1

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    report = {
        "evaluation": "phase4-controlled-ai-v1",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "provider": provider.name,
        "model": provider.model,
        "prompt_version": provider.prompt_version,
        "datasets": {
            "normalization": "normalization.v1.jsonl",
            "intent": "intent.v1.jsonl",
            "text2sql": "text2sql.v1.jsonl",
            "adversarial": "text2sql-adversarial.v1.jsonl",
        },
        "metrics": {
            "normalization_accuracy": normalization_correct / len(normalization_rows),
            "intent_route_accuracy": intent_correct / len(intent_rows),
            "text2sql_validation_accuracy": text2sql_correct / len(text2sql_rows),
            "text2sql_execution_accuracy": (
                execution_correct / len(text2sql_rows) if executor is not None else None
            ),
            "adversarial_block_rate": blocked / len(adversarial_rows),
        },
        "counts": {
            "normalization": len(normalization_rows),
            "intent": len(intent_rows),
            "text2sql": len(text2sql_rows),
            "adversarial": len(adversarial_rows),
        },
        "latency_ms": elapsed_ms,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
