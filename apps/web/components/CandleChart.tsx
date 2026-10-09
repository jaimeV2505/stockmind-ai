import { bandPath, candleShape, indexOfTime, linePath, makeScales, niceTicks, priceDomain, type Box } from "../lib/chart.ts";
import { formatDate, formatInt, formatPrice } from "../lib/format.ts";
import { t, type Locale } from "../lib/i18n.ts";
import type { Prefs } from "../lib/summary.ts";
import type { Candle, Indicators, Marker, Series } from "../lib/types.ts";

const W = 900;
const PRICE_H = 300;
const VOL_TOP = 312;
const VOL_H = 56;
const BOX: Box = { width: W, height: PRICE_H, left: 8, right: 64, top: 10, bottom: 22 };

export function CandleChart(props: { symbol: string; locale: Locale; candles: Candle[]; indicators: Indicators; markers: Marker[]; prefs: Prefs }) {
  const { symbol, locale, candles, indicators: ind, markers, prefs } = props;
  const overlays: Series[] = [];
  if (prefs.ema20) overlays.push(ind.ema20);
  if (prefs.ema50) overlays.push(ind.ema50);
  if (prefs.sma200) overlays.push(ind.sma200);
  if (prefs.bollinger) overlays.push(ind.bb_upper, ind.bb_lower);
  const [lo, hi] = priceDomain(candles, overlays);
  const s = makeScales(candles.length, BOX, [lo, hi]);
  const ticks = niceTicks(lo, hi, 6);
  const totalH = prefs.volume ? VOL_TOP + VOL_H + 8 : PRICE_H + 8;
  const maxV = Math.max(...candles.map((c) => c.v), 1);
  const bw = Math.max(1, s.step * 0.62);
  const labelEvery = Math.max(1, Math.round(candles.length / 6));
  return (
    <svg viewBox={`0 0 ${W} ${totalH}`} className="chart" role="img" aria-label={t(locale, "chartAria", { symbol, n: candles.length })} data-testid="candle-chart">
      <title>{t(locale, "chartAria", { symbol, n: candles.length })}</title>
      {ticks.map((v) => (
        <g key={v}>
          <line x1={BOX.left} x2={W - BOX.right} y1={s.y(v)} y2={s.y(v)} className="grid" />
          <text x={W - BOX.right + 6} y={s.y(v) + 4} className="axis">{formatPrice(v, locale)}</text>
        </g>
      ))}
      {candles.map((c, i) =>
        i % labelEvery === 0 ? (
          <text key={c.t} x={s.x(i)} y={PRICE_H - 4} className="axis" textAnchor={s.x(i) < 60 ? "start" : "middle"}>{formatDate(c.t, locale)}</text>
        ) : null,
      )}
      {prefs.bollinger ? (
        <g data-testid="ov-bollinger">
          <path d={bandPath(ind.bb_upper, ind.bb_lower, s.x, s.y)} className="band" />
          <path d={linePath(ind.bb_upper, s.x, s.y)} className="ln ln-bb" />
          <path d={linePath(ind.bb_lower, s.x, s.y)} className="ln ln-bb" />
        </g>
      ) : null}
      {candles.map((c, i) => {
        const k = candleShape(c, i, s);
        return (
          <g key={c.t} className={k.up ? "candle up" : "candle down"}>
            <title>{`${formatDate(c.t, locale)}  O ${formatPrice(c.o, locale)}  H ${formatPrice(c.h, locale)}  L ${formatPrice(c.l, locale)}  C ${formatPrice(c.c, locale)}  V ${formatInt(c.v, locale)}`}</title>
            <line x1={k.x} x2={k.x} y1={k.wickTop} y2={k.wickBottom} />
            <rect x={k.x - bw / 2} y={k.bodyTop} width={bw} height={k.bodyHeight} />
          </g>
        );
      })}
      {prefs.ema20 ? <path d={linePath(ind.ema20, s.x, s.y)} className="ln ln-ema20" data-testid="ov-ema20" /> : null}
      {prefs.ema50 ? <path d={linePath(ind.ema50, s.x, s.y)} className="ln ln-ema50" data-testid="ov-ema50" /> : null}
      {prefs.sma200 ? <path d={linePath(ind.sma200, s.x, s.y)} className="ln ln-sma200" data-testid="ov-sma200" /> : null}
      {prefs.entries
        ? markers.map((m) => {
            const i = indexOfTime(candles, m.t);
            if (i < 0) return null;
            const x = s.x(i);
            const y = s.y(candles[i].l) + 9;
            return (
              <path key={`${m.strategy}-${m.t}`} d={`M${x} ${y - 6}L${x - 5} ${y + 3}L${x + 5} ${y + 3}Z`} className="marker" data-testid="entry-marker">
                <title>{`${m.strategy}: ${t(locale, "entries")} ${formatDate(m.t, locale)}`}</title>
              </path>
            );
          })
        : null}
      {prefs.volume ? (
        <g data-testid="ov-volume" aria-hidden="true">
          {candles.map((c, i) => {
            const h = Math.max(1, (c.v / maxV) * VOL_H);
            return <rect key={c.t} x={s.x(i) - bw / 2} y={VOL_TOP + VOL_H - h} width={bw} height={h} className={c.c >= c.o ? "vol up" : "vol down"} />;
          })}
        </g>
      ) : null}
    </svg>
  );
}
