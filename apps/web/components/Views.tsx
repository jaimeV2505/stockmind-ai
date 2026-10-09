import Link from "next/link";
import type { ReactNode } from "react";
import { formatDateTime, formatPct, formatPrice, signed, tone, formatNumber } from "../lib/format.ts";
import { messages, t, type Locale } from "../lib/i18n.ts";
import type { Loaded } from "../lib/snapshot.ts";
import { activeSignals, summarize } from "../lib/summary.ts";
import type { Mode } from "../lib/types.ts";
import { ErrorState } from "./ErrorState.tsx";
import { ModeBanner } from "./ModeBanner.tsx";
import { BacktestPanel, DecisionsPanel, PatternsPanel, RiskPanel } from "./Panels.tsx";
import { SiteHeader } from "./SiteHeader.tsx";
import { StockWorkspace } from "./StockWorkspace.tsx";

export function PageShell({ locale, mode, pathSuffix, children }: { locale: Locale; mode: Mode; pathSuffix: string; children: ReactNode }) {
  return (
    <>
      <ModeBanner locale={locale} mode={mode} />
      <SiteHeader locale={locale} pathSuffix={pathSuffix} />
      <main id="main">{children}</main>
      <footer className="site-footer">{t(locale, "footer")}</footer>
    </>
  );
}

/** When data cannot be loaded the shell still says what mode we are in: the failed state is never mistaken for live data. */
const FALLBACK_MODE: Mode = "simulated";

export function DashboardView({ locale, loaded }: { locale: Locale; loaded: Loaded }) {
  if (!loaded.ok) {
    return <PageShell locale={locale} mode={FALLBACK_MODE} pathSuffix=""><ErrorState locale={locale} detail={loaded.error} /></PageShell>;
  }
  const { meta, symbols } = loaded.data;
  const rows = symbols.map(summarize);
  const signals = activeSignals(symbols);
  return (
    <PageShell locale={locale} mode={meta.mode} pathSuffix="">
      <h1>{t(locale, "dashboardTitle")}</h1>
      <p className="lead">{t(locale, "dashboardIntro")}</p>
      <p className="meta" data-testid="freshness">
        {t(locale, "dataAsOf")}: <time dateTime={meta.as_of}>{formatDateTime(meta.as_of, locale)}</time> · {t(locale, "generated")}: <time dateTime={meta.generated_at}>{formatDateTime(meta.generated_at, locale)}</time> · {meta.data_source}
      </p>
      <section className="card" aria-labelledby="mk-h">
        <h2 id="mk-h">{t(locale, "navDashboard")}</h2>
        <div className="table-wrap">
          <table data-testid="symbols-table">
            <caption className="sr-only">{t(locale, "dashboardTitle")}</caption>
            <thead>
              <tr>
                <th scope="col">{t(locale, "colSymbol")}</th><th scope="col">{t(locale, "colName")}</th>
                <th scope="col" className="num">{t(locale, "colClose")}</th><th scope="col" className="num">{t(locale, "colChange")}</th>
                <th scope="col" className="num">{t(locale, "colRsi")}</th><th scope="col" className="num">{t(locale, "colSignals")}</th>
                <th scope="col">{t(locale, "colAction")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.symbol}>
                  <th scope="row">{r.symbol}</th>
                  <td>{r.name}</td>
                  <td className="num">{formatPrice(r.close, locale)}</td>
                  <td className={`num tone-${tone(r.changePct)}`}>{signed(formatPct(r.changePct, locale), r.changePct)}</td>
                  <td className="num">{formatNumber(r.rsi, locale, 1)}</td>
                  <td className="num">{r.signals} / {r.strategies}</td>
                  <td><Link href={`/${locale}/stock/${r.symbol}`} aria-label={`${t(locale, "open")} ${r.symbol}`}>{t(locale, "open")}</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="card" aria-labelledby="sg-h" data-testid="signals-section">
        <h2 id="sg-h">{t(locale, "signalsTitle")}</h2>
        {signals.length === 0 ? (
          <p data-testid="no-signals">{t(locale, "noSignalsToday")}</p>
        ) : (
          <ul>
            {signals.map(({ symbol, decision }) => (
              <li key={`${symbol}-${decision.strategy}`}><Link href={`/${locale}/stock/${symbol}`}>{symbol}</Link> — {decision.strategy} ({decision.status})</li>
            ))}
          </ul>
        )}
      </section>
    </PageShell>
  );
}

export function StockView({ locale, loaded, symbol }: { locale: Locale; loaded: Loaded; symbol: string }) {
  const suffix = `/stock/${symbol}`;
  if (!loaded.ok) {
    return <PageShell locale={locale} mode={FALLBACK_MODE} pathSuffix={suffix}><ErrorState locale={locale} detail={loaded.error} /></PageShell>;
  }
  const data = loaded.data.symbols.find((s) => s.symbol === symbol);
  if (!data) {
    return (
      <PageShell locale={locale} mode={loaded.data.meta.mode} pathSuffix="">
        <h1>{t(locale, "notFoundTitle")}</h1>
        <p><Link href={`/${locale}`}>{t(locale, "stockBack")}</Link></p>
      </PageShell>
    );
  }
  const row = summarize(data);
  return (
    <PageShell locale={locale} mode={loaded.data.meta.mode} pathSuffix={suffix}>
      <p><Link href={`/${locale}`}>← {t(locale, "stockBack")}</Link></p>
      <h1>{data.symbol} <span className="muted">{data.name}</span></h1>
      <p className="meta" data-testid="stock-summary">
        {formatPrice(row.close, locale)} {data.currency} · <span className={`tone-${tone(row.changePct)}`}>{signed(formatPct(row.changePct, locale), row.changePct)}</span> · {t(locale, "dataAsOf")}{" "}
        <time dateTime={loaded.data.meta.as_of}>{formatDateTime(loaded.data.meta.as_of, locale)}</time> · {loaded.data.meta.data_source}
      </p>
      <StockWorkspace data={data} locale={locale} />
      <DecisionsPanel decisions={data.decisions} locale={locale} />
      <BacktestPanel backtests={data.backtests} locale={locale} />
      <PatternsPanel patterns={data.patterns} locale={locale} />
      <RiskPanel r={data.risk_example} locale={locale} />
    </PageShell>
  );
}

export function MethodView({ locale, mode }: { locale: Locale; mode: Mode }) {
  return (
    <PageShell locale={locale} mode={mode} pathSuffix="/method">
      <h1>{t(locale, "methodTitle")}</h1>
      <ul className="notes">{messages[locale].methodBody.map((p) => <li key={p}>{p}</li>)}</ul>
    </PageShell>
  );
}
