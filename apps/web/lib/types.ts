// Mirrors scripts/export_demo_snapshot.py (schema_version 1). Keep in sync; lib/snapshot.ts validates at runtime.
export type Mode = "simulated" | "delayed" | "live";
export type Series = (number | null)[];

export interface Candle { t: string; o: number; h: number; l: number; c: number; v: number }
export interface Indicators {
  ema20: Series; ema50: Series; sma200: Series; bb_upper: Series; bb_lower: Series; rsi14: Series;
  macd: Series; macd_signal: Series; macd_hist: Series; atr14: Series;
}
export interface EvidenceItem { name: string; value: number | string; note: string }
export type Decision =
  | { kind: "signal"; strategy: string; version: string; as_of: string; status: string; supporting: EvidenceItem[]; contradicting: EvidenceItem[] }
  | { kind: "no_signal"; strategy: string; version: string; as_of: string; reason: string };
export interface Marker { t: string; strategy: string; type: "entry_flag" }
export interface Trade { entry: string; exit: string; entry_price: number; exit_price: number; shares: number; pnl: number; reason: string }
export type MetricValue = number | boolean | null;
export interface Backtest {
  strategy: string; version: string; simulated: true; config_hash: string;
  config: Record<string, number | string | null>; metrics: Record<string, MetricValue>;
  equity: number[]; warnings: string[]; trades: Trade[];
}
export interface PatternMatch {
  symbol: string; window_start: string; window_end: string; outcome_end: string; distance: number; similarity: number;
  forward_return: number; mfe: number; mae: number; regime: string | null;
}
export interface PatternSummary {
  n: number; notes: string[]; ci_median_95: [number, number] | null;
  median_forward_return?: number; mean_forward_return?: number; share_positive?: number;
  median_mfe?: number; median_mae?: number; worst_mae?: number; q10?: number; q90?: number;
}
export interface Patterns { window: number; horizon: number; as_of: string; matches: PatternMatch[]; summary: PatternSummary }
export interface RiskExample {
  equity: number; risk_fraction: number; entry: number; atr14: number; atr_multiple: number; stop: number;
  shares: number; risk_amount: number; notional: number; binding: string; reward_risk_at_3R: number;
}
export interface SymbolData {
  symbol: string; name: string; currency: string; exchange: string; candles: Candle[]; indicators: Indicators;
  decisions: Decision[]; markers: Marker[]; backtests: Backtest[]; patterns: Patterns; risk_example: RiskExample;
}
export interface Excluded { symbol: string; reason: string }
export type BannerMode = Mode | "unavailable";
export interface Meta {
  mode: Mode; data_source: string; generated_at: string; as_of: string; timeframe: string; bars_shown: number;
  symbols_are_fictional: boolean; note: string; feed?: string; adjustment?: string; excluded?: Excluded[];
}
export interface Snapshot { schema_version: 1; meta: Meta; symbols: SymbolData[] }
