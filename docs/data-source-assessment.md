# 官方資料來源評估

最後驗證：2026-09-28（Asia/Taipei）

## 結論

農業部「農產品交易行情」足以支援 Price Lens 第一版的批發價格分析，包括價格、交易量、品項、市場與日期。它不能單獨回答消費者在零售通路實際會付多少錢，因此產品文案必須使用「批發均價／元每公斤」，不可直接回答「一斤售價」。

## 已驗證的官方入口

- [政府資料開放平臺：農產品交易行情](https://data.gov.tw/dataset/8066)
- [農業資料開放平臺：資料集 037](https://data.moa.gov.tw/open_detail.aspx?id=037)
- [農業部 OpenAPI specification](https://data.moa.gov.tw/openapi.json)
- [新版 API endpoint](https://data.moa.gov.tw/api/v1/AgriProductsTransType/)
- [農產品批發市場交易行情站](https://amis.afa.gov.tw/)

官方頁面標示每日更新，欄位包含：

| 官方欄位 | 新版 API 欄位 | 入庫欄位 | 單位 |
|---|---|---|---|
| 交易日期 | `TransDate` | `trade_date` | date |
| 種類代碼 | `TcType` | `category_code` | code |
| 作物代號 | `CropCode` | `source_product_code` | code |
| 作物名稱 | `CropName` | `source_product_name` | text |
| 市場代號 | `MarketCode` | `source_market_code` | code |
| 市場名稱 | `MarketName` | `source_market_name` | text |
| 上價 | `Upper_Price` | `upper_price` | TWD/kg |
| 中價 | `Middle_Price` | `middle_price` | TWD/kg |
| 下價 | `Lower_Price` | `lower_price` | TWD/kg |
| 平均價 | `Avg_Price` | `average_price` | TWD/kg |
| 交易量 | `Trans_Quantity` | `volume_kg` | kg |

## API 行為驗證

OpenAPI 定義的 operation 為 `AgriProductsTransType`，支援：

- `Start_time`、`End_time`
- `CropCode`、`CropName`
- `MarketName`
- `TcType`
- `Page`（回應 `Next=true` 時翻頁）

小型實測可在無 API key 的情況下成功取得 JSON，外層格式為：

```json
{
  "RS": "OK",
  "Data": [
    {
      "TransDate": "114.09.26",
      "TcType": "N04",
      "CropCode": "LA2",
      "CropName": "甘藍-改良種",
      "MarketCode": "109",
      "MarketName": "台北一",
      "Upper_Price": 26.2,
      "Middle_Price": 21.3,
      "Lower_Price": 11.5,
      "Avg_Price": 20.3,
      "Trans_Quantity": 140970.0
    }
  ],
  "Next": false
}
```

上例僅用來記錄 schema，不作為目前價格展示。

### 已觀察到的查詢陷阱

#### 無 API key 的分頁限制

單日未分區查詢會在 1,000 筆時回傳 `Next=true`；但未登入／未帶會員授權的 `Page=2` 實測回傳 `RS=ERROR`（非會員只限第一頁）。因此 Phase 1 不能依賴一般 `Page` 迴圈取得完整資料。

目前 adapter 先由 `CropMarketType` 取得蔬菜／水果市場查詢名稱，再以「日期 window × 市場名稱」分區。若 window 回傳 `Next=true`，會遞迴二分日期直到完整；若單日仍為 `Next=true` 才 fail closed。2026-09-24 實測 20 個去重後市場 query 共取得 2,363 筆，所有分區皆 `Next=false`。

Phase 2 另加入 `CropCode` 精確分區的 mapped-product backfill。它只抓受版本控制 mapping 中的 MVP codes，並在 ingestion metadata 標示 `mapped_mvp_products_only`，不可解讀為同期間全品項 coverage。2025-09-25～2026-09-24 實際取得 69,169 records，run 成功完成。

#### 市場參照與交易資料不一致

`CropMarketType` 的水果市場參照將「台北市」列為 `MarketCode=100`；同名條件查詢交易 API 時，資料實際回傳「台北市場」與 `MarketCode=105`。這表示參照 endpoint 的 code 不能拿來當交易 endpoint 的相等驗證。

Phase 1 的處理方式是：

- `MarketName` 只作官方 query partition alias。
- 每個非空分區必須只回傳單一、非空 `MarketCode`；若混入多個代碼即 fail。
- fact/dimension 一律保存交易 payload 的官方 `MarketCode` 與 `MarketName`，不覆寫成參照值。
- 參照 code/name 差異列為官方 source quality issue，後續可建立版本化 market alias 表，但不在 Phase 1 猜測合併。

#### 商品名稱不是 canonical filter

以 `CropName=甘藍` 查詢時，結果可能同時包含：

- `甘藍-初秋`
- `甘藍-改良種`
- `甘藍-進口 ...`
- `甘藍-甘藍芽`
- `球莖甘藍`

因此 `CropName` 比較接近文字搜尋，不應直接視為 canonical product filter。正式 ETL 會同步 source code，再由受版本控制的 product mapping 決定哪些 source products 屬於「高麗菜／甘藍」主商品；進口、特殊品種與球莖甘藍預設分開。

## 建議抓取策略

### 初始 backfill

- MVP 先抓最近 24 個月，足以計算 365 日 percentile 並跨越季節。
- 以日期 window × 官方市場名稱分區；`Next=true` 時自動二分，單日仍截斷才中止，避免無授權 Page 限制造成靜默遺漏。
- 原始 response 先驗證，再 normalize；每個 ingestion run 記錄 request parameters、筆數、hash、開始／結束時間與錯誤。
- 以 `(source_id, trade_date, market_id, product_id)` 作 idempotent upsert key。

### 每日同步

- 每日排程抓取最近 7 個日曆日，而不是只抓昨天，以吸收遲到與修正資料。
- source row hash 相同則不重寫；變更時更新 observation 並保留 run provenance。
- 未取得資料時先標記 freshness warning，不把空集合寫成零價格。
- 休市 row 保留於 raw/quarantine audit，但不進入價格 observation。

### 資料驗證

- 民國日期可解析並落在 request window。
- price 與 volume 為非負有限數；非休市資料的 `average_price > 0`、`volume_kg > 0` 才進分析層。
- `lower_price <= upper_price`；middle/average 超出合理區間時 quarantine，而不是靜默刪除。
- 維度 code/name 變更需記錄與告警。
- duplicate key、缺欄、未知 category 與極端值產生 data-quality metrics。

## 分析語意

### 全市場代表價

同一商品同一天的全市場價格使用交易量加權：

```text
weighted_average_price = sum(average_price * volume_kg) / sum(volume_kg)
```

不能直接平均各市場均價，否則小量市場與大量市場權重相同。商品 family 跨品種聚合時也使用同樣方法，且必須揭露包含的 source product codes。

### 「今天」

顯示每個商品的 `latest_available_trade_date`。休市、延遲或缺資料時，不把前一個交易日數據標成今日數據。

### 元／台斤

來源單位為元／公斤。若 UI 提供消費者熟悉的換算，可另外顯示 `TWD/600g = TWD/kg × 0.6`，並清楚標示它只是批發價單位換算，不是零售報價。

## RAG 的官方來源候選

RAG 不查價，只提供價格變化的可能背景。Phase 5 才納入，候選白名單：

- [農業部全球資訊網](https://www.moa.gov.tw/)：新聞、公告、農業產銷概況
- [農業部統計處](https://agrstat.moa.gov.tw/)：農業統計與產銷報告
- [農糧署](https://www.afa.gov.tw/)：產量、災損、供應調節相關官方資訊
- 未來若確有需求，再加入中央氣象署的官方天候資料；不能只因同時發生就宣稱是價格因果。

每份文件至少保存 `title`、`publisher`、`published_at`、`source_url`、`retrieved_at`、`content_hash` 與適用商品／日期 metadata。答案只有在文件時間與商品範圍相符時才可引用，並使用「可能因素」措辭。

## 主要資料風險與處理

| 風險 | 影響 | MVP 對策 |
|---|---|---|
| 批發價被誤認成零售價 | 產品誤導 | 所有畫面固定顯示批發、元/kg、日期與市場範圍 |
| 商品名稱與品種混雜 | 聚合失真 | code-based product dimension + 人工審核 mapping |
| 休市／缺值被當零價 | 排行與平均嚴重失真 | raw 保留、analytics 排除、freshness 狀態分開 |
| 市場覆蓋不完整 | 「全台」代表性被誇大 | 稱「回報市場加權價」，列出市場數與 scope |
| API 分頁或筆數限制 | 歷史資料不完整 | 日期 window × 市場／CropCode adaptive split；單日 `Next=true` fail closed |
| 市場參照 code/name 與交易資料不同 | 錯誤拒收或錯誤合併市場 | query alias 與交易維度分離；保留交易 payload；單分區只允許一個回傳 code |
| 歷史修正與遲到資料 | 日更不同步 | 7 日 rolling re-fetch + idempotent upsert |
| 極端值可能是真實也可能是錯誤 | percentile/z-score 污染 | quarantine + robust statistics + 人工 QA 頁 |
| 季節性 | 高點被誤判異常 | 365 日 percentile 加 rolling baseline；Phase 6 評估同季基準 |
| 來源網站結構改版 | ETL/RAG 中斷 | contract tests、source adapters、freshness alert |
| 官方文件只有相關性 | LLM 過度推論因果 | 價格事實與原因證據分欄，無文件就明說不知道 |

## Phase 1 spike 結果

已完成：

1. 驗證未授權第一頁 1,000 筆上限與 `Page=2` 限制，改採 fail-closed 市場分區。
2. 以 PostgreSQL 實際載入 2026-09-24：2,363 raw、2,352 valid facts、11 quarantine。
3. 同一日期重跑後 0 insert、0 update、2,352 unchanged，duplicate natural-key group 為 0。
4. 匯出並人工建立甘藍 code/name mapping；進口、甘藍心、甘藍芽、紫色與球莖甘藍均明確分流。
5. 保存資料集 URL、API URL、publisher 與政府資料開放授權條款 metadata。

Phase 2 已完成 365 日 mapped-product backfill，足以驗證 365 日 metrics；仍未完成 24 個月全品項 backfill、完整日期 × 市場 × 商品 completeness matrix、官方 rate-limit 數字確認，以及歷史修訂頻率量測。mapped backfill 是 portfolio MVP 的 analytics coverage，不可包裝成來源全集 coverage。
