import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import Link from "next/link";

import { FreshnessChip } from "@/components/freshness-chip";
import { StatusBadge } from "@/components/status-badge";
import { formatPercent, formatPrice } from "@/lib/format";
import type { PriceSummary } from "@/lib/types";

export function RadarCard({ item, latest }: { item: PriceSummary; latest: string }) {
  const change = item.metrics.wow_change_pct;
  const numericChange = change === null ? null : Number(change);
  const ChangeIcon =
    numericChange === null || numericChange === 0
      ? ArrowRight
      : numericChange > 0
        ? ArrowUpRight
        : ArrowDownRight;

  return (
    <Link className="radar-card" href={`/products/${item.product.slug}`}>
      <div className="radar-card-top">
        <div>
          <p className="eyebrow">{item.product.category === "fruit" ? "水果" : "蔬菜"}</p>
          <h3>{item.product.display_name}</h3>
        </div>
        <StatusBadge classification={item.classification.label} />
      </div>
      <div className="price-line">
        <strong>{formatPrice(item.metrics.current_price)}</strong>
        <span>元／公斤</span>
      </div>
      <div className="card-meta-row">
        <span className={numericChange !== null && numericChange > 0 ? "change-up" : "change-down"}>
          <ChangeIcon size={16} aria-hidden="true" />
          近 7 日 {formatPercent(change)}
        </span>
        <span>{item.scope.market_count} 個市場</span>
      </div>
      <div className="radar-card-footer">
        <FreshnessChip asOf={item.as_of} latest={latest} />
        <ArrowRight size={17} aria-hidden="true" />
      </div>
    </Link>
  );
}
