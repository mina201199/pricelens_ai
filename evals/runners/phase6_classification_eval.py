#!/usr/bin/env python3

import json
import platform
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from price_lens.analytics.calculator import CLASSIFICATION_VERSION, classify_price

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "evals" / "datasets" / "classification.v1.jsonl"
OUTPUT = ROOT / "evals" / "reports" / "phase6-classification.v1.json"


def main() -> None:
    rows = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines()]
    details = []
    for row in rows:
        actual = classify_price(
            history_day_count=row["history_day_count"],
            current=Decimal(row["current"]),
            ma_30d=Decimal(row["ma_30d"]),
            percentile_365d=Decimal(row["percentile_365d"]),
            robust_z_365d=Decimal(row["robust_z_365d"]),
        )
        details.append({"id": row["id"], "expected": row["expected"], "actual": actual})
    accuracy = sum(item["expected"] == item["actual"] for item in details) / len(details)
    report = {
        "evaluation": "phase6-classification-review-v1",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "provider": "deterministic-rule-engine",
        "model": CLASSIFICATION_VERSION,
        "prompt_version": "none",
        "dataset": DATASET.name,
        "dataset_revision": "classification.v1",
        "metrics": {"boundary_accuracy": accuracy},
        "counts": {"cases": len(rows)},
        "runtime": {"python": platform.python_version(), "platform": platform.platform()},
        "details": details,
        "notes": ["Boundary review fixtures are synthetic; expert agreement is not measured."],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if accuracy != 1:
        raise SystemExit("Classification review regression detected.")


if __name__ == "__main__":
    main()
