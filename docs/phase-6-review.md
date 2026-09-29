# Phase 6 Review — Evaluation, Hardening, and Portfolio Release

狀態：Phase 6 首輪交付與本機驗證完成；CI workflow 已建立，需由遠端 GitHub runner 首次執行確認。

## 交付

- `.github/workflows/ci.yml`：Python 3.12、PostgreSQL/pgvector integration suite、Ruff、Phase 4/5 evaluations、classification review、dependency audit；前端 frozen install、ESLint、TypeScript、Vitest、production build。
- `evals/datasets/classification.v1.jsonl`：凍結分類邊界 review set，涵蓋資料不足、異常高、high/low 門檻、正常區間與規則優先順序。
- `evals/runners/phase6_classification_eval.py`：版本化結果報告和 regression gate。
- `evals/runners/phase6_release_smoke.py`：服務健康、radar、首頁十次延遲樣本、p50/p95、錯誤數與最新交易日 lag；記錄 deterministic provider、runtime 和外部模型費用為零。
- FastAPI structured request logs：request ID、method、path、status、duration；不記錄 query string 或使用者問題。回應提供 `X-Request-ID`。
- `scripts/demo.ps1`：Windows 一鍵 build/start/health check；不刪除既有資料 volume。
- `scripts/backup-restore-smoke.ps1`：將目前 DB 備份還原到專用暫存資料庫，比對 observation 筆數後僅刪除本次建立的暫存 DB。

## 驗收快照

- Backend on pytest 9.1.1: 77 passed, 1 skipped（官方 live contract test）。Ruff passed.
- Frontend: 11 Vitest cases passed; ESLint、TypeScript、Next.js production build passed.
- Phase 4 (including read-only SQL execution)/5 evaluation MVP suites passed; Phase 6 classification set: 9/9 boundary cases.
- Frontend production image build runs ESLint, TypeScript, Vitest, production compilation and `pnpm audit --prod`; audit reported no known production dependency vulnerabilities.
- Python dependency audit reported no known vulnerabilities after upgrading the image's pip and pytest; the locally built `price-lens` package is not published on PyPI and is skipped by the advisory service.
- Docker API/frontend/db healthy. Health, `/docs`, homepage and AI Search POST returned success. Reason query without imported matching official documents abstained with an explicit warning.
- Synthetic Phase 5 set: Recall@5, MRR, citation host check, and abstention accuracy all 1.0 over 3 queries / 9 documents. These are not coverage or semantic-quality claims.

## Known limits and follow-up gate

- CI has been authored and the same core checks were run locally; GitHub-hosted CI cannot report a green run until this repository is pushed. `pip-audit` depends on its live advisory service.
- No committed real-data database snapshot: source data is public but raw dumps are intentionally excluded. Demo uses the existing local PostgreSQL volume; a clean install needs an ETL backfill before product charts populate.
- Backup/restore smoke and release latency smoke are available as opt-in local drills (`make backup-smoke`, `make demo-eval`); they must be run in the release environment before publishing.
- Playwright E2E and representative load test remain release follow-ups; unit/component tests and local endpoint smoke do not replace them.
- RAG uses lexical character n-grams, manual publication/event/product metadata, and an empty-by-default document store. No semantic embedding or generated causal explanation.
- No LoRA experiment was run: the frozen normalization and intent sets currently show no errors to target, so there is no evidence-based fine-tuning hypothesis. Do not treat a perfect small MVP set as production generalization.
- Release smoke is an opt-in local report, not a scheduled alerting service. Data lag is reported for review rather than silently treated as a price.
