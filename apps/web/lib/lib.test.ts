import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { bandPath, candleShape, linePath, makeScales, niceTicks, priceDomain } from "./chart.ts";
import { formatDate, formatInt, formatNumber, formatPct, formatPrice, signed, tone } from "./format.ts";
import { LOCALES, messages, t } from "./i18n.ts";
import { loadFromText, parseSnapshot, SnapshotError } from "./snapshot.ts";
import { activeSignals, DEFAULT_PREFS, lastValue, OVERLAY_KEYS, parsePrefs, summarize } from "./summary.ts";
import type { Candle, Snapshot } from "./types.ts";

const RAW = readFileSync(new URL("../data/demo-snapshot.json", import.meta.url), "utf8");
const fresh = (): Snapshot => JSON.parse(RAW) as Snapshot;
const nbsp = (s: string) => s.replace(/[\u00a0\u202f]/g, " ");

test("the committed snapshot is strict JSON, parses, and is labelled simulated", () => {
  assert.ok(!/NaN|Infinity/.test(RAW));
  const r = loadFromText(RAW);
  assert.ok(r.ok, r.ok ? "" : r.error);
  if (r.ok) {
    assert.equal(r.data.meta.mode, "simulated");
    assert.equal(r.data.meta.symbols_are_fictional, true);
    assert.deepEqual(r.data.symbols.map((s) => s.symbol), ["SIMA", "SIMB", "SIMC", "SIMD", "SIME"]);
    for (const s of r.data.symbols) for (const b of s.backtests) assert.equal(b.simulated, true);
  }
});

test("snapshot validator rejects every kind of corruption instead of rendering it", () => {
  const cases: Record<string, (d: Snapshot) => void> = {
    "schema version": (d) => ((d as { schema_version: number }).schema_version = 2),
    "unknown mode": (d) => ((d.meta as { mode: string }).mode = "turbo"),
    "bad generated_at": (d) => (d.meta.generated_at = "yesterday"),
    "no symbols": (d) => (d.symbols = []),
    "duplicate symbol": (d) => (d.symbols[1].symbol = d.symbols[0].symbol),
    "high below low": (d) => (d.symbols[0].candles[5].h = d.symbols[0].candles[5].l - 1),
    "negative price": (d) => (d.symbols[0].candles[5].o = -1),
    "NaN-like price": (d) => (d.symbols[0].candles[5].c = Number.NaN),
    "string price": (d) => ((d.symbols[0].candles[5] as unknown as { c: string }).c = "10"),
    "non-increasing time": (d) => (d.symbols[0].candles[6].t = d.symbols[0].candles[5].t),
    "indicator length": (d) => d.symbols[0].indicators.rsi14.pop(),
    "indicator string": (d) => ((d.symbols[0].indicators.ema20 as unknown[])[40] = "x"),
    "backtest not simulated": (d) => ((d.symbols[0].backtests[0] as unknown as { simulated: boolean }).simulated = false),
    "equity length": (d) => d.symbols[0].backtests[0].equity.pop(),
    "decision kind": (d) => ((d.symbols[0].decisions[0] as unknown as { kind: string }).kind = "maybe"),
    "marker type": (d) => ((d.symbols[0].markers[0] as unknown as { type: string }).type = "buy_now"),
    "too few candles": (d) => (d.symbols[0].candles = d.symbols[0].candles.slice(0, 10)),
    "missing risk": (d) => delete (d.symbols[0] as Partial<Snapshot["symbols"][0]>).risk_example,
  };
  for (const [name, mutate] of Object.entries(cases)) {
    const d = fresh();
    mutate(d);
    assert.throws(() => parseSnapshot(JSON.parse(JSON.stringify(d, (_, v) => (Number.isNaN(v) ? "__NaN__" : v)))), SnapshotError, name);
  }
});

test("loadFromText returns an error object (never throws, never invents data) for garbage", () => {
  for (const bad of ["", "{", "null", "[]", "123", '{"schema_version":1}']) {
    const r = loadFromText(bad);
    assert.equal(r.ok, false, bad);
    if (!r.ok) assert.ok(r.error.length > 0);
  }
});

