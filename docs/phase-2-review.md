# Phase 2 Review Report

執行日期：2026-09-28（Asia/Taipei）  
範圍：Price Analytics Engine + Typed Backend API  
狀態：完成，等待使用者 review；未進入 Phase 3。

## 1. 交付結果

- 新增 Alembic `0002_phase2`：canonical product slug 與 `analytics.daily_product_metrics`。
- 建立 SQL volume-weighted daily aggregation，以及 Python deterministic rolling metrics/classification。
- 支援 `all_reporting_markets` 與 `market:{source_market_code}` scopes。
- 加入 365 日 mapped-product official backfill 模式與 adaptive date-window split。
- 實作 products、radar、movers、summary、history typed APIs。
- 建立 unit golden fixtures、classification boundary tests、PostgreSQL weighted aggregation、refresh idempotency與 API integration tests。
- 實際載入一年官方資料並重建 32,806 筆 analytics rows。

未實作 Frontend、Text2SQL、RAG、Agent、LoRA 或 LLM explanation。

## 2. 新增／主要修改檔案

- `backend/migrations/versions/0002_phase2_analytics.py`
- `backend/src/price_lens/analytics/calculator.py`
- `backend/src/price_lens/analytics/refresh.py`
- `backend/src/price_lens/analytics/service.py`
- `backend/src/price_lens/api/routes/analytics.py`
- `backend/src/price_lens/schemas/analytics.py`
- `backend/tests/unit/test_analytics_calculator.py`
- `backend/tests/integration/test_analytics_refresh.py`
- 更新 models、CLI、status API、ETL source adapter、mapping、Docker Compose、README 與 architecture docs。

## 3. Database schema

`core.product_families` 新增 unique `slug`，例如 `cabbage`, `tomato`, `banana`。

`analytics.daily_product_metrics` 保存：

- identity：`trade_date`, `family_id`, `scope_key`, optional `market_id`
- daily base：`weighted_avg_price`, `total_volume_kg`, `market_count`, `product_count`, `included_product_codes`
- rolling：`ma_7d`, `ma_30d`, `ma_90d`
- comparison：`wow_change_pct`, `mom_change_pct`, `volume_change_pct`
- distribution：`percentile_365d`, `z_score_365d`, `robust_z_365d`
- extremes：365 日 `historical_high/low` price/date
- risk：`volatility_30d`
- audit：`history_day_count`, `classification`, calculation/classification version, `computed_at`

Versioned unique key：`(trade_date, family_id, scope_key, calculation_version, classification_version)`。目前版本為 `daily-canonical-v1` / `price-classification-v1`。

## 4. Calculation definitions

### Daily price

```text
Σ(source average price × volume kg) / Σ(volume kg)
```

只納入 `analytics_included=true` 且有明確 canonical family 的 source products。進口、特殊部位或名稱相似品項不會因 substring 自動加入。

### Rolling and comparisons

- MA：最近 7/30/90 個日曆日內「可用交易日 daily canonical price」的算術平均。
- WoW/MoM：目標為 7/30 日前，取當天或之前最近交易日；若再早超過 7 日則 null。
- Percentile：最近 365 日 midpoint empirical rank，constant series 為 50 而不是 100。
- Z-score：365 日 population standard deviation。
- Robust z：`0.6745 × (current - median) / MAD`；MAD=0 時為 null。
- Volume change：最近 7 日總量相對前 7 日。
- Volatility：最近 30 日 daily log return 的 population standard deviation，少於 2 個 returns 時為 null。
- High/low：最近 365 日；同價保留最早日期。

### Classification v1

1. 少於 120 個有效日：`insufficient_data`
2. percentile ≥95 且 robust z ≥2：`anomalously_high`
3. percentile ≥75 或 current/MA30 ≥1.15：`high`
4. percentile ≤25 或 current/MA30 ≤0.85：`low`
5. 其他：`normal`

這是可重現的 rule label，不代表已經過消費者零售價或專家 ground-truth 驗證。

## 5. Actual official data

365 日 mapped-product backfill window：2025-09-25～2026-09-24。

| ETL metric | result |
|---|---:|
| received | 69,169 |
| inserted | 68,971 |
| unchanged | 187 |
| quarantined in this run | 11 |
| run status | succeeded |

合併 Phase 1 後的 database quality：

| metric | result |
|---|---:|
| normalized observations | 71,323 |
| observation date range | 2025-09-25 – 2026-09-24 |
| source products | 743 |
| markets | 20 |
| duplicate observation keys | 0 |
| null / invalid fact prices | 0 |
| raw quarantined records | 22 |

本次 backfill 只含 mapping v1 的 70 個 source codes；`request_params.data_scope` 保存為 `mapped_mvp_products_only`，不宣稱是 365 日全品項 coverage。

## 6. Analytics results

| metric | result |
|---|---:|
| analytics rows | 32,806 |
| family/scope series | 126 |
| canonical families | 8 |
| distinct scope keys | 20 |
| date range | 2025-09-25 – 2026-09-24 |
| versioned duplicate groups | 0 |
| refresh latency | 61.90 seconds |

