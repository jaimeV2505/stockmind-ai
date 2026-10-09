import { linePath, makeScales, niceTicks, type Box } from "../lib/chart.ts";
import { formatNumber } from "../lib/format.ts";
import type { Locale } from "../lib/i18n.ts";
import type { Series } from "../lib/types.ts";

const W = 900;
const H = 120;
const BOX: Box = { width: W, height: H, left: 8, right: 64, top: 8, bottom: 8 };

export interface Line { name: string; data: Series; cls: string }

/** Small indicator panel (RSI, MACD): optional histogram, fixed guides, fixed or auto domain. */
export function LinePanel(props: { title: string; locale: Locale; lines: Line[]; hist?: Series; domain?: [number, number]; guides?: number[]; testId: string }) {
  const { title, locale, lines, hist, domain, guides = [], testId } = props;
  const vals: number[] = [];
  for (const l of lines) for (const v of l.data) if (v !== null) vals.push(v);
  if (hist) for (const v of hist) if (v !== null) vals.push(v);
  let lo = domain ? domain[0] : Math.min(...vals, 0);
  let hi = domain ? domain[1] : Math.max(...vals, 0);
  if (!(hi > lo)) {
    lo -= 1;
    hi += 1;
  }
  const n = lines[0]?.data.length ?? 0;
  if (n === 0) return null;
  const s = makeScales(n, BOX, [lo, hi]);
  const ticks = guides.length ? guides : niceTicks(lo, hi, 3);
  return (
    <figure className="panel" data-testid={testId}>
      <figcaption>{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart small" role="img" aria-label={title}>
        <title>{title}</title>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={BOX.left} x2={W - BOX.right} y1={s.y(v)} y2={s.y(v)} className={guides.length ? "guide" : "grid"} />
            <text x={W - BOX.right + 6} y={s.y(v) + 4} className="axis">{formatNumber(v, locale, v % 1 === 0 ? 0 : 2)}</text>
          </g>
        ))}
        {hist
          ? hist.map((v, i) =>
              v === null ? null : (
                <rect key={i} x={s.x(i) - s.step * 0.3} width={s.step * 0.6} y={Math.min(s.y(v), s.y(0))} height={Math.max(1, Math.abs(s.y(v) - s.y(0)))} className={v >= 0 ? "vol up" : "vol down"} />
              ),
            )
          : null}
        {lines.map((l) => (
          <path key={l.name} d={linePath(l.data, s.x, s.y)} className={`ln ${l.cls}`}>
            <title>{l.name}</title>
          </path>
        ))}
      </svg>
    </figure>
  );
}
