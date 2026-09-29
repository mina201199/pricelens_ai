import type {
  DataStatus,
  MoversResponse,
  PriceSummary,
  ProductHistory,
  ProductListItem,
} from "@/lib/types";

const API_URL = process.env.PRICE_LENS_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function fetchJson<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new ApiError("目前無法連線到價格資料服務，請稍後再試。");
  }
  if (!response.ok) {
    if (response.status === 404) {
      throw new ApiError("找不到指定商品或價格資料。", 404);
    }
    throw new ApiError("價格資料服務暫時無法回應。", response.status);
  }
  return (await response.json()) as T;
}

export const getProducts = () => fetchJson<ProductListItem[]>("/api/v1/products");
export const getDataStatus = () => fetchJson<DataStatus>("/api/v1/data-status");
export const getRadar = () => fetchJson<PriceSummary[]>("/api/v1/radar");
export const getMovers = (direction: "up" | "down", period = "7d") =>
  fetchJson<MoversResponse>(
    `/api/v1/movers?direction=${direction}&period=${period}`,
  );
export const getProductSummary = (slug: string) =>
  fetchJson<PriceSummary>(`/api/v1/products/${encodeURIComponent(slug)}/summary`);
export const getProductHistory = (
  slug: string,
  range: string,
  market = "all",
) =>
  fetchJson<ProductHistory>(
    `/api/v1/products/${encodeURIComponent(slug)}/history?range=${range}&market=${encodeURIComponent(market)}`,
  );
