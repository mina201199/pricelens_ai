#!/usr/bin/env python3

import json
import os
import platform
import statistics
import time
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
API_BASE = os.getenv("PRICE_LENS_API_URL", "http://api:8000")
FRONTEND_URL = os.getenv("PRICE_LENS_FRONTEND_URL", "http://frontend:3000")


def _measure(url: str, count: int = 10) -> dict[str, float | int]:
    samples: list[float] = []
    failures = 0
    for _ in range(count):
        started = time.perf_counter()
        try:
            with urlopen(url, timeout=5) as response:
                if response.status != 200:
                    failures += 1
                else:
                    response.read()
        except (OSError, URLError):
            failures += 1
        samples.append((time.perf_counter() - started) * 1000)
    ordered = sorted(samples)
    return {
        "requests": count,
        "failures": failures,
        "p50_ms": round(statistics.median(ordered), 2),
        "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 2),
    }


def _freshness() -> dict[str, str | int | None]:
    with urlopen(f"{API_BASE}/api/v1/data-status", timeout=5) as response:
        status = json.loads(response.read())
    latest = status.get("latest_trade_date")
    lag = (date.today() - date.fromisoformat(latest)).days if latest else None
    return {"latest_trade_date": latest, "calendar_day_lag": lag}


def main() -> None:
    report = {
        "evaluation": "phase6-release-smoke-v1",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "provider": "deterministic-rules-and-local-ngram",
        "model": "price-lens-rules-v1 / char-ngram-hash-v1",
        "prompt_version": "ask-contract-v1 / extractive-template-v1",
        "dataset_revision": "phase4-controlled-ai-v1 + rag.v1",
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "hardware": platform.machine(),
        },
        "cost": {"external_model_calls": 0, "currency_cost": "not applicable"},
        "checks": {
            "api_health": _measure(f"{API_BASE}/api/v1/health"),
            "api_radar": _measure(f"{API_BASE}/api/v1/radar"),
            "frontend_home": _measure(FRONTEND_URL),
        },
        "freshness": _freshness(),
    }
    output = ROOT / "evals" / "reports" / "phase6-release-smoke.v1.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if any(check["failures"] for check in report["checks"].values()):
        raise SystemExit("Release smoke failed; see checks above.")


if __name__ == "__main__":
    main()
