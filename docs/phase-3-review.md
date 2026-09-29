# Phase 3 Review Report — Product Frontend

日期：2026-09-28  
狀態：實作與驗證完成，等待 review；未進入 Phase 4

## 1. Outcome

Phase 3 已完成可執行的 Next.js 產品前端，直接讀取 Phase 2 的 typed FastAPI endpoints。首頁不以聊天框為唯一入口，而先呈現最新批發行情雷達與本週漲跌；商品詳情提供價格／交易量走勢、deterministic classification、判斷指標與完整 provenance。

產品語意保持不變：所有價格皆為農業部農產品批發市場交易行情，單位為元／公斤，不是零售售價。真正的 AI Search、Text2SQL、RAG、Agent 與 LoRA 均未提前實作。

## 2. Implemented surface

### 首頁 `/`

- 最新官方交易日期、偏高／偏低／追蹤商品數摘要。
- 8 個 canonical family 的今日價格雷達。
- 每張卡片顯示批發元／公斤、7 日漲跌、市場數、freshness 與 classification。
- 7 日漲價榜與降價榜；資料不足時保留誠實 empty state。
- AI Search preview shell：輸入問題時明確告知 Phase 4 才開放，不生成假答案。
- 核心 radar API 失敗時顯示 service error；movers 失敗時允許 partial error。

### 商品詳情 `/products/[slug]`

- 最新批發交易量加權均價、7 日變化、classification 與規則式解讀。
- 可切換 1m / 3m / 6m / 1y / 2y 歷史期間。
- Recharts 組合圖：批發均價、30 日均線、交易量。
- 7D / 30D 平均、365 日 percentile、30 日 volatility、交易量、市場數。
- 顯示日期、批發單位、所有回報市場 scope、官方 source、納入 source product codes、計算／分類版本。
- 404、loading、empty、stale 與 global error states。

## 3. Runtime architecture

```text
Browser
  → Next.js App Router (server-rendered pages + client chart/search shell)
  → server-only typed fetch client (`PRICE_LENS_API_URL`)
  → FastAPI typed analytics endpoints
  → PostgreSQL analytics.daily_product_metrics

Recharts receives numeric history already calculated by SQL/Python.
It does not calculate price metrics or classification.
```

The browser does not receive the backend URL as a public environment variable and has no database credentials. Next.js server components fetch the FastAPI responses with `cache: no-store`, preserving freshness and honest backend failure states.

## 4. Main files

```text
frontend/
├─ Dockerfile
├─ package.json
├─ pnpm-lock.yaml
├─ pnpm-workspace.yaml
├─ next.config.ts
├─ playwright.config.ts
├─ vitest.config.ts
├─ src/
│  ├─ app/
│  │  ├─ layout.tsx
│  │  ├─ page.tsx
│  │  ├─ globals.css
│  │  ├─ loading.tsx
│  │  ├─ error.tsx
│  │  ├─ not-found.tsx
│  │  └─ products/[slug]/{page,loading}.tsx
│  ├─ components/
│  │  ├─ ai-search.tsx
│  │  ├─ price-chart.tsx
│  │  ├─ radar-card.tsx
│  │  ├─ movers-panel.tsx
│  │  └─ status/freshness/metric/state/header components
│  └─ lib/{api,format,types}.ts
└─ tests/
   ├─ ai-search.test.tsx
   ├─ format.test.ts
   ├─ status-badge.test.tsx
   └─ e2e/home.spec.ts
```

Repository-level changes：`.env.example` 增加 server-side API URL、`compose.yaml` 增加 frontend service、`Makefile` 增加 web targets、README 與 architecture status 更新。

## 5. Real-data verification

端到端驗證使用 Phase 2 寫入 PostgreSQL 的官方資料，未使用 production mock：

| item | verified value |
|---|---:|
| latest available trade date | 2026-09-24 |
| radar canonical families | 8 |
| latest high classifications | 7 |
| latest low classifications | 0 |
| cabbage weighted wholesale price | 35.1 TWD/kg |
| cabbage WoW | +12.2% |
| cabbage 365D percentile | 96% |
| cabbage classification | 偏高 (`high`) |
| cabbage reporting markets | 12 |
| cabbage included source codes | LA1, LA2, LA7 |

資料庫與 ETL 數量未因 Phase 3 改變；完整 observation / analytics snapshot 見 Phase 1 與 Phase 2 Review。

## 6. Verification results

