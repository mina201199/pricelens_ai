"use client";

import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatCompactNumber, formatPrice } from "@/lib/format";
import type { HistoryPoint } from "@/lib/types";

interface ChartPoint {
  date: string;
  shortDate: string;
  price: number;
  ma30: number | null;
  volume: number;
}

function ChartTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: Array<{ dataKey: string; value: number; color: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      {payload.map((entry) => (
        <span key={entry.dataKey}>
          <i style={{ background: entry.color }} />
          {entry.dataKey === "volume" ? "交易量" : entry.dataKey === "ma30" ? "30 日均線" : "批發均價"}
          <b>{entry.dataKey === "volume" ? `${formatCompactNumber(entry.value)} kg` : `${formatPrice(entry.value)} 元`}</b>
        </span>
      ))}
    </div>
  );
}

export function PriceChart({ points }: { points: HistoryPoint[] }) {
  const data: ChartPoint[] = points.map((point) => ({
    date: point.trade_date,
    shortDate: point.trade_date.slice(5).replace("-", "/"),
    price: Number(point.weighted_avg_price),
    ma30: point.ma_30d === null ? null : Number(point.ma_30d),
    volume: Number(point.total_volume_kg),
  }));

  return (
    <div className="chart-frame" aria-label="批發均價與交易量走勢圖">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 12, right: 8, left: -12, bottom: 4 }} accessibilityLayer>
          <defs>
            <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#1f6a4a" stopOpacity={0.22} />
              <stop offset="100%" stopColor="#1f6a4a" stopOpacity={0.01} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#e6e5dc" vertical={false} />
          <XAxis dataKey="shortDate" tickLine={false} axisLine={false} minTickGap={34} tick={{ fill: "#74766f", fontSize: 12 }} />
          <YAxis yAxisId="price" tickLine={false} axisLine={false} tick={{ fill: "#74766f", fontSize: 12 }} width={52} />
          <YAxis yAxisId="volume" orientation="right" hide />
          <Tooltip content={<ChartTooltip />} />
          <Bar yAxisId="volume" dataKey="volume" fill="#dfe9df" radius={[3, 3, 0, 0]} maxBarSize={8} />
          <Area yAxisId="price" type="monotone" dataKey="price" stroke="#1f6a4a" strokeWidth={2.4} fill="url(#priceFill)" activeDot={{ r: 4, fill: "#1f6a4a" }} />
          <Line yAxisId="price" type="monotone" dataKey="ma30" stroke="#e78a43" strokeWidth={1.6} strokeDasharray="5 5" dot={false} connectNulls />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