最新 all-market snapshot：

| product | as of | TWD/kg wholesale | WoW | percentile | days | class |
|---|---|---:|---:|---:|---:|---|
| 香蕉 | 2026-09-24 | 26.2058 | -15.7158% | 37.781 | 356 | normal |
| 甘藍（高麗菜） | 2026-09-24 | 35.1106 | +12.1587% | 96.016 | 364 | high |
| 小番茄 | 2026-09-24 | 132.7082 | +17.6050% | 96.761 | 355 | high |
| 球莖甘藍 | 2026-08-15 | 21.0000 | null | 89.729 | 258 | high |
| 包心白菜 | 2026-09-24 | 24.4213 | -6.1417% | 95.192 | 364 | high |
| 洋蔥 | 2026-09-24 | 26.0605 | +1.9641% | 79.060 | 351 | high |
| 木瓜 | 2026-09-24 | 44.0432 | +8.0550% | 44.803 | 356 | high |
| 番茄 | 2026-09-24 | 87.9499 | +16.4988% | 92.995 | 364 | high |

木瓜雖 percentile 接近中位數，仍因 current/MA30 ≥1.15 被標記 high。UI 必須顯示 rule evidence，不能只顯示顏色。球莖甘藍資料較舊，因此保留於 radar/detail 並顯示 `as_of`，但被排除於相對 2026-09-24 的 movers 榜。

## 7. API surface

```text
GET /api/v1/products
GET /api/v1/radar
GET /api/v1/movers?direction=up|down&period=7d|30d
GET /api/v1/products/{slug-or-alias}/summary
GET /api/v1/products/{slug-or-alias}/history?range=1m|3m|6m|1y|2y|all&market=all|CODE
```

所有 summary 固定包含 `as_of`, product identity, scope, `TWD/kg wholesale`, included source codes, metrics, classification/version, calculation version, source 和 warnings。`高麗菜` alias 與 `cabbage` slug 均可解析為 canonical `甘藍`。

Movers 僅保留符合方向正負號的商品，並排除落後全體最新日超過 7 天的 stale series。

## 8. Tests and latency

- Ruff：all checks passed。
- Non-live suite：35 passed，1 live deselected。
- Official live contract：1 passed；驗證市場分區與 `CropCode` 精確 filter。
- PostgreSQL integration：migration、17.5 weighted golden result、refresh repeatability、alias resolution、typed API、mover direction。
- API TestClient baseline，20 warm requests：

| endpoint | median | p95 |
|---|---:|---:|
| cabbage summary | 5.66 ms | 6.60 ms |
| radar | 7.96 ms | 10.03 ms |
| movers | 8.65 ms | 9.16 ms |

這是同機 process + local PostgreSQL baseline，不代表網路部署 latency。

## 9. Re-run locally

```powershell
Copy-Item .env.example .env
docker compose up --build -d db api

docker compose --profile tools run --rm etl etl `
  --start 2025-09-25 --end 2026-09-24 `
  --job-type mapped-backfill --mapped-products-only

docker compose --profile tools run --rm etl analytics-refresh
docker compose --profile tools run --rm etl data-quality

docker compose run --rm api pytest -m "not live"
docker compose run --rm api ruff check .
```

Analytics refresh 先計算完整 replacement，再在一個 transaction 中刪除／寫入目前版本；API 不會看到半套 refresh。

## 10. Known issues / technical debt

- Classification v1 尚無人工標註 ground-truth accuracy；目前只能聲稱 rule fixtures 正確。
- 365 日 backfill 是 mapped MVP codes，不是全品項 historical completeness。
- Refresh 約 61.9 秒；Phase 3 可接受，但未來應以 sliding windows／SQL window functions 降低 CPU 與 replacement write cost。
- 沒有自動 scheduler；CLI 可由 Task Scheduler、cron 或 CI 呼叫。
- `analytics.daily_product_metrics` 為 full rebuild；尚未做 incremental affected-window recompute。
- TestClient 顯示 upstream Starlette/httpx deprecation warning，不影響測試結果，但 dependency upgrade 時需處理。
- Radar 保留 stale products 並依 `as_of` 說明；正式 UI 必須提供 freshness warning。
- 仍未建立固定市場 panel 敏感度分析，市場組成變動可能影響 all-market series。
- 本機沒有 Docker Desktop，Compose runtime 尚未 smoke test；真實 PostgreSQL 16.15 migration、ETL、analytics 與 API 已驗證。

## 11. Phase 3 建議

1. 直接使用 typed APIs 建立 Next.js product UI，不在 frontend 重算任何 metric。
2. 首頁 radar 同時顯示 classification、批發元/kg、`as_of`、market count 與 freshness。
3. Movers 分開上漲／下跌，顯示 period 與 scope，不把 high/low classification 混同於短期漲跌。
4. 商品頁畫 price 與 volume，並將 percentile、MA、historical high/low 的 rule evidence 展開。
5. 完成 loading、empty、stale、partial、API error states，以及 desktop/mobile/accessibility checks。
6. AI Search 在 Phase 3 只做 UI shell；不要提前接 LLM 或 fake answer。
