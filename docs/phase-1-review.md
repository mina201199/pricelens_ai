# Phase 1 Review Report

執行日期：2026-09-28（Asia/Taipei）  
範圍：Project Foundation + Government Data ETL + PostgreSQL  
狀態：完成並於 2026-09-28 通過使用者 review；本文件保留當時的 Phase 1 驗證快照。

## 1. 交付結果

- 初始化 Git repository（branch `main`），加入 `.gitignore` 與 `.env.example`。
- 建立 Python 3.12 / FastAPI / SQLAlchemy / Alembic 模組化 backend。
- 建立 PostgreSQL 16 Docker Compose 開發環境與獨立 integration-test database bootstrap。
- 實作農業部 `AgriProductsTransType` 與 `CropMarketType` source adapter。
- 完成 fetch → validate → clean/normalize → map → raw audit → idempotent load。
- 保留官方 payload、source hash、source product/market code/name、fetch time、ingestion run 與 source metadata。
- 建立 v1 code-and-name-based canonical product mapping；未知或名稱不符的 code fail closed。
- 建立 structured logging、retry/backoff、HTTP/API envelope error、truncation error、quarantine 與 failed-run 紀錄。
- 建立 health/data-status API、ETL/data-quality CLI、unit/integration/live contract tests。

## 2. 新增／修改檔案

### Repository / infrastructure

- `.gitignore`, `.env.example`, `compose.yaml`, `Makefile`
- `infra/postgres/init/01-create-test-database.sql`
- `backend/Dockerfile`, `backend/.dockerignore`, `backend/pyproject.toml`

### Database

- `backend/alembic.ini`
- `backend/migrations/env.py`
- `backend/migrations/script.py.mako`
- `backend/migrations/versions/0001_phase1_data_foundation.py`
- `backend/src/price_lens/db/{base,models,session}.py`

### ETL / application

- `backend/src/price_lens/{config,logging_config,cli,data_quality}.py`
- `backend/src/price_lens/ingestion/normalize.py`
- `backend/src/price_lens/ingestion/mapping.py`
- `backend/src/price_lens/ingestion/loader.py`
- `backend/src/price_lens/ingestion/sources/moa.py`
- `backend/src/price_lens/ingestion/validation/schemas.py`
- `backend/src/price_lens/ingestion/jobs/market_etl.py`
- `backend/src/price_lens/ingestion/mappings/product_mappings.v1.json`
- `backend/src/price_lens/api/app.py`
- `backend/src/price_lens/schemas/status.py`

### Tests / docs

- `backend/tests/unit/test_{normalize,mapping,validation,moa_client}.py`
- `backend/tests/integration/test_idempotent_etl.py`
- `backend/tests/contract/test_moa_live.py`
- 更新 `README.md`, `AGENTS.md`, `docs/architecture.md`, `docs/data-source-assessment.md`
- 新增本文件 `docs/phase-1-review.md`

## 3. 最終目錄結構

```text
price check/
├─ .env.example
├─ .gitignore
├─ AGENTS.md
├─ Makefile
├─ README.md
├─ compose.yaml
├─ backend/
│  ├─ .dockerignore
│  ├─ Dockerfile
│  ├─ alembic.ini
│  ├─ pyproject.toml
│  ├─ migrations/
│  │  ├─ env.py
│  │  ├─ script.py.mako
│  │  └─ versions/0001_phase1_data_foundation.py
│  ├─ src/price_lens/
│  │  ├─ api/
│  │  ├─ db/
│  │  ├─ ingestion/{jobs,mappings,sources,validation}/
│  │  ├─ schemas/
│  │  ├─ cli.py
│  │  ├─ config.py
│  │  ├─ data_quality.py
│  │  └─ logging_config.py
│  └─ tests/{unit,integration,contract}/
├─ docs/
│  ├─ architecture.md
│  ├─ data-source-assessment.md
│  ├─ phase-1-review.md
│  └─ decisions/                  # later ADRs
├─ frontend/{src,tests}/          # tracked placeholders; no Phase 1 UI
├─ evals/{datasets,reports,runners}/
├─ data/samples/
├─ scripts/
└─ infra/postgres/init/01-create-test-database.sql
```

Phase 0 規劃中的 `frontend/`, `analytics/`, `ai/`, `evals/` 以 `.gitkeep` 追蹤目錄邊界，但沒有提前加入任何 Phase 2+ 功能。

