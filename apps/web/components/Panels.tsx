import { linePath, makeScales, priceDomain, type Box } from "../lib/chart.ts";
import { formatDate, formatInt, formatNumber, formatPct, formatPrice, signed, tone } from "../lib/format.ts";
import { t, type Locale } from "../lib/i18n.ts";
import { visibleNotes } from "../lib/notes.ts";
import type { Backtest, Decision, PatternSummary, Patterns, RiskExample } from "../lib/types.ts";

const metric = (b: Backtest, k: string) => {
  const v = b.metrics[k];
  return typeof v === "number" ? v : null;
};

export function DecisionsPanel({ decisions, locale }: { decisions: Decision[]; locale: Locale }) {
  return (
    <section className="card" aria-labelledby="dec-h" data-testid="decisions">
      <h2 id="dec-h">{t(locale, "signalsPanel")}</h2>
      <div className="table-wrap">
        <table>
          <caption className="sr-only">{t(locale, "signalsPanel")}</caption>
          <thead>
            <tr><th scope="col">{t(locale, "strategy")}</th><th scope="col">{t(locale, "version")}</th><th scope="col">{t(locale, "result")}</th><th scope="col">{t(locale, "reason")}</th></tr>
          </thead>
          <tbody>
            {decisions.map((d) => (
              <tr key={d.strategy}>
                <th scope="row">{d.strategy}</th>
                <td><code>{d.version}</code></td>
                <td className={d.kind === "signal" ? "tag tag-signal" : "tag tag-none"}>{d.kind === "signal" ? t(locale, "signal") : t(locale, "noSignal")}</td>
                <td>
                  {d.kind === "no_signal" ? (
                    d.reason
                  ) : (
                    <ul>
                      {d.supporting.map((e) => <li key={`s-${e.name}`}>{t(locale, "supporting")}: {e.name} = {String(e.value)} {e.note}</li>)}
                      {d.contradicting.map((e) => <li key={`c-${e.name}`}>{t(locale, "contradicting")}: {e.name} {String(e.value)} {e.note}</li>)}
                    </ul>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const EQ: Box = { width: 400, height: 90, left: 4, right: 4, top: 6, bottom: 6 };

function EquityChart({ equity, initial, label }: { equity: number[]; initial: number; label: string }) {
  const [lo, hi] = priceDomain(equity.map((v) => ({ t: "", o: v, h: v, l: v, c: v, v: 0 })), [[initial]]);
  const s = makeScales(equity.length, EQ, [lo, hi]);
  return (
    <svg viewBox={`0 0 ${EQ.width} ${EQ.height}`} className="chart equity" role="img" aria-label={label}>
      <title>{label}</title>
      <line x1={EQ.left} x2={EQ.width - EQ.right} y1={s.y(initial)} y2={s.y(initial)} className="guide" />
      <path d={linePath(equity, s.x, s.y)} className="ln ln-equity" />
    </svg>
  );
}

export function BacktestPanel({ backtests, locale }: { backtests: Backtest[]; locale: Locale }) {
  const na = t(locale, "undefinedMetric");
  const pct = (x: number | null) => (x === null ? na : formatPct(x, locale));
  return (
    <section className="card" aria-labelledby="bt-h" data-testid="backtests">
      <h2 id="bt-h">{t(locale, "backtestTitle")}</h2>
      <p className="note">{t(locale, "backtestNote")}</p>
      <div className="bt-grid">
        {backtests.map((b) => {
          const tr = metric(b, "total_return");
          return (
            <article key={b.strategy} className="bt" data-testid="backtest">
              <h3>{b.strategy} <span className="sim-tag">SIM</span></h3>
              <EquityChart equity={b.equity} initial={Number(b.config.initial_capital)} label={t(locale, "equityAria", { strategy: b.strategy })} />
              <dl className="metrics">
                <div><dt>{t(locale, "mTotalReturn")}</dt><dd className={`tone-${tone(tr)}`}>{tr === null ? na : signed(formatPct(tr, locale), tr)}</dd></div>
                <div><dt>{t(locale, "mBuyHold")}</dt><dd>{pct(metric(b, "buy_hold_return"))}</dd></div>
                <div><dt>{t(locale, "mTrades")}</dt><dd>{formatInt(metric(b, "n_trades"), locale)}</dd></div>
                <div><dt>{t(locale, "mWinRate")}</dt><dd>{pct(metric(b, "win_rate"))}</dd></div>
                <div><dt>{t(locale, "mProfitFactor")}</dt><dd>{metric(b, "profit_factor") === null ? na : formatNumber(metric(b, "profit_factor"), locale)}</dd></div>
                <div><dt>{t(locale, "mMaxDd")}</dt><dd>{pct(metric(b, "max_drawdown"))}</dd></div>
                <div><dt>{t(locale, "mExposure")}</dt><dd>{pct(metric(b, "exposure"))}</dd></div>
                <div><dt>{t(locale, "mSharpe")}</dt><dd>{metric(b, "sharpe") === null ? na : formatNumber(metric(b, "sharpe"), locale)}</dd></div>
              </dl>
              {visibleNotes(locale, b.warnings).map((w) => <p key={w} className="note">{w}</p>)}
              {b.trades.length > 0 ? (
                <details>
                  <summary>{t(locale, "tradesTitle")} ({b.trades.length})</summary>
                  <div className="table-wrap">
                    <table>
                      <caption className="sr-only">{t(locale, "tradesTitle")}</caption>
                      <thead><tr><th scope="col">{t(locale, "colEntry")}</th><th scope="col">{t(locale, "colExit")}</th><th scope="col">{t(locale, "colPnl")}</th><th scope="col">{t(locale, "colWhy")}</th></tr></thead>
                      <tbody>
                        {b.trades.map((x) => (
                          <tr key={x.entry}>
                            <td>{formatDate(x.entry, locale)} @ {formatPrice(x.entry_price, locale)}</td>
                            <td>{formatDate(x.exit, locale)} @ {formatPrice(x.exit_price, locale)}</td>
                            <td className={`tone-${tone(x.pnl)}`}>{signed(formatPrice(x.pnl, locale), x.pnl)}</td>
                            <td>{x.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function Summary({ s, h, locale }: { s: PatternSummary; h: number; locale: Locale }) {
  const f = (x: number | undefined) => (x === undefined ? "—" : formatPct(x, locale));
  return (
    <>
      <dl className="metrics">
        <div><dt>{t(locale, "pSample")}</dt><dd>{s.n}</dd></div>
        <div><dt>{t(locale, "pMedian", { h })}</dt><dd>{f(s.median_forward_return)}</dd></div>
        <div><dt>{t(locale, "pPositive")}</dt><dd>{f(s.share_positive)}</dd></div>
        <div><dt>{t(locale, "pMfe")}</dt><dd>{f(s.median_mfe)}</dd></div>
        <div><dt>{t(locale, "pMae")}</dt><dd>{f(s.median_mae)}</dd></div>
        <div><dt>{t(locale, "pWorstMae")}</dt><dd>{f(s.worst_mae)}</dd></div>
        <div><dt>{t(locale, "pCi")}</dt><dd>{s.ci_median_95 ? `${formatPct(s.ci_median_95[0], locale)} … ${formatPct(s.ci_median_95[1], locale)}` : t(locale, "pNoCi")}</dd></div>
      </dl>
      <ul className="notes">{visibleNotes(locale, s.notes).map((n) => <li key={n}>{n}</li>)}</ul>
    </>
  );
}

export function PatternsPanel({ patterns, locale }: { patterns: Patterns; locale: Locale }) {
  return (
    <section className="card" aria-labelledby="pt-h" data-testid="patterns">
      <h2 id="pt-h">{t(locale, "patternsTitle")}</h2>
      <p className="note">{t(locale, "patternsNote")}</p>
      {patterns.matches.length === 0 ? <p>{t(locale, "patternsEmpty")}</p> : null}
      <Summary s={patterns.summary} h={patterns.horizon} locale={locale} />
      {patterns.matches.length > 0 ? (
        <div className="table-wrap">
          <table>
            <caption className="sr-only">{t(locale, "patternsTitle")}</caption>
            <thead><tr><th scope="col">{t(locale, "colSymbol")}</th><th scope="col">{t(locale, "colWindowEnd")}</th><th scope="col">{t(locale, "colSimilarity")}</th><th scope="col">{t(locale, "colFwd")}</th><th scope="col">{t(locale, "colMfe")}</th><th scope="col">{t(locale, "colMae")}</th></tr></thead>
            <tbody>
              {patterns.matches.map((m) => (
                <tr key={`${m.symbol}-${m.window_end}`}>
                  <th scope="row">{m.symbol}</th>
                  <td>{formatDate(m.window_end, locale)}</td>
                  <td>{formatNumber(m.similarity, locale, 3)}</td>
                  <td className={`tone-${tone(m.forward_return)}`}>{signed(formatPct(m.forward_return, locale), m.forward_return)}</td>
                  <td>{formatPct(m.mfe, locale)}</td>
                  <td>{formatPct(m.mae, locale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

export function RiskPanel({ r, locale }: { r: RiskExample; locale: Locale }) {
  return (
    <section className="card" aria-labelledby="rk-h" data-testid="risk">
      <h2 id="rk-h">{t(locale, "riskTitle")}</h2>
      <p className="note">{t(locale, "riskNote")}</p>
      <dl className="metrics">
        <div><dt>{t(locale, "rEntry")}</dt><dd>{formatPrice(r.entry, locale)}</dd></div>
        <div><dt>{t(locale, "rStop")}</dt><dd>{formatPrice(r.stop, locale)}</dd></div>
        <div><dt>{t(locale, "rShares")}</dt><dd>{formatInt(r.shares, locale)}</dd></div>
        <div><dt>{t(locale, "rRiskAmt")}</dt><dd>{formatPrice(r.risk_amount, locale)}</dd></div>
        <div><dt>{t(locale, "rNotional")}</dt><dd>{formatPrice(r.notional, locale)}</dd></div>
        <div><dt>{t(locale, "rBinding")}</dt><dd>{r.binding}</dd></div>
        <div><dt>{t(locale, "rRR")}</dt><dd>{formatNumber(r.reward_risk_at_3R, locale)}</dd></div>
      </dl>
    </section>
  );
}