| check | result |
|---|---|
| TypeScript strict check | pass |
| ESLint | pass |
| Vitest | 3 files, 10 tests passed |
| Next.js production build | pass; `/` and `/products/[slug]` dynamic SSR |
| Playwright desktop | pass |
| Playwright Pixel 7 viewport | pass |
| critical path | homepage → cabbage detail → wholesale disclaimer → chart SVG |
| visual QA | desktop homepage, mobile homepage, desktop product detail reviewed |

視覺 QA 曾發現 chart container 存在但 SVG 尚未渲染。根因是 E2E 以 `127.0.0.1` 進入、Next dev server 預設以 `localhost` 啟動，Next.js 16 阻擋 dev-only cross-origin assets。已依 bundled Next.js 16.3 docs 加入 `allowedDevOrigins: ["127.0.0.1"]`，並將 `.recharts-surface` 可見性與無 page errors 納入 Playwright regression test。

## 7. Run locally

### Docker Compose

```powershell
Copy-Item .env.example .env
docker compose up --build -d db api frontend
```

開啟 <http://localhost:3000>。首次資料庫仍須依 README 執行 ETL 與 analytics refresh。

### Frontend developer loop

```powershell
Set-Location frontend
pnpm install --frozen-lockfile
$env:PRICE_LENS_API_URL = "http://127.0.0.1:8000"
pnpm dev
```

### Quality checks

```powershell
pnpm typecheck
pnpm lint
pnpm test
pnpm build
pnpm exec playwright install chromium
pnpm test:e2e
```

Playwright E2E 需要 PostgreSQL、FastAPI 及已建立的 analytics data。單元與 component tests 不需要資料庫。

## 8. Known issues / technical debt

- E2E 現在使用真實本機資料，能驗證整合但不是完全 hermetic；Phase 6 應增加固定 demo snapshot / test seed，同時保留一條真實資料 smoke path。
- `frontend/src/lib/types.ts` 目前手寫對齊 Pydantic schema；Phase 4 前可由 OpenAPI 產生 types，降低 contract drift。
- 首頁 radar family 清單仍由後端 active mappings 決定，沒有使用者自訂排序或篩選。
- 商品頁目前只顯示 all-reporting-markets scope；市場切換留待有明確 UX 與性能驗證後加入。
- 圖表 volume 使用隱藏的 secondary axis，適合趨勢閱讀但不應被解讀成與 price 共用刻度。
- Next.js dev mode 會顯示 framework indicator；production standalone image 不會顯示。
- 尚未做 automated axe scan、bundle budget 或 Web Vitals baseline；本階段已完成 keyboard focus、skip link、semantic headings、chart accessibility layer 與 reduced-motion handling。
- AI Search 僅是誠實 preview shell；沒有任何 LLM 或自然語言 query execution。
- 本機沒有 Docker CLI / Docker Desktop，因此本輪未在此 host 實際 build Compose image；相同 Dockerfile 所需的 `pnpm install --frozen-lockfile` 與 Next.js production build 已在 bundled Node 24 runtime 通過。應在有 Docker 的 review host 補跑 `docker compose up --build` smoke test。

## 9. Phase 2 assumptions changed by implementation

- 沒有 API schema 或 database schema 變更。
- Next.js 實際鎖定為 16.3.x，App Router 的 dynamic pages 使用 async `params` / `searchParams`。
- Next.js server-side API fetch 取代 browser-to-FastAPI 直連，因此目前不需開放 CORS，也避免將 internal API URL 暴露為 `NEXT_PUBLIC_*`。
- Recharts 3 的 client-side responsive chart 需要實際 hydration 驗收；只檢查容器不夠，因此 E2E gate 改為要求 SVG surface。

## 10. Phase 4 recommendation

Phase 4 建議依序做：

1. 由 OpenAPI 產生／驗證 TypeScript contracts。
2. 建立 provider abstraction、structured intent contract 與 product normalization evaluation set。
3. 先把固定問題路由至既有 typed analytics tools。
4. 建立 allowlisted semantic views、專用 read-only PostgreSQL role 與 timeout/row-limit policy。
5. 使用 SQL AST validator 實作 Text2SQL，先通過 adversarial suite 再接上 UI。
6. 最後才把首頁 AI Search shell 接到 `/api/v1/ask`；RAG 原因解釋仍留在 Phase 5。

Phase 3 完成後停止，等待使用者確認再進入 Phase 4。