test("i18n: both locales define every key, no blanks, no leftover placeholders", () => {
  const keys = Object.keys(messages.es).sort();
  assert.deepEqual(Object.keys(messages.en).sort(), keys);
  for (const l of LOCALES) for (const k of keys) {
    const v = (messages[l] as Record<string, unknown>)[k];
    if (typeof v === "string") assert.ok(v.trim().length > 0, `${l}.${k}`);
    else assert.ok(Array.isArray(v) && v.length > 0, `${l}.${k}`);
  }
  assert.equal(t("en", "chartAria", { symbol: "SIMA", n: 252 }), "Candlestick chart of SIMA, 252 sessions");
  assert.ok(!t("es", "pMedian", { h: 10 }).includes("{"));
  assert.match(messages.es.bannerSimulated, /SIMULADOS/);
  assert.match(messages.en.bannerSimulated, /SIMULATED/);
});

test("format: locale-aware, null-safe, fractions for percentages", () => {
  assert.equal(nbsp(formatPrice(1234.5, "en")), "1,234.50");
  assert.equal(nbsp(formatPrice(1234.5, "es")), "1234,50");
  assert.equal(nbsp(formatPrice(12345.5, "es")), "12.345,50");
  assert.equal(nbsp(formatPct(0.125, "en")), "12.50%");
  assert.equal(nbsp(formatPct(0.125, "es")), "12,50 %");
  assert.equal(nbsp(formatPct(-0.0042, "en", 1)), "-0.4%");
  for (const f of [formatPrice, formatInt, formatNumber]) for (const bad of [null, undefined, Number.NaN, Infinity]) assert.equal(f(bad as number, "es"), "—");
  assert.equal(formatPct(null, "en"), "—");
  assert.equal(formatDate("2026-10-07T13:30:00Z", "en"), "Oct 07, 2026");
  assert.equal(formatDate("garbage", "en"), "—");
  assert.deepEqual([tone(1), tone(-1), tone(0), tone(null)], ["up", "down", "flat", "flat"]);
  assert.equal(signed("1.0%", 0.01), "+1.0%");
  assert.equal(signed("-1.0%", -0.01), "-1.0%");
});

const candle = (o: number, h: number, l: number, c: number, i = 0): Candle => ({ t: `2026-01-${String(i + 1).padStart(2, "0")}T13:30:00Z`, o, h, l, c, v: 1 });

test("chart geometry: domain, scales, paths, ticks", () => {
  const cs = [candle(10, 12, 9, 11, 0), candle(11, 15, 10, 14, 1), candle(14, 14.5, 8, 9, 2)];
  const [lo, hi] = priceDomain(cs, [[null, 20, null], [3, null, null]]);
  assert.ok(lo < 3 && hi > 20, "overlays widen the domain");
  const [lo2, hi2] = priceDomain(cs);
  assert.ok(lo2 < 8 && hi2 > 15 && lo2 > 7 && hi2 < 16);
  const box = { width: 300, height: 200, left: 40, right: 10, top: 10, bottom: 20 };
  const s = makeScales(3, box, [0, 20]);
  assert.equal(s.y(20), 10);
  assert.equal(s.y(0), 180);
  assert.ok(s.y(15) < s.y(5), "higher price = smaller y");
  assert.ok(s.x(0) > 40 && s.x(2) < 290 && s.x(0) < s.x(1) && s.x(1) < s.x(2));
  assert.equal(s.step, 250 / 3);
  const c = candleShape(candle(14, 14.5, 8, 9), 2, s);
  assert.equal(c.up, false);
  assert.equal(c.wickTop, s.y(14.5));
  assert.equal(c.bodyTop, Math.min(s.y(14), s.y(9)));
  assert.ok(candleShape(candle(10, 10, 10, 10), 0, s).bodyHeight >= 1, "doji stays visible");
  assert.throws(() => priceDomain([]));
  assert.throws(() => makeScales(0, box, [0, 1]));
  assert.throws(() => makeScales(3, box, [1, 1]));
  const x = (i: number) => i * 10;
  const y = (v: number) => 100 - v;
  assert.equal(linePath([1, 2, null, 4, 5], x, y), "M0.00 99.00L10.00 98.00M30.00 96.00L40.00 95.00");
  assert.equal(linePath([null, null], x, y), "");
  assert.equal(bandPath([2, 3, null, 5], [1, 1, null, 2], x, y), "M0.00 98.00L10.00 97.00L10.00 99.00L0.00 99.00ZM30.00 95.00L30.00 98.00Z");
  assert.equal(bandPath([1, null], [null, 1], x, y), "");
  const ticks = niceTicks(3, 97, 5);
  assert.ok(ticks.every((v) => v >= 3 && v <= 97) && ticks.length >= 2);
  assert.ok(ticks.slice(1).every((v, i) => Math.abs(v - ticks[i] - (ticks[1] - ticks[0])) < 1e-9));
  assert.deepEqual(niceTicks(0, 100, 5), [0, 25, 50, 75, 100]);
  assert.deepEqual(niceTicks(3, 97, 5), [25, 50, 75]);
  assert.ok(niceTicks(99.2, 100.1, 5).length >= 2);          // tiny range still gets a usable axis
  for (const [lo, hi] of [[0.001, 0.009], [1e5, 1.2e5], [-50, 50], [87.3, 142.9]]) {
    const tk = niceTicks(lo, hi, 5);
    assert.ok(tk.length >= 2 && tk.every((v) => v >= lo - 1e-9 && v <= hi + 1e-9), `${lo}..${hi}: ${tk}`);
  }
  assert.deepEqual(niceTicks(5, 5), [5]);
});