## 4. Database schema

實際 migration 在 PostgreSQL 16.15 成功建立 8 張表：

| schema.table | purpose | key constraint |
|---|---|---|
| `core.data_sources` | publisher、dataset/API URL、license | unique `code` |
| `core.ingestion_runs` | window、status、request、各類筆數、錯誤、code version | PK `id` |
| `raw.market_records` | 完整官方 JSON、hash、validation status/errors | unique `(source_id, source_record_hash)` |
| `core.markets` | 交易 payload 的官方市場 code/name | unique `(source_id, source_market_code)` |
| `core.product_families` | canonical consumer family | unique `canonical_name` |
| `core.product_aliases` | 高麗菜等查詢 alias | unique `(family_id, normalized_alias)` |
| `core.products` | 官方 source product + mapping decision/version | unique `(source_id, source_product_code)` |
| `core.market_price_observations` | 日期 × 市場 × source product 批發行情 | unique `(source_id, trade_date, market_id, product_id)` |

價格為 `numeric(12,2)`、交易量為 `numeric(16,2)`、交易日為 Gregorian `date`、稽核時間為 `timestamptz`。fact table 對正價與正交易量加 DB check constraints；raw/quarantine 不受這些 analytics constraints 限制。

## 5. ETL flow

```text
CropMarketType Veg/Fruit
  → deduplicate official MarketName query aliases
  → for each Gregorian day × market alias
  → AgriProductsTransType with ROC Start_time/End_time
  → reject RS != OK, HTTP failure after retry, or Next=true
  → require each non-empty partition to contain one MarketCode
  → Pydantic schema + ROC date + Decimal validation
  → closure exclusion / malformed quarantine
  → source hash + raw JSON audit insert
  → explicit source code + expected name canonical mapping
  → market/product dimension upsert
  → observation natural-key insert/update/unchanged classification
  → ingestion-run counters and data-quality report
```

HTTP 失敗使用 bounded exponential backoff；任何日期失敗會將 ingestion run 設為 `failed`，不把不完整 window 標為成功。每日各自 transaction，避免整段 backfill 一次佔用大量記憶體。

## 6. Actual data / data quality

