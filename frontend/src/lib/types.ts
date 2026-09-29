import type { components } from "@/lib/api-schema.generated";

export type Classification =
  | "low"
  | "normal"
  | "high"
  | "anomalously_high"
  | "insufficient_data";

export interface ProductIdentity {
  slug: string;
  canonical_name: string;
  display_name: string;
  category: string;
}

export interface ScopeInfo {
  key: string;
  type: "all_reporting_markets" | "market";
  market_code: string | null;
  market_count: number;
}

export interface MetricValues {
  current_price: string;
  ma_7d: string | null;
  ma_30d: string | null;
  ma_90d: string | null;
  wow_change_pct: string | null;
  mom_change_pct: string | null;
  percentile_365d: string | null;
  z_score_365d: string | null;
  robust_z_365d: string | null;
  historical_high_price: string | null;
  historical_high_date: string | null;
  historical_low_price: string | null;
  historical_low_date: string | null;
  total_volume_kg: string;
  volume_change_pct: string | null;
  volatility_30d: string | null;
  history_day_count: number;
}

export interface PriceSummary {
  as_of: string;
  product: ProductIdentity;
  scope: ScopeInfo;
  unit: "TWD/kg wholesale";
  price_semantics: "wholesale market transaction price";
  included_source_product_codes: string[];
  metrics: MetricValues;
  classification: { label: Classification; version: string };
  calculation_version: string;
  computed_at: string;
  source: string;
  warnings: string[];
}

export interface HistoryPoint {
  trade_date: string;
  weighted_avg_price: string;
  total_volume_kg: string;
  market_count: number;
  ma_7d: string | null;
  ma_30d: string | null;
  ma_90d: string | null;
  percentile_365d: string | null;
  classification: Classification;
}

export interface ProductHistory {
  product: ProductIdentity;
  scope: ScopeInfo;
  unit: "TWD/kg wholesale";
  range: string;
  points: HistoryPoint[];
}

export interface MoverItem {
  product: ProductIdentity;
  as_of: string;
  change_pct: string;
  current_price: string;
  classification: Classification;
  market_count: number;
}

export interface MoversResponse {
  direction: "up" | "down";
  period: "7d" | "30d";
  unit: "TWD/kg wholesale";
  items: MoverItem[];
}

export interface ProductListItem extends ProductIdentity {
  latest_available_trade_date: string | null;
  latest_classification: Classification | null;
}

export interface DataStatus {
  dataset: string;
  publisher: string;
  price_semantics: "wholesale market transaction price, not retail price";
  unit: "TWD/kg wholesale";
  observation_count: number;
  earliest_trade_date: string | null;
  latest_trade_date: string | null;
  product_count: number;
  market_count: number;
  latest_successful_ingestion_at: string | null;
  analytics_metric_count: number;
  analytics_latest_trade_date: string | null;
  analytics_last_computed_at: string | null;
  analytics_calculation_version: string;
  analytics_classification_version: string;
}

export type AnswerEvidence = components["schemas"]["AnswerEvidence"];
export type PossibleFactor = {
  statement: string;
  evidence: AnswerEvidence;
};
type GeneratedAskResponse = components["schemas"]["AskResponse"];

export type AskResponse = GeneratedAskResponse & {
  as_of: string | null;
  product: ProductIdentity | null;
  scope: ScopeInfo | null;
  metrics: MetricValues | null;
  classification: { label: Classification; version: string } | null;
  data: Record<string, unknown>[];
  warnings: string[];
  possible_factors: PossibleFactor[];
};
