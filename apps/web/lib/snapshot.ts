// Runtime validation of the data snapshot. The UI must never render data that fails these checks: it shows an error instead
// (no invented prices, no silent fallbacks).
import type { Backtest, Decision, Snapshot, SymbolData } from "./types.ts";

export class SnapshotError extends Error {
  path: string;
  constructor(path: string, message: string) {
    super(`${path}: ${message}`);
    this.name = "SnapshotError";
    this.path = path;
  }
}

type Rec = Record<string, unknown>;
const isRec = (x: unknown): x is Rec => typeof x === "object" && x !== null && !Array.isArray(x);
const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
const SERIES_KEYS = ["ema20", "ema50", "sma200", "bb_upper", "bb_lower", "rsi14", "macd", "macd_signal", "macd_hist", "atr14"] as const;

function rec(x: unknown, path: string): Rec {
  if (!isRec(x)) throw new SnapshotError(path, "expected an object");
  return x;
}
function arr(x: unknown, path: string): unknown[] {
  if (!Array.isArray(x)) throw new SnapshotError(path, "expected an array");
  return x;
}
function str(x: unknown, path: string): string {
  if (typeof x !== "string" || x.length === 0) throw new SnapshotError(path, "expected a non-empty string");
  return x;
}
function iso(x: unknown, path: string): string {
  const s = str(x, path);
  if (!ISO.test(s) || Number.isNaN(Date.parse(s))) throw new SnapshotError(path, `expected an ISO-8601 UTC timestamp, got ${s}`);
  return s;
}
function num(x: unknown, path: string): number {
  if (typeof x !== "number" || !Number.isFinite(x)) throw new SnapshotError(path, "expected a finite number");
  return x;
}

function symbol(raw: unknown, path: string): SymbolData {
  const s = rec(raw, path);
  str(s.symbol, `${path}.symbol`);
  str(s.name, `${path}.name`);
  const candles = arr(s.candles, `${path}.candles`);
  if (candles.length < 30) throw new SnapshotError(`${path}.candles`, "need at least 30 candles");
  let prev = "";
  candles.forEach((cr, i) => {
    const p = `${path}.candles[${i}]`;
    const c = rec(cr, p);
    const t = iso(c.t, `${p}.t`);
    if (t <= prev) throw new SnapshotError(`${p}.t`, "timestamps must be strictly increasing");
    prev = t;
    const [o, h, l, cl, v] = [num(c.o, `${p}.o`), num(c.h, `${p}.h`), num(c.l, `${p}.l`), num(c.c, `${p}.c`), num(c.v, `${p}.v`)];
    if (Math.min(o, h, l, cl) <= 0 || v < 0) throw new SnapshotError(p, "prices must be positive and volume >= 0");
    if (h < Math.max(o, cl, l) || l > Math.min(o, cl, h)) throw new SnapshotError(p, "inconsistent OHLC (high/low violated)");
  });
  const ind = rec(s.indicators, `${path}.indicators`);
  for (const k of SERIES_KEYS) {
    const a = arr(ind[k], `${path}.indicators.${k}`);
    if (a.length !== candles.length) throw new SnapshotError(`${path}.indicators.${k}`, `length ${a.length} != candles ${candles.length}`);
    a.forEach((v, i) => {
      if (v !== null) num(v, `${path}.indicators.${k}[${i}]`);
    });
  }
  arr(s.decisions, `${path}.decisions`).forEach((dr, i) => {
    const p = `${path}.decisions[${i}]`;
    const d = rec(dr, p);
    str(d.strategy, `${p}.strategy`);
    str(d.version, `${p}.version`);
    iso(d.as_of, `${p}.as_of`);
    if (d.kind === "no_signal") str(d.reason, `${p}.reason`);
    else if (d.kind === "signal") {
      str(d.status, `${p}.status`);
      arr(d.supporting, `${p}.supporting`);
      arr(d.contradicting, `${p}.contradicting`);
    } else throw new SnapshotError(`${p}.kind`, "expected 'signal' or 'no_signal'");
  });
  arr(s.markers, `${path}.markers`).forEach((mr, i) => {
    const m = rec(mr, `${path}.markers[${i}]`);
    iso(m.t, `${path}.markers[${i}].t`);
    if (m.type !== "entry_flag") throw new SnapshotError(`${path}.markers[${i}].type`, "unsupported marker type");
  });
  arr(s.backtests, `${path}.backtests`).forEach((br, i) => {
    const p = `${path}.backtests[${i}]`;
    const b = rec(br, p);
    if (b.simulated !== true) throw new SnapshotError(`${p}.simulated`, "every backtest must be labelled simulated");
    rec(b.metrics, `${p}.metrics`);
    const eq = arr(b.equity, `${p}.equity`);
    if (eq.length !== candles.length) throw new SnapshotError(`${p}.equity`, "equity length must equal the number of candles");
    eq.forEach((v, j) => num(v, `${p}.equity[${j}]`));
    arr(b.trades, `${p}.trades`).forEach((tr, j) => {
      const t = rec(tr, `${p}.trades[${j}]`);
      iso(t.entry, `${p}.trades[${j}].entry`);
      iso(t.exit, `${p}.trades[${j}].exit`);
      num(t.pnl, `${p}.trades[${j}].pnl`);
    });
  });
  const pat = rec(s.patterns, `${path}.patterns`);
  arr(pat.matches, `${path}.patterns.matches`);
  const sum = rec(pat.summary, `${path}.patterns.summary`);
  num(sum.n, `${path}.patterns.summary.n`);
  arr(sum.notes, `${path}.patterns.summary.notes`);
  const r = rec(s.risk_example, `${path}.risk_example`);
  for (const k of ["entry", "stop", "shares", "risk_amount", "notional"]) num(r[k], `${path}.risk_example.${k}`);
  return raw as SymbolData;
}

