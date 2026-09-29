import {
  Activity,
  ArrowDownRight,
  ArrowLeft,
  ArrowUpRight,
  BarChart3,
  CalendarRange,
  Database,
  Gauge,
  Landmark,
  Scale,
  Store,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { FreshnessChip } from "@/components/freshness-chip";
import { MetricCard } from "@/components/metric-card";
import { PriceChart } from "@/components/price-chart";
import { EmptyState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { ApiError, getDataStatus, getProductHistory, getProductSummary } from "@/lib/api";
import { classificationLabels, formatCompactNumber, formatDate, formatPercent, formatPrice, formatRatioPercent } from "@/lib/format";
import type { Classification } from "@/lib/types";

export const dynamic = "force-dynamic";

const ranges = [
  { value: "1m", label: "1 個月" },
  { value: "3m", label: "3 個月" },
  { value: "6m", label: "6 個月" },
  { value: "1y", label: "1 年" },
  { value: "2y", label: "2 年" },
] as const;

const allowedRanges = new Set(ranges.map((range) => range.value));

const interpretations: Record<Classification, string> = {
  low: "目前批發均價位於歷史相對低檔，對採購端而言是較便宜的價格區間。",
  normal: "目前批發均價落在常態區間，尚未出現明顯偏高或偏低訊號。",
  high: "目前批發均價處於歷史相對高檔，建議同時觀察近期走勢與到貨量。",
  anomalously_high: "目前批發均價顯著高於歷史常態，屬於需要留意的異常高價訊號。",
  insufficient_data: "可用歷史資料仍不足，目前不做高低價判斷。",
};

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  try {
    const { slug } = await params;
    const summary = await getProductSummary(slug);
    return { title: `${summary.product.display_name}批發價格分析` };
  } catch {
    return { title: "商品價格分析" };
  }
}

export default async function ProductPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ range?: string }>;
}) {
  const { slug } = await params;
  const requestedRange = (await searchParams).range ?? "3m";
  const range = allowedRanges.has(requestedRange as (typeof ranges)[number]["value"])
    ? requestedRange
    : "3m";

  let summary;
  try {
    summary = await getProductSummary(slug);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const [history, dataStatus] = await Promise.all([
    getProductHistory(slug, range),
    getDataStatus(),
  ]);
  const latestAnalyticsDate = dataStatus.analytics_latest_trade_date ?? summary.as_of;
  const change = summary.metrics.wow_change_pct;
  const numericChange = change === null ? null : Number(change);
  const sourceCodes = summary.included_source_product_codes;

  return (
    <>
      <section className="detail-hero">
        <div className="shell">
          <Link className="back-link" href="/"><ArrowLeft size={17} />返回價格雷達</Link>
          <div className="detail-heading">
            <div>
              <p className="eyebrow">{summary.product.category === "fruit" ? "水果" : "蔬菜"} · WHOLESALE PRICE</p>
              <h1>{summary.product.display_name}</h1>
              <p>官方批發市場交易行情的相對價格分析</p>
            </div>
            <div className="detail-freshness">
              <StatusBadge classification={summary.classification.label} />
              <FreshnessChip asOf={summary.as_of} latest={latestAnalyticsDate} />
            </div>
          </div>
        </div>
      </section>

      <div className="shell detail-layout">
        <section className="price-summary-card" aria-labelledby="current-price-title">
          <div className="current-price">
            <p id="current-price-title">最新批發加權均價</p>
            <div><strong>{formatPrice(summary.metrics.current_price)}</strong><span>元／公斤</span></div>
            <p className={numericChange !== null && numericChange > 0 ? "change-up" : "change-down"}>
              {numericChange !== null && numericChange > 0 ? <ArrowUpRight size={17} /> : <ArrowDownRight size={17} />}
              較 7 日前 {formatPercent(change)}
            </p>
          </div>
          <div className="price-interpretation">
            <span><Gauge size={19} aria-hidden="true" /></span>
            <div>
              <p>Price Lens 判讀</p>
              <h2>{classificationLabels[summary.classification.label]}</h2>
              <p>{interpretations[summary.classification.label]}</p>
            </div>
          </div>
          <div className="truth-note">
            <Landmark size={18} aria-hidden="true" />
            <p><strong>這不是零售售價。</strong> 資料反映 {summary.scope.market_count} 個回報市場的批發交易行情，實際店家價格仍包含運輸、耗損與通路成本。</p>
          </div>
        </section>

        <section className="chart-card" aria-labelledby="trend-title">
          <div className="chart-heading">
            <div>
              <p className="eyebrow">PRICE HISTORY</p>
              <h2 id="trend-title">價格與交易量走勢</h2>
            </div>
            <nav className="range-tabs" aria-label="選擇價格走勢期間">
              {ranges.map((item) => (
                <Link
                  aria-current={range === item.value ? "page" : undefined}
                  className={range === item.value ? "active" : ""}
                  href={`/products/${summary.product.slug}?range=${item.value}`}
                  key={item.value}
                  scroll={false}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
          {history.points.length ? <PriceChart points={history.points} /> : <EmptyState title="這段期間沒有資料" detail="請切換其他期間，或稍後等候新的交易資料。" />}
          <div className="chart-legend" aria-label="圖表圖例">
            <span><i className="legend-price" />批發均價</span>
            <span><i className="legend-average" />30 日均線</span>
            <span><i className="legend-volume" />交易量</span>
          </div>
        </section>

        <section className="metrics-section" aria-labelledby="metrics-title">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">EXPLAINABLE METRICS</p>
              <h2 id="metrics-title">判斷依據</h2>
            </div>
          </div>
          <div className="metrics-grid">
            <MetricCard icon={CalendarRange} label="7 日移動平均" value={`${formatPrice(summary.metrics.ma_7d)} 元`} note="平滑短期日間波動" />
            <MetricCard icon={CalendarRange} label="30 日移動平均" value={`${formatPrice(summary.metrics.ma_30d)} 元`} note="觀察月度價格中樞" />
            <MetricCard icon={Scale} label="一年歷史百分位" value={summary.metrics.percentile_365d === null ? "—" : `${Number(summary.metrics.percentile_365d).toFixed(0)}%`} note="越高代表接近一年高檔" />
            <MetricCard icon={Activity} label="近 30 日波動度" value={formatRatioPercent(summary.metrics.volatility_30d)} note="每日對數報酬的標準差" />
            <MetricCard icon={BarChart3} label="最新交易量" value={`${formatCompactNumber(summary.metrics.total_volume_kg)} kg`} note={`較前期 ${formatPercent(summary.metrics.volume_change_pct)}`} />
            <MetricCard icon={Store} label="涵蓋市場" value={`${summary.scope.market_count} 個`} note="當日有有效交易回報" />
          </div>
        </section>

        <section className="provenance-card" aria-labelledby="provenance-title">
          <div>
            <span className="feature-icon"><Database size={18} aria-hidden="true" /></span>
            <p className="eyebrow">DATA PROVENANCE</p>
            <h2 id="provenance-title">資料範圍與來源</h2>
          </div>
          <dl>
            <div><dt>資料日期</dt><dd>{formatDate(summary.as_of)}</dd></div>
            <div><dt>價格單位</dt><dd>新台幣／公斤（批發）</dd></div>
            <div><dt>市場範圍</dt><dd>所有回報市場；交易量加權，當日 {summary.scope.market_count} 個市場</dd></div>
            <div><dt>官方來源</dt><dd>{summary.source}</dd></div>
            <div><dt>納入原始代碼</dt><dd className="code-list">{sourceCodes.length ? sourceCodes.join("、") : "未提供"}</dd></div>
            <div><dt>計算版本</dt><dd>{summary.calculation_version} · {summary.classification.version}</dd></div>
          </dl>
          {summary.warnings.length > 0 && <p className="warning-line">注意：{summary.warnings.join("；")}</p>}
        </section>
      </div>
    </>
  );
}
