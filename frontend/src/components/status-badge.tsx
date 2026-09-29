import { CircleAlert, CircleCheck, CircleMinus, CircleX, Info } from "lucide-react";

import { classificationLabels } from "@/lib/format";
import type { Classification } from "@/lib/types";

const icons = {
  low: CircleCheck,
  normal: CircleMinus,
  high: CircleAlert,
  anomalously_high: CircleX,
  insufficient_data: Info,
};

export function StatusBadge({ classification }: { classification: Classification }) {
  const Icon = icons[classification];
  return (
    <span className={`status-badge status-${classification}`}>
      <Icon size={14} aria-hidden="true" />
      {classificationLabels[classification]}
    </span>
  );
}
