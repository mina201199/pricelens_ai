import { ArrowDownRight, ArrowUpRight, CalendarDays, Landmark, ScanSearch } from "lucide-react";

import { AiSearch } from "@/components/ai-search";
import { MoversPanel } from "@/components/movers-panel";
import { RadarCard } from "@/components/radar-card";
import { ServiceError } from "@/components/states";
import { getMovers, getRadar } from "@/lib/api";
import { formatDate } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [radarResult, upResult, downResult] = await Promise.allSettled([
    getRadar(),
    getMovers("up"),
    getMovers("down"),
  ]);

  if (radarResult.status === "rejected") {
    return (
      <div className="shell page-state-wrap">
        <ServiceError detail={radarResult.reason instanceof Error ? radarResult.reason.message : undefined} />
      </div>
    );
  }

  const radar = radarResult.value;
  const latest = radar.reduce((date, item) => (item.as_of > date ? item.as_of : date), "");
  const highCount = radar.filter((item) => ["high", "anomalously_high"].includes(item.classification.label)).length;
  const lowCount = radar.filter((item) => item.classification.label === "low").length;

  return (
    <>
      <section className="hero">
        <div className="shell hero-grid">
          <div className="hero-copy">
            <p className="eyebrow"><span /> AI 民生物價雷達</p>
            <h1>現在買，<br /><em>算貴嗎？</em></h1>
            <p className="hero-lead">
              用歷史行情與近期趨勢，理解台灣農產品的批發價格位置。不是只看一個數字，而是看它相對於過去處在哪裡。
            </p>
            <div className="hero-actions">
              <a className="button button-primary" href="#radar"><ScanSearch size={18} />查看今日雷達</a>
              <a className="text-link" href="#ai-search">試試自然語言搜尋 <span aria-hidden="true">→</span></a>
            </div>
          </div>
          <aside className="hero-snapshot" aria-label="最新資料摘要">
            <div className="snapshot-top">
              <span><Landmark size={18} />官方批發行情</span>
              <span className="live-dot">資料已驗證</span>
            </div>
            <p>資料最新日期</p>
            <strong>{latest ? formatDate(latest) : "尚無資料"}</strong>
            <div className="snapshot-stats">
              <div><span className="snapshot-icon high"><ArrowUpRight /></span><b>{highCount}</b><small>項偏高</small></div>
              <div><span className="snapshot-icon low"><ArrowDownRight /></span><b>{lowCount}</b><small>項偏低</small></div>
              <div><span className="snapshot-icon neutral"><CalendarDays /></span><b>{radar.length}</b><small>項追蹤中</small></div>
            </div>
            <p className="snapshot-note">以各商品所有回報市場的交易量加權批發均價計算。</p>
          </aside>
        </div>
      </section>

      <section className="section shell" id="radar" aria-labelledby="radar-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">MARKET PULSE</p>
            <h2 id="radar-title">今日價格雷達</h2>
            <p>比較近期均價與一年歷史分布，快速掌握批發價格位置。</p>
          </div>
          {latest && <span className="as-of-label">資料截至 {formatDate(latest)}</span>}
        </div>
        {radar.length ? (
          <div className="radar-grid">
            {radar.map((item) => <RadarCard key={item.product.slug} item={item} latest={latest} />)}
          </div>
        ) : (
          <ServiceError detail="目前沒有可顯示的商品分析資料。請先執行 ETL 與 analytics refresh。" />
        )}
      </section>

      <section className="section section-tint" id="movers" aria-labelledby="movers-title">
        <div className="shell">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">WEEKLY MOVERS</p>
              <h2 id="movers-title">本週價格動向</h2>
              <p>同一商品最新批發均價，與 7 日前可用交易日相比。</p>
            </div>
          </div>
          <div className="movers-grid">
            {upResult.status === "fulfilled" ? <MoversPanel data={upResult.value} /> : <ServiceError detail="漲價榜暫時無法載入。" />}
            {downResult.status === "fulfilled" ? <MoversPanel data={downResult.value} /> : <ServiceError detail="降價榜暫時無法載入。" />}
          </div>
        </div>
      </section>

      <section className="section shell">
        <AiSearch />
      </section>
    </>
  );
}
