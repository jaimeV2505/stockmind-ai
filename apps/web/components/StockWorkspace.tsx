"use client";

import { useEffect, useState } from "react";
import { t, type Locale, type MessageKey } from "../lib/i18n.ts";
import { DEFAULT_PREFS, OVERLAY_KEYS, parsePrefs, PREFS_KEY, type OverlayKey, type Prefs } from "../lib/summary.ts";
import type { SymbolData } from "../lib/types.ts";
import { CandleChart } from "./CandleChart.tsx";
import { LinePanel } from "./LinePanel.tsx";

const LABEL: Record<OverlayKey, MessageKey> = {
  ema20: "ema20", ema50: "ema50", sma200: "sma200", bollinger: "bollinger", volume: "volume", rsi: "rsi", macd: "macd", entries: "entries",
};

/** Chart + indicator toggles. Preferences persist in localStorage (validated on read: storage is untrusted). */
export function StockWorkspace({ data, locale }: { data: SymbolData; locale: Locale }) {
  const [prefs, setPrefs] = useState<Prefs>(DEFAULT_PREFS);
  useEffect(() => {
    try {
      setPrefs(parsePrefs(window.localStorage.getItem(PREFS_KEY)));
    } catch {
      /* storage blocked (private mode): keep defaults */
    }
  }, []);
  const toggle = (k: OverlayKey) => {
    const next = { ...prefs, [k]: !prefs[k] };
    setPrefs(next);
    try {
      window.localStorage.setItem(PREFS_KEY, JSON.stringify(next));
    } catch {
      /* ignore */
    }
  };
  const ind = data.indicators;
  return (
    <section className="card" aria-labelledby="chart-h">
      <h2 id="chart-h">{t(locale, "chartTitle")}</h2>
      <fieldset className="toggles">
        <legend>{t(locale, "overlays")}</legend>
        {OVERLAY_KEYS.map((k) => (
          <label key={k} className="toggle">
            <input type="checkbox" checked={prefs[k]} onChange={() => toggle(k)} data-testid={`toggle-${k}`} />
            <span>{t(locale, LABEL[k])}</span>
          </label>
        ))}
      </fieldset>
      <CandleChart symbol={data.symbol} locale={locale} candles={data.candles} indicators={ind} markers={data.markers} prefs={prefs} />
      {prefs.rsi ? (
        <LinePanel title={t(locale, "rsi")} locale={locale} testId="panel-rsi" domain={[0, 100]} guides={[30, 50, 70]} lines={[{ name: "RSI 14", data: ind.rsi14, cls: "ln-rsi" }]} />
      ) : null}
      {prefs.macd ? (
        <LinePanel title={t(locale, "macd")} locale={locale} testId="panel-macd" hist={ind.macd_hist}
          lines={[{ name: "MACD", data: ind.macd, cls: "ln-ema20" }, { name: "Signal", data: ind.macd_signal, cls: "ln-ema50" }]} />
      ) : null}
    </section>
  );
}
