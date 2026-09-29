# Phase 4 Review — Controlled AI and Safe Text2SQL

日期：2026-09-28  
狀態：Phase 4 實作與驗證完成；Phase 5 已於 2026-09-29 獲批准並開始

## 1. Delivered

- `POST /api/v1/ask` 的版本化 Pydantic answer contract。
- code-based product alias normalization 與 deterministic intent router。
- 常見商品現況、近期變化、原因提問與漲跌榜優先走 typed analytics tools。
- provider abstraction 與可重現的 `price-lens-rules-v1` baseline provider。
- 四個 allowlisted analytics semantic views。
- `sqlglot` AST validator、單 statement SELECT policy、LIMIT cap 與危險函式封鎖。
- 獨立 `price_lens_text2sql` PostgreSQL login、read-only transaction、statement/lock timeout 與獨立 pool。
- execution 前 `EXPLAIN (FORMAT JSON)` cost gate 與結果列數限制。
- template answer composer、provider failure fallback 與 privacy-preserving structured trace log。
- 首頁真實 AI Search flow、loading/error/abstention、可見日期／批發單位／scope／官方來源。
- OpenAPI snapshot 與 generated TypeScript API schema。

Phase 4 review 時尚未包含 RAG；後續 Phase 5 狀態見 README 與 architecture.md。Agent orchestration 與 LoRA 不屬於 Phase 5。

## 2. Safety Boundary

Text2SQL 只能存取：

- `analytics.v_product_daily`
- `analytics.v_latest_product_status`
- `analytics.v_weekly_movers`
- `analytics.v_market_product_daily`

防線依序為 provider schema context、AST allowlist、LIMIT cap、EXPLAIN cost gate、獨立連線池，以及資料庫角色本身的 `default_transaction_read_only=on`。整合測試以該角色實際登入，確認 SELECT 成功，而 `DELETE` 與 `CREATE TABLE` 均由 PostgreSQL 拒絕。

Trace log 保存 `trace_id`、question SHA-256、字數、route、intent、provider/model、row count 與 latency；不保存完整使用者問題或 credential。

## 3. Truthfulness

- 所有回答固定標示 `TWD/kg wholesale`，不是零售售價。
- `as_of` 是最新可用交易日，不冒充日曆今天。
- product mapping、market scope、classification 與來源均保留在 structured response。
- 問「為什麼」時只回覆已計算的價格事實，並聲明尚無相符官方文件可證明原因。
- 數字完全來自 deterministic analytics 或 read-only SQL；provider 不計算價格。

## 4. Verification

| Gate | Result |
|---|---:|
| Ruff | pass |
| backend unit/non-live tests | 68 passed |
| PostgreSQL integration tests | 4 passed |
| frontend Vitest | 11 passed |
| Playwright desktop + Pixel 7 critical paths | 4 passed |
| frontend ESLint | pass |
| Next.js production build / typecheck | pass |
| normalization set | 18/18 |
| intent/route set | 14/14 |
| Text2SQL validation + live execution | 10/10 |
| destructive/adversarial blocking | 20/20 |

Versioned datasets live under `evals/datasets`; the recorded report is `evals/reports/phase4-controlled-ai.v1.json`. The evaluation used Python 3.12.14 on WSL2, provider `rules`, model `price-lens-rules-v1`, and prompt version `text2sql-rules-v1`.

## 5. Known Limitations

- The default rules provider intentionally covers a narrow, deterministic question set. No hosted LLM credential is required or exercised.
- The evaluation set is small and curated for the MVP; 100% does not imply unrestricted natural-language or arbitrary SQL accuracy.
- Text2SQL answers currently use template verbalization and return at most 100 rows.
- Market-comparison queries use the latest date available for that product across market series; sparse individual markets may need a future per-market freshness policy.
- RAG and causal evidence are absent by design until Phase 5.

## 6. Review Gate

Phase 4 stops here. Phase 5 should begin only after explicit user approval and should add official-document retrieval, product/time filtering, reranking, nearby citations and abstention evaluation without weakening the current SQL or database boundaries.