官方來源：[農業資料開放平臺資料集 037](https://data.moa.gov.tw/open_detail.aspx?id=037) / `AgriProductsTransType`。驗證 window 為 2026-09-24 單日。

| metric | result |
|---|---:|
| raw records received / stored | 2,363 / 2,363 |
| valid observations | 2,352 |
| date range | 2026-09-24 – 2026-09-24 |
| distinct observed source products | 727 |
| distinct observed markets | 13 |
| duplicate natural-key groups | 0 |
| null / invalid price rows in fact | 0 |
| excluded closure rows | 0 |
| quarantined raw rows | 11 |
| unmapped source products | 693 |

11 筆 quarantine 均位於交易市場 code `105`：官方 payload 有 `CropCode`、價格及交易量，但 `TcType` 與 `CropName` 空白。它們保留於 raw audit，未建立 product/fact。

### 甘藍 source samples

| code | official name | canonical family | default analytics |
|---|---|---|---|
| `LA1` | 甘藍-初秋 | 甘藍 | include |
| `LA2` | 甘藍-改良種 | 甘藍 | include |
| `LA7` | 甘藍-改良尖 | 甘藍 | include |
| `LA4` | 甘藍-紫色 | 甘藍 | exclude |
| `LA5` | 甘藍-甘藍心 | 甘藍 | exclude |
| `LA6` | 甘藍-甘藍芽 | 甘藍 | exclude |
| `LA9`, `LA91`, `LA92`, `LA94` | 甘藍-進口… | 甘藍 / imported | exclude |

`SW1` 球莖甘藍映射到獨立 family，不因名稱包含「甘藍」併入高麗菜。mapping 同時比對 code 與 expected official name；code/name 不一致時不自動歸類。

### 真實資料 idempotency

同一日期第二次完整抓取：`received=2363`, `inserted=0`, `updated=0`, `unchanged=2352`, `quarantined=11`。資料庫仍為 2,352 facts 與 2,363 distinct raw hashes，duplicate group 為 0。

## 7. Tests

- Ruff：all checks passed。
- Unit / non-live suite：**23 passed, 1 live deselected**；涵蓋日期轉換、hash、validation、closure、mapping fail-closed、API query/retry/truncation/market partition、failed-run audit 與 PostgreSQL integration。
- PostgreSQL integration：從空 test schemas 跑 migration，同一 fixture ETL 兩次，assert fact/raw 各 1、run 2 筆。
- Live contract：**1 passed**；官方市場參照 + 單日單市場 payload 可通過目前 validator。
- 實際 ETL：PostgreSQL 16.15，官方單日全市場分區，並完成第二次重跑。
- API smoke：`/api/v1/health` 與 `/api/v1/data-status` 均回傳 HTTP 200；data-status 回報 2,352 observations、727 products、13 markets。

live test 需 `RUN_LIVE_CONTRACT_TESTS=1` 才執行，避免一般 unit run 意外依賴網路。

本機未安裝 Docker Desktop，因此本次無法執行 `docker compose up` runtime smoke test；Compose/Dockerfile 已人工檢查，migration、integration 與 ETL 則使用真實 PostgreSQL 16.15 驗證，不是 SQLite mock。

## 8. 如何重新執行

```powershell
Copy-Item .env.example .env
docker compose up --build -d db api
docker compose --profile tools run --rm etl etl --start 2026-09-24 --end 2026-09-24
docker compose --profile tools run --rm etl data-quality
docker compose run --rm api pytest -m "not live"
docker compose run --rm api ruff check .
```

重跑相同 ETL window 是正常操作。若官方歷史資料被修訂，hash 不同的同 natural key 會 update；完全相同則計入 unchanged。

## 9. Phase 0 assumptions 與實際差異

1. **不能依賴未授權分頁。** `Next=true` 後的 `Page=2` 對非會員回傳 error，因此從「短 window + 翻頁」改為「單日 × 市場 query partition + Next fail closed」。
2. **市場參照並非 authoritative dimension。** 參照 API 的 `台北市 / 100` 對應交易 API 的 `台北市場 / 105`。query alias 與交易 code/name 因此分離，DB 保存交易 payload。
3. **ingestion counters 增加。** 實際 schema 比 Phase 0 多 `records_unchanged` 與 `records_excluded`，用來證明 idempotency 與休市處理。
4. **官方有半結構化缺漏。** 11 筆有價格但缺商品名稱／種類；採 quarantine，不猜商品。
5. **市場數不能寫死。** 20 個市場 query alias 在該日只有 13 個市場回報有效觀測；API/UI contract 必須回傳實際 `market_count`。

## 10. Known issues / technical debt

- 尚未做 24 個月 backfill、30 日 completeness matrix、歷史修訂率與 latency baseline。
- 未取得官方明確 rate-limit 數字；目前以 concurrency=5、retry=3 保守執行。
- 尚未加入 OS scheduler／CI schedule；CLI 的 `--days 7` 已可由 cron、Task Scheduler 或 CI 定期呼叫。
- v1 mapping 只主動涵蓋 MVP family；727 個觀測商品中 693 個保持 unmapped 是 fail-closed 設計，不是自動以名稱猜測。
- raw hash 去重保存第一次看到該 payload 的 run；重抓歷史可由 run counters 看到 unchanged，但若要 many-to-many re-fetch lineage，未來需新增 run-record association table。
- market reference discrepancy 目前記錄在文件；長期應建立可版本化的 market query alias/reference table 與告警。
- Docker development image目前包含 dev dependencies 以確保測試可重現；部署階段再拆 production target。

## 11. Phase 2 建議

進 Phase 2 前先完成受控 backfill 與 coverage baseline，再建立 analytics，避免在單日樣本上鎖定分類規則：

1. 先 backfill 至少 24 個月，逐日輸出 received/quarantine/market coverage，任何 `Next=true` 停止該 run。
2. 對 MVP families 完成 source-code coverage review，特別檢查 code/name 漂移與新增品種。
3. 建立 volume-weighted canonical daily series，保存 included codes、market count、total volume 與 calculation version。
4. 以 hand-calculated golden fixtures 實作 7/30/90D、WoW/MoM、percentile、z-score、volatility 與 classification v0。
5. 再開 typed radar/movers/detail API；所有 response 固定包含 `as_of`, `scope`, `unit=TWD/kg wholesale`, source 與 warnings。

不要在 Phase 2 同時加入 Text2SQL、RAG 或 LLM；先把 deterministic analytics 與 data coverage 驗證完成。
