# Price Lens — AI 民生物價雷達

> 將台灣官方農產品批發市場交易資料，轉成可追溯、可解釋的價格訊號。

**目前的 AI Search 是規則 baseline，尚未接 LLM。** 意圖判斷用關鍵字規則，Text2SQL 用規則模板產生 SQL，官方文件檢索用字元 n-gram hashing 向量；整個系統沒有呼叫 LLM、外部 embedding 或任何學習式模型。SQL 生成透過 provider 介面隔開，架構上可以換成 LLM provider，而 SQL 驗證與唯讀執行限制不變。各元件與對應檔案見 [AI Search 實作現況](#ai-search-實作現況)。

## 專案狀態

**Phase 6 release hardening 已完成首輪驗收。** 系統包含可執行的 Next.js 產品前端、PostgreSQL/pgvector、FastAPI、官方資料 ETL、deterministic price analytics、typed intent routing、安全 Text2SQL，以及官方文件 RAG。首頁 AI Search 會先回答批發價格事實，再以符合商品與日期的農業部官方文件列出有引用的可能背景；無文件時明確 abstain。

官方文件問答採本地可重現的字元 n-gram 向量檢索，不呼叫外部 embedding 或生成模型。文件內容視為不可信資料，引用只表達可能相關背景，不代表已證實因果。Agent orchestration 與 LoRA 不屬於 Phase 5。

Phase 6 新增 CI、凍結的分類邊界 review set、request-id JSON logs、release latency/freshness smoke 報告與一鍵 demo 啟動。LoRA 不進 production：目前凍結的 normalization/intent MVP set 已達滿分，尚無錯誤切片可證明微調能帶來可測提升。

### AI Search 實作現況

「AI Search」目前是可重現的規則 baseline，不是 LLM 應用：

| 元件 | 目前實作 | 檔案 |
|---|---|---|
| 意圖路由 | 關鍵字規則（例如「為什麼」、「漲／跌」、「排行」），決定走 typed analytics 工具或 Text2SQL | `backend/src/price_lens/ai/router.py` |
| Text2SQL | `RulesSqlProvider`（`price-lens-rules-v1`）以規則模板產生 SQL；設定 `AI_PROVIDER` 預設為 `rules` | `backend/src/price_lens/ai/providers.py` |
| SQL 安全層 | sqlglot AST 驗證、只允許 `analytics` 的 allowlisted views、禁用函式、強制 LIMIT；執行時使用唯讀 transaction、statement timeout、EXPLAIN 成本門檻與專用唯讀 DB 角色 | `backend/src/price_lens/ai/text2sql/validator.py`、`backend/src/price_lens/ai/text2sql/executor.py` |
| 官方文件檢索（RAG） | 1–3 字元 n-gram 以 feature hashing 轉成 256 維向量，存在 pgvector（HNSW、cosine）；沒有生成模型，只列出引用文件 | `backend/src/price_lens/rag/documents.py`、`backend/migrations/versions/0004_phase5_official_rag.py` |

Provider 可替換的範圍：`AskService`（`backend/src/price_lens/ai/service.py`）以建構參數注入 SQL provider，介面是 `SqlGenerationProvider.generate_sql()`。目前唯一的實作是 `RulesSqlProvider`；`AI_PROVIDER` 設定已預留，但程式還沒有依它切換 provider。日後接上 LLM provider 時，產生的 SQL 仍要通過同一套驗證與執行限制。

## 資料語意

Price Lens 使用農業部「農產品交易行情」：

- 價格是**批發市場交易行情**，單位為 **TWD/kg（元／公斤）**。
- 它不是超市、傳統市場、電商或特定商店的零售售價。
- 現階段不能直接判斷某間商店是否賣太貴，也不把「一斤」當成 API 原始單位。
- 官方代碼與名稱原樣保存；消費者名稱（例如「高麗菜」→「甘藍」）位於獨立、版本化 mapping。

官方資料來源：[政府資料開放平臺資料集 8066](https://data.gov.tw/dataset/8066)、[農業資料開放平臺資料集 037](https://data.moa.gov.tw/open_detail.aspx?id=037)、[AgriProductsTransType API](https://data.moa.gov.tw/api/v1/AgriProductsTransType/)。

## 目前架構

```text
MOA official API
  → date × official market partitioned fetch
  → Pydantic validation / quarantine
  → ROC date and numeric normalization
  → versioned product code mapping
  → raw.market_records (immutable source audit)
  → core dimensions + market_price_observations (idempotent upsert)
  → analytics.daily_product_metrics
      ├─ volume-weighted daily canonical prices
      ├─ 7/30/90D, WoW/MoM, percentile, z-score
      ├─ high/low, volume change, volatility
      └─ versioned price classification
  → typed radar / movers / summary / history tools
  → controlled intent router
      ├─ known questions → deterministic analytics tools
      └─ exploratory questions → SQL AST validator
           → EXPLAIN cost gate → dedicated read-only DB role
           → allowlisted analytics semantic views only
  → versioned answer contract + template fallback + trace log
  → Next.js product UI
      ├─ market radar + weekly movers
      ├─ product summary + price/volume chart
      ├─ visible freshness, scope and provenance
      ├─ sourced natural-language price search
      └─ honest loading / empty / stale / error states
```

PostgreSQL 使用 `raw`、`core` 與 `analytics` schema。唯一鍵 `(source_id, trade_date, market_id, product_id)` 防止 observation 重複；source payload 另以 `(source_id, source_record_hash)` 去重。價格與數量均以 `numeric` 保存。

## 本機啟動（Docker Compose）

需求：Git、Docker Desktop（含 Docker Compose v2）。

```powershell
Copy-Item .env.example .env
docker compose up --build -d db api frontend
docker compose ps
```

Windows PowerShell 可用 `./scripts/demo.ps1` 啟動並等待 API 健康檢查；停止服務用 `docker compose down`（不加 `-v`，保留行情資料）。

### 匯入官方背景文件

僅允許 `moa.gov.tw`、`agrstat.moa.gov.tw`、`afa.gov.tw` 的 HTTPS HTML。匯入者必須標記發布日期、事件期間及一個或多個 canonical product slug；系統以來源 URL 更新文件、依正文 SHA-256 去重 chunk，並保留抓取時間。

```powershell
docker compose run --rm api python -m price_lens.rag.cli ingest `
  https://www.afa.gov.tw/example `
  --published-at 2026-09-20 --event-start 2026-09-18 --event-end 2026-09-24 `
  --product cabbage
```

日期與商品範圍需要由匯入者根據原始文件確認，不會從文件文字自動推定。問答只檢索在價格資料日以前發布、商品標籤吻合且事件期間與近 60 日窗口重疊的文件。

Phase 5 檢索 baseline 評估使用固定、去識別的 query-document fixtures：

```powershell
docker compose run --rm api python /app/evals/runners/phase5_rag_eval.py
```

結果寫至 `evals/reports/phase5-rag.v1.json`，包含 Recall@5、MRR、官方網域引用率與 abstention accuracy。此 lexical baseline 評估不代表正式語意搜尋效能或真實文件覆蓋率。

開啟：

- Product UI: <http://localhost:3000>
- FastAPI / OpenAPI: <http://localhost:8000/docs>

API 啟動時會先執行 migration，並以 `TEXT2SQL_DATABASE_URL` provision 專用唯讀登入角色：

- Health: <http://localhost:8000/api/v1/health>
- Data status: <http://localhost:8000/api/v1/data-status>
- Products: <http://localhost:8000/api/v1/products>
- Price radar: <http://localhost:8000/api/v1/radar>
- Weekly movers: <http://localhost:8000/api/v1/movers?direction=up&period=7d>
- Cabbage summary: <http://localhost:8000/api/v1/products/cabbage/summary>
- Cabbage history: <http://localhost:8000/api/v1/products/cabbage/history?range=1y&market=all>
- Controlled AI: `POST http://localhost:8000/api/v1/ask`，body 為 `{"question":"高麗菜現在算貴嗎？"}`
- OpenAPI: <http://localhost:8000/docs>

執行指定日期 ETL（輸入為西元日期，adapter 會轉成官方民國日期）：

```powershell
docker compose --profile tools run --rm etl etl --start 2026-09-24 --end 2026-09-24
docker compose --profile tools run --rm etl data-quality
```

受限於明確 mapping source codes 的一年期 MVP backfill：

```powershell
docker compose --profile tools run --rm etl etl `
  --start 2025-09-25 --end 2026-09-24 `
  --job-type mapped-backfill --mapped-products-only
docker compose --profile tools run --rm etl analytics-refresh
```

`--mapped-products-only` 是加速 analytics 歷史資料的受限模式，ingestion metadata 會明確標示 scope；它不代表同期間所有農產品都有完整 backfill。

預設增量同步最近 7 個日曆日：

```powershell
docker compose --profile tools run --rm etl etl --days 7
```

停止服務：

```powershell
docker compose down
```

`.env` 已被 Git 忽略；請勿提交真實密碼。`price_lens_test` 只在全新 PostgreSQL volume 初始化時建立，專供會清除 schema 的 integration test 使用。

## Migration、測試與 lint

```powershell
docker compose run --rm api alembic upgrade head
docker compose run --rm api pytest -m "not live"
docker compose run --rm api ruff check .
docker compose run --rm -v "${PWD}:/workspace" -w /workspace `
  -e PYTHONPATH=/workspace/backend/src api `
  python evals/runners/phase4_eval.py --execute
```

官方 API live contract test 必須明確 opt-in：

```powershell
docker compose run --rm -e RUN_LIVE_CONTRACT_TESTS=1 api pytest tests/contract/test_moa_live.py -q
```

常用指令也可透過 `make up`、`make etl`、`make analytics`、`make quality`、`make test`、`make lint` 執行。

### 不使用 Docker 的前端開發

先啟動 PostgreSQL 與 FastAPI，再使用 Node.js 24 與 pnpm 11：

```powershell
Set-Location frontend
pnpm install --frozen-lockfile
$env:PRICE_LENS_API_URL = "http://127.0.0.1:8000"
pnpm dev
```

前端品質檢查：

```powershell
pnpm typecheck
pnpm lint
pnpm test
pnpm build
pnpm exec playwright install chromium  # 首次執行 E2E 才需要
pnpm test:e2e                         # 需有 API + DB 與官方資料
```

`PRICE_LENS_API_URL` 只在 Next.js server 端使用；瀏覽器不直接持有資料庫或後端 credential。E2E 同時驗證桌面與 Pixel 7 viewport，並要求 Recharts SVG 確實渲染，避免空白圖表誤判為成功。

## 實際驗證快照

2026-09-28 完成官方資料一年期 mapped-product backfill 與 analytics refresh：

| metric | result |
|---|---:|
| normalized observations | 69,158 |
| observation date range | 2025-09-25 – 2026-09-24 |
| observed source products | 50 |
| observed markets | 19 |
| quarantined source records | 11 |
| duplicate natural-key groups | 0 |
| null / invalid prices in fact table | 0 |
| analytics rows | 32,806 |
| canonical families / scopes | 8 / 20 |
| analytics date range | 2025-09-25 – 2026-09-24 |
| analytics refresh latency | 61.90 seconds |

甘藍在最新交易日的回報市場加權批發均價為 35.1106 TWD/kg，7 日變化 +12.1587%，365 日 percentile 96.016，規則分類為 `high`。Phase 4 baseline 評估為 normalization 18/18、intent routing 14/14、Text2SQL validation/execution 10/10、adversarial blocking 20/20；這是小型 MVP set，不代表 unrestricted Text2SQL accuracy。這些數字只描述官方批發市場資料，不是消費者零售報價。完整紀錄見 [Phase 4 Review](docs/phase-4-review.md)。

## 目錄導覽

```text
backend/
  migrations/                    # Alembic schema
  src/price_lens/
    ai/                           # normalization, router, tools, safe Text2SQL
    api/                          # health, status, typed price and ask APIs
    analytics/                    # deterministic calculation + refresh service
    db/                           # SQLAlchemy models and sessions
    ingestion/
      jobs/                       # ETL orchestration
      mappings/                   # versioned canonical product mapping
      sources/                    # official API adapter
      validation/                 # boundary validation / quarantine
    cli.py                        # migrate, etl, analytics-refresh, data-quality
  tests/{unit,integration,contract}/
frontend/
  src/app/                       # App Router pages and route states
  src/components/                # radar, movers, chart, controlled AI search
  src/lib/                       # generated API contract, clients, formatting
  tests/                         # Vitest components + Playwright E2E
  Dockerfile                     # standalone Next.js production image
infra/postgres/init/              # development test DB bootstrap
docs/                             # architecture, source assessment, review
```

完整設計見 [System Architecture](docs/architecture.md)、[官方資料來源評估](docs/data-source-assessment.md) 與 [開發規則](AGENTS.md)。

## Phase 6 驗收

Phase 5 已加入官方文件匯入、pgvector metadata filtering、時間與商品限定檢索、逐條 citation UI，以及無文件 abstention。SQL／Python 計算價格數字；文件提供的只是可能背景，不能單獨當作價格因果證明。

CI 定義於 `.github/workflows/ci.yml`。本機可執行 `make ci`，再於服務啟動時執行 `make demo-eval` 產生 `evals/reports/phase6-release-smoke.v1.json`。分類 review 使用 `classification.v1.jsonl`，報告輸出至 `evals/reports/phase6-classification.v1.json`。所有評估均標示資料集版本；小型合成集分數不可外推為生產準確率。完整 gate、已知風險與檢查快照見 [Phase 6 Review](docs/phase-6-review.md)。

## 授權

本專案的程式碼與文件以 [MIT License](LICENSE) 授權。農業部「農產品交易行情」等官方資料不在 MIT 授權範圍內，依政府資料開放授權條款－第 1 版使用；系統匯入時也會在 `core.data_sources` 記錄這項授權。
