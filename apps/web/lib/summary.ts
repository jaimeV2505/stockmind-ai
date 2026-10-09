import type { Decision, Series, SymbolData } from "./types.ts";

export const lastValue = (s: Series): number | null => {
  for (let i = s.length - 1; i >= 0; i--) {
    const v = s[i];
    if (v !== null && Number.isFinite(v)) return v;
  }
  return null;
};

export interface Row { symbol: string; name: string; close: number; changePct: number | null; rsi: number | null; signals: number; strategies: number }

export function summarize(s: SymbolData): Row {
  const n = s.candles.length;
  const last = s.candles[n - 1].c;
  const prev = n > 1 ? s.candles[n - 2].c : null;
  return {
    symbol: s.symbol, name: s.name, close: last, changePct: prev ? last / prev - 1 : null, rsi: lastValue(s.indicators.rsi14),
    signals: s.decisions.filter((d) => d.kind === "signal").length, strategies: s.decisions.length,
  };
}

export const activeSignals = (symbols: SymbolData[]): { symbol: string; decision: Extract<Decision, { kind: "signal" }> }[] =>
  symbols.flatMap((s) => s.decisions.flatMap((d) => (d.kind === "signal" ? [{ symbol: s.symbol, decision: d }] : [])));

// ---- persisted UI preferences (localStorage content is untrusted: corrupt/old values fall back to defaults) ----
export const OVERLAY_KEYS = ["ema20", "ema50", "sma200", "bollinger", "volume", "rsi", "macd", "entries"] as const;
export type OverlayKey = (typeof OVERLAY_KEYS)[number];
export type Prefs = Record<OverlayKey, boolean>;
export const DEFAULT_PREFS: Prefs = { ema20: true, ema50: true, sma200: false, bollinger: false, volume: true, rsi: true, macd: false, entries: true };

export function parsePrefs(raw: string | null): Prefs {
  if (!raw) return { ...DEFAULT_PREFS };
  try {
    const o: unknown = JSON.parse(raw);
    if (typeof o !== "object" || o === null || Array.isArray(o)) return { ...DEFAULT_PREFS };
    const out = { ...DEFAULT_PREFS };
    for (const k of OVERLAY_KEYS) {
      const v = (o as Record<string, unknown>)[k];
      if (typeof v === "boolean") out[k] = v;
    }
    return out;
  } catch {
    return { ...DEFAULT_PREFS };
  }
}
export const PREFS_KEY = "stockmind.chart.prefs.v1";