export function parseSnapshot(raw: unknown): Snapshot {
  const root = rec(raw, "$");
  if (root.schema_version !== 1) throw new SnapshotError("$.schema_version", `unsupported schema version ${String(root.schema_version)}`);
  const meta = rec(root.meta, "$.meta");
  if (meta.mode !== "simulated" && meta.mode !== "delayed" && meta.mode !== "live") throw new SnapshotError("$.meta.mode", "unknown data mode");
  if ((meta.mode === "simulated") !== (meta.symbols_are_fictional === true)) {
    throw new SnapshotError("$.meta", "mode and symbols_are_fictional disagree: simulated data must use fictional symbols and real data must not claim to be fictional");
  }
  if (meta.excluded !== undefined) {
    arr(meta.excluded, "$.meta.excluded").forEach((e, i) => {
      const r = rec(e, `$.meta.excluded[${i}]`);
      str(r.symbol, `$.meta.excluded[${i}].symbol`);
      str(r.reason, `$.meta.excluded[${i}].reason`);
    });
  }
  iso(meta.generated_at, "$.meta.generated_at");
  iso(meta.as_of, "$.meta.as_of");
  str(meta.data_source, "$.meta.data_source");
  const symbols = arr(root.symbols, "$.symbols");
  if (symbols.length === 0) throw new SnapshotError("$.symbols", "no symbols");
  const seen = new Set<string>();
  symbols.forEach((s, i) => {
    const sd = symbol(s, `$.symbols[${i}]`);
    if (seen.has(sd.symbol)) throw new SnapshotError(`$.symbols[${i}].symbol`, `duplicate symbol ${sd.symbol}`);
    seen.add(sd.symbol);
  });
  return raw as Snapshot;
}

export type Loaded = { ok: true; data: Snapshot } | { ok: false; error: string };

export function loadFromText(text: string): Loaded {
  try {
    return { ok: true, data: parseSnapshot(JSON.parse(text) as unknown) };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export type { Backtest, Decision };
