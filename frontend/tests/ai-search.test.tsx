import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AiSearch } from "@/components/ai-search";

const response = {
  answer: "截至 2026-09-24，高麗菜批發均價為 35.1106 元/公斤，分類為偏高。",
  route: "typed_analytics",
  as_of: "2026-09-24",
  unit: "TWD/kg wholesale",
  price_semantics: "wholesale market transaction price",
  product: null,
  scope: { key: "all_reporting_markets", type: "all_reporting_markets", market_code: null, market_count: 12 },
  metrics: null,
  classification: null,
  data: [],
  evidence: [{ publisher: "農業部農糧署", title: "農產品交易行情", source_url: "https://example.test", as_of: null }],
  possible_factors: [{
    statement: "高麗菜供應與產地採收受到天候影響。",
    evidence: {
      publisher: "農業部農糧署",
      title: "高麗菜產地供應說明",
      source_url: "https://www.afa.gov.tw/news/1",
      as_of: "2026-09-24",
      published_at: "2026-09-20",
      event_start: "2026-09-18",
      event_end: "2026-09-24",
      document_id: 7,
    },
  }],
  warnings: [],
  trace_id: "trace-1",
  method: { route: "typed_analytics", intent: "product_status", provider: "deterministic-tools", model: "none", version: "ask-contract-v1" },
};

describe("AiSearch Phase 5", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders a sourced answer with freshness and wholesale unit", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(response), { status: 200 }),
    );
    render(<AiSearch />);
    fireEvent.change(screen.getByLabelText("輸入價格問題"), { target: { value: "高麗菜現在算貴嗎？" } });
    fireEvent.click(screen.getByRole("button", { name: "送出問題" }));
    await waitFor(() => expect(screen.getByText(/35.1106/)).toBeInTheDocument());
    expect(screen.getByText(/資料 2026-09-24/)).toBeInTheDocument();
    expect(screen.getByText(/批發 · 元／公斤/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "農業部農糧署" })).toHaveAttribute("href", "https://example.test");
    expect(screen.getByText("高麗菜供應與產地採收受到天候影響。")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "農業部農糧署：高麗菜產地供應說明" }))
      .toHaveAttribute("href", "https://www.afa.gov.tw/news/1");
    expect(screen.getByText(/發布 2026-09-20/)).toBeInTheDocument();
  });

  it("validates an empty question", () => {
    render(<AiSearch />);
    fireEvent.click(screen.getByRole("button", { name: "送出問題" }));
    expect(screen.getByRole("alert")).toHaveTextContent("請先輸入");
  });

  it("shows an honest service error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 503 }));
    render(<AiSearch />);
    fireEvent.change(screen.getByLabelText("輸入價格問題"), { target: { value: "哪個商品最貴？" } });
    fireEvent.click(screen.getByRole("button", { name: "送出問題" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("暫時無法回應"));
  });
});
