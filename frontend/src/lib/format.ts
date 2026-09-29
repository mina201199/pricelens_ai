import type { Classification } from "@/lib/types";

export const classificationLabels: Record<Classification, string> = {
  low: "偏低",
  normal: "正常",
  high: "偏高",
  anomalously_high: "異常高",
  insufficient_data: "資料不足",
};

export function formatPrice(value: string | number | null): string {
  if (value === null) return "—";
  return new Intl.NumberFormat("zh-TW", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(Number(value));
}

export function formatPercent(value: string | number | null): string {
  if (value === null) return "—";
  const numeric = Number(value);
  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(1)}%`;
}

export function formatRatioPercent(value: string | number | null): string {
  if (value === null) return "—";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

export function formatCompactNumber(value: string | number): string {
  return new Intl.NumberFormat("zh-TW", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(Number(value));
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-TW", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(`${value}T00:00:00+08:00`));
}

export function calendarDaysBetween(older: string, newer: string): number {
  const start = new Date(`${older}T00:00:00Z`).getTime();
  const end = new Date(`${newer}T00:00:00Z`).getTime();
  return Math.max(0, Math.round((end - start) / 86_400_000));
}