test("summaries on real snapshot data", () => {
  const d = fresh();
  for (const sym of d.symbols) {
    const r = summarize(sym);
    const n = sym.candles.length;
    assert.equal(r.close, sym.candles[n - 1].c);
    assert.ok(Math.abs((r.changePct as number) - (sym.candles[n - 1].c / sym.candles[n - 2].c - 1)) < 1e-12);
    assert.ok(r.rsi !== null && r.rsi >= 0 && r.rsi <= 100);
    assert.equal(r.strategies, sym.decisions.length);
    assert.equal(new Set(sym.decisions.map((x) => x.strategy)).size, sym.decisions.length);
    for (const b of sym.backtests) assert.equal(b.metrics.n_trades, b.trades.length);
  }
  assert.deepEqual(activeSignals(d.symbols), []);          // today the engines produce no signal: the UI must handle that honestly
  assert.equal(lastValue([1, null, 3, null]), 3);
  assert.equal(lastValue([null, null]), null);
});

test("persisted preferences: untrusted storage never crashes and never enables unknown keys", () => {
  assert.deepEqual(parsePrefs(null), DEFAULT_PREFS);
  for (const bad of ["", "{", "null", "[]", "42", '"x"', "undefined"]) assert.deepEqual(parsePrefs(bad), DEFAULT_PREFS, bad);
  const p = parsePrefs(JSON.stringify({ ema20: false, macd: true, volume: "yes", hacked: true, rsi: 1 }));
  assert.equal(p.ema20, false);
  assert.equal(p.macd, true);
  assert.equal(p.volume, DEFAULT_PREFS.volume);     // wrong type -> default
  assert.equal(p.rsi, DEFAULT_PREFS.rsi);
  assert.deepEqual(Object.keys(p).sort(), [...OVERLAY_KEYS].sort());
});

import { localiseNote, visibleNotes } from "./notes.ts";

test("engine notes: known ones are localised, redundant ones hidden, unknown ones never dropped", () => {
  const es = localiseNote("es", "signal on the last bar ignored: no next bar to execute on");
  assert.match(es.text, /última barra/);
  assert.equal(localiseNote("en", "3 entry signal(s) skipped: not enough cash for one share after costs").text.startsWith("3 entry signal"), true);
  assert.match(localiseNote("es", "2 entry signal(s) skipped: not enough cash for one share after costs").text, /^2 señal/);
  assert.equal(localiseNote("es", "Similarity scores are uncalibrated distances, not probabilities.").redundant, true);
  assert.equal(localiseNote("es", "n=8 < 30: no confidence interval is reported (sample too small to justify one)").redundant, true);
  const weird = "some brand new engine warning";
  assert.deepEqual(localiseNote("es", weird), { text: weird, redundant: false, known: false });
  const d = fresh();
  for (const sym of d.symbols) {
    for (const loc of LOCALES) {
      const raw = [...sym.patterns.summary.notes, ...sym.backtests.flatMap((b) => b.warnings)];
      const shown = [...visibleNotes(loc, sym.patterns.summary.notes), ...sym.backtests.flatMap((b) => visibleNotes(loc, b.warnings))];
      assert.ok(shown.length <= raw.length && shown.every((x) => x.length > 0));
      if (loc === "es") for (const x of shown) assert.ok(!/signal on the last bar|calendar period are correlated|anecdotal/.test(x), `untranslated engine text in es: ${x}`);
    }
  }
});
