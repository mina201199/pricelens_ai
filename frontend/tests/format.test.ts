import { describe, expect, it } from "vitest";

import { calendarDaysBetween, classificationLabels, formatPercent, formatPrice, formatRatioPercent } from "@/lib/format";

describe("display formatting", () => {
  it("formats wholesale prices and signed changes for zh-TW", () => {
    expect(formatPrice("35.1106")).toBe("35.1");
    expect(formatPercent("12.1587")).toBe("+12.2%");
    expect(formatPercent("-8")).toBe("-8.0%");
  });

  it("converts a stored volatility ratio to a percentage", () => {
    expect(formatRatioPercent("0.08356")).toBe("8.4%");
    expect(formatRatioPercent(null)).toBe("—");
  });

  it("keeps classification copy explicit and computes calendar lag", () => {
    expect(classificationLabels.anomalously_high).toBe("異常高");
    expect(calendarDaysBetween("2026-09-20", "2026-09-24")).toBe(4);
  });
});
