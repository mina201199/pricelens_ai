import { Clock3 } from "lucide-react";

import { calendarDaysBetween, formatDate } from "@/lib/format";

export function FreshnessChip({ asOf, latest }: { asOf: string; latest: string }) {
  const lag = calendarDaysBetween(asOf, latest);
  return (
    <span className={`freshness ${lag > 7 ? "is-stale" : ""}`}>
      <Clock3 size={13} aria-hidden="true" />
      {lag > 7 ? `資料較舊 · ${formatDate(asOf)}` : `更新至 ${formatDate(asOf)}`}
    </span>
  );
}
