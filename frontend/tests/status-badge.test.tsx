import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "@/components/status-badge";

describe("StatusBadge", () => {
  it.each([
    ["low", "偏低"],
    ["normal", "正常"],
    ["high", "偏高"],
    ["anomalously_high", "異常高"],
    ["insufficient_data", "資料不足"],
  ] as const)("renders %s as %s", (classification, label) => {
    render(<StatusBadge classification={classification} />);
    expect(screen.getByText(label)).toHaveClass(`status-${classification}`);
  });
});
