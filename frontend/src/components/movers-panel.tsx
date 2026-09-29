import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import Link from "next/link";

import { formatPercent, formatPrice } from "@/lib/format";
import type { MoversResponse } from "@/lib/types";

export function MoversPanel({ data }: { data: MoversResponse }) {
  const up = data.direction === "up";
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <article className="movers-panel">
      <div className="panel-heading">
        <span className={`direction-icon ${up ? "is-up" : "is-down"}`}>
          <Icon size={18} aria-hidden="true" />
        </span>
        <div>
          <p className="eyebrow">近 7 日批發均價</p>
          <h3>{up ? "本週漲價榜" : "本週降價榜"}</h3>
        </div>
      </div>
      {data.items.length === 0 ? (
        <p className="empty-inline">目前沒有足夠的可比較資料。</p>
      ) : (
        <ol className="mover-list">
          {data.items.slice(0, 5).map((item, index) => (
            <li key={item.product.slug}>
              <span className="rank">{String(index + 1).padStart(2, "0")}</span>
              <Link href={`/products/${item.product.slug}`}>
                <strong>{item.product.display_name}</strong>
                <small>{formatPrice(item.current_price)} 元／公斤</small>
              </Link>
              <span className={up ? "change-up" : "change-down"}>
                {formatPercent(item.change_pct)}
              </span>
            </li>
          ))}
        </ol>
      )}
    </article>
  );
}
