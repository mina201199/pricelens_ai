#!/usr/bin/env python3

import json
import platform
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from price_lens.rag.documents import embed_text, source_publisher

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "evals" / "datasets" / "rag.v1.jsonl"
REPORT = ROOT / "evals" / "reports" / "phase5-rag.v1.json"
MAX_DISTANCE = 0.94
TOP_K = 5


def _eligible(document: dict[str, Any], product_slug: str, as_of: date) -> bool:
    published = date.fromisoformat(document["published_at"])
    event_start = date.fromisoformat(document["event_start"])
    event_end = date.fromisoformat(document["event_end"])
    return (
        product_slug in document["product_slugs"]
        and as_of - timedelta(days=365) <= published <= as_of
        and event_start <= as_of
        and event_end >= as_of - timedelta(days=60)
    )


def evaluate() -> dict[str, Any]:
    cases = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines()]
    started = time.perf_counter()
    recall_values: list[float] = []
    reciprocal_ranks: list[float] = []
    citation_checks = 0
    abstention_correct = 0
    details = []

    for case in cases:
        query = embed_text(f"{case['product_name']} {case['question']}")
        as_of = date.fromisoformat(case["as_of"])
        candidates = [
            document
            for document in case["documents"]
            if _eligible(document, case["product_slug"], as_of)
        ]
        ranked = []
        for document in candidates:
            vector = embed_text(document["content"])
            distance = 1 - sum(left * right for left, right in zip(query, vector, strict=True))
            if distance <= MAX_DISTANCE:
                ranked.append((distance, document))
        ranked.sort(key=lambda item: item[0])
        retrieved = [document for _, document in ranked[:TOP_K]]
        retrieved_ids = [document["id"] for document in retrieved]
        expected = case["expected_relevant_ids"]
        hits = [
            index
            for index, item_id in enumerate(retrieved_ids, start=1)
            if item_id in expected
        ]
        recall_values.append(
            len(set(retrieved_ids) & set(expected)) / len(expected) if expected else 1.0
        )
        reciprocal_ranks.append(1 / hits[0] if hits else 0.0 if expected else 1.0)
        citation_checks += sum(
            source_publisher(document["source_url"])
            in {"農業部", "農業部統計處", "農業部農糧署"}
            for document in retrieved
        )
        abstention_correct += int(not expected and not retrieved)
        details.append(
            {
                "id": case["id"],
                "expected_relevant_ids": expected,
                "retrieved_ids": retrieved_ids,
                "abstained": not retrieved,
            }
        )

    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    citation_count = sum(len(item["retrieved_ids"]) for item in details)
    report = {
        "evaluation": "phase5-official-rag-v1",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "provider": "local-character-ngram",
        "model": "char-ngram-hash-v1",
        "prompt_version": "extractive-template-v1",
        "embedding_version": "char-ngram-256-v1",
        "dataset": DATASET.name,
        "dataset_revision": "rag.v1",
        "metrics": {
            "recall_at_5": round(sum(recall_values) / len(recall_values), 4),
            "mrr": round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4),
            "citation_domain_correctness": round(citation_checks / citation_count, 4)
            if citation_count
            else 1.0,
            "abstention_accuracy": round(
                abstention_correct
                / sum(not case["expected_relevant_ids"] for case in cases),
                4,
            )
            if any(not case["expected_relevant_ids"] for case in cases)
            else 1.0,
        },
        "counts": {
            "queries": len(cases),
            "documents": sum(len(case["documents"]) for case in cases),
        },
        "latency_ms": elapsed_ms,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "hardware": {
                "architecture": platform.machine(),
                "processor": platform.processor() or "not exposed inside the container",
            },
        },
        "details": details,
        "notes": [
            "Sanitized synthetic query-document fixtures; not a live coverage claim.",
            "Character n-gram embeddings are lexical and are not semantic embeddings.",
            "Citation checks verify an official host; answers are extractive chunks.",
            "Prompt-injection text is untrusted evidence, never an instruction.",
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
