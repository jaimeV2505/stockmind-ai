// Pure chart geometry (no React): tested in isolation, rendered as SVG by components/CandleChart.tsx.
import type { Candle, Series } from "./types.ts";

export interface Box { width: number; height: number; left: number; right: number; top: number; bottom: number }
export interface Scales { x: (i: number) => number; y: (v: number) => number; min: number; max: number; step: number }

/** [min, max] covering all candle highs/lows and the given overlay series (nulls ignored), padded by `pad` (fraction of range). */
export function priceDomain(candles: Candle[], overlays: Series[] = [], pad = 0.04): [number, number] {
  if (candles.length === 0) throw new Error("no candles");
  let lo = Infinity;
  let hi = -Infinity;
  for (const c of candles) {
    lo = Math.min(lo, c.l);
    hi = Math.max(hi, c.h);
  }
  for (const s of overlays) for (const v of s) if (v !== null && Number.isFinite(v)) {
    lo = Math.min(lo, v);
    hi = Math.max(hi, v);
  }
  const range = hi - lo || Math.abs(hi) * 0.01 || 1;
  return [lo - range * pad, hi + range * pad];
}

export function makeScales(n: number, box: Box, domain: [number, number]): Scales {
  if (n < 1) throw new Error("need at least one point");
  const [min, max] = domain;
  if (!(max > min)) throw new Error("invalid domain");
  const plotW = box.width - box.left - box.right;
  const plotH = box.height - box.top - box.bottom;
  const step = plotW / n;
  return { x: (i) => box.left + step * (i + 0.5), y: (v) => box.top + plotH * (1 - (v - min) / (max - min)), min, max, step };
}

/** SVG path for a series; nulls break the line (no interpolation across gaps). */
export function linePath(s: Series, x: (i: number) => number, y: (v: number) => number): string {
  let d = "";
  let pen = false;
  s.forEach((v, i) => {
    if (v === null || !Number.isFinite(v)) {
      pen = false;
      return;
    }
    d += `${pen ? "L" : "M"}${x(i).toFixed(2)} ${y(v).toFixed(2)}`;
    pen = true;
  });
  return d;
}

/** Filled band between two series (e.g. Bollinger): only where both exist, one polygon per contiguous run. */
export function bandPath(upper: Series, lower: Series, x: (i: number) => number, y: (v: number) => number): string {
  let d = "";
  let i = 0;
  while (i < upper.length) {
    if (upper[i] === null || lower[i] === null) {
      i++;
      continue;
    }
    let j = i;
    while (j < upper.length && upper[j] !== null && lower[j] !== null) j++;
    const up = Array.from({ length: j - i }, (_, k) => `${x(i + k).toFixed(2)} ${y(upper[i + k] as number).toFixed(2)}`);
    const lo = Array.from({ length: j - i }, (_, k) => `${x(j - 1 - k).toFixed(2)} ${y(lower[j - 1 - k] as number).toFixed(2)}`);
    d += `M${up.join("L")}L${lo.join("L")}Z`;
    i = j;
  }
  return d;
}

export interface CandleShape { x: number; bodyTop: number; bodyHeight: number; wickTop: number; wickBottom: number; up: boolean }
export function candleShape(c: Candle, i: number, s: Scales): CandleShape {
  const yo = s.y(c.o);
  const yc = s.y(c.c);
  return { x: s.x(i), bodyTop: Math.min(yo, yc), bodyHeight: Math.max(Math.abs(yo - yc), 1), wickTop: s.y(c.h), wickBottom: s.y(c.l), up: c.c >= c.o };
}

/** "Nice" axis ticks inside [min, max]; always returns at least 2 ticks when the range is non-degenerate. */
export function niceTicks(min: number, max: number, count = 5): number[] {
  if (!(max > min) || count < 2) return [min];
  const raw = (max - min) / (count - 1);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  let step = ([1, 2, 2.5, 5, 10].find((c) => c >= norm - 1e-12) ?? 10) * mag;
  for (let attempt = 0; attempt < 4; attempt++, step /= 2) {
    const out: number[] = [];
    for (let v = Math.ceil(min / step - 1e-9) * step; v <= max + 1e-9; v += step) out.push(Number(v.toPrecision(12)));
    if (out.length >= 2) return out;
  }
  return [min, max];
}

/** Index of the candle whose timestamp equals `t` (markers, trades); -1 if absent. */
export function indexOfTime(candles: Candle[], t: string): number {
  return candles.findIndex((c) => c.t === t);
}
