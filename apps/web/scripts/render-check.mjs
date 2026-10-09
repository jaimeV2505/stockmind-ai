// Offline verification harness (NOT part of the Next build). Compiles the TS/TSX with the TypeScript API, renders the real React
// components to static HTML with react-dom/server using the real snapshot, then opens them in headless Chromium to check layout,
// accessibility basics and data-mode labelling at desktop and mobile widths. `next/link` is stubbed with a plain <a>.
//   NODE_PATH=<global node_modules> node scripts/render-check.mjs [--shots <dir>]
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const GLOBAL = process.env.NODE_PATH?.split(path.delimiter)[0] ?? "/home/claude/.npm-global/lib/node_modules";
const ts = require(path.join(GLOBAL, "typescript"));
const { chromium } = require(path.join(GLOBAL, "playwright"));
const ROOT = path.resolve(new URL("..", import.meta.url).pathname);
const OUT = fs.mkdtempSync("/tmp/webrender-");
const shotsDir = process.argv.includes("--shots") ? process.argv[process.argv.indexOf("--shots") + 1] : null;
if (shotsDir) fs.mkdirSync(shotsDir, { recursive: true });

// ---- 1. compile lib/ + components/ ------------------------------------------------------------------------------------------
for (const dir of ["lib", "components"]) {
  fs.mkdirSync(path.join(OUT, dir), { recursive: true });
  for (const f of fs.readdirSync(path.join(ROOT, dir))) {
    if (!/\.tsx?$/.test(f) || f.endsWith(".test.ts") || f === "server-data.ts") continue;
    const src = fs.readFileSync(path.join(ROOT, dir, f), "utf8");
    const res = ts.transpileModule(src, { fileName: f, reportDiagnostics: true, compilerOptions: { target: "ES2022", module: "ESNext", jsx: "react-jsx", rewriteRelativeImportExtensions: true, isolatedModules: true } });
    const errs = (res.diagnostics ?? []).filter((d) => d.category === ts.DiagnosticCategory.Error);
    if (errs.length) throw new Error(`syntax error in ${dir}/${f}: ${ts.flattenDiagnosticMessageText(errs[0].messageText, "\n")}`);
    fs.writeFileSync(path.join(OUT, dir, f.replace(/\.tsx?$/, ".js")), res.outputText);
  }
}
fs.writeFileSync(path.join(OUT, "package.json"), '{"type":"module"}');
const nm = path.join(OUT, "node_modules");
fs.mkdirSync(path.join(nm, "next"), { recursive: true });
for (const pkg of ["react", "react-dom"]) fs.symlinkSync(path.join(GLOBAL, pkg), path.join(nm, pkg));
fs.writeFileSync(path.join(nm, "next", "package.json"), '{"name":"next","type":"module","exports":{"./link":"./link.js"}}');
fs.writeFileSync(path.join(nm, "next", "link.js"), 'import { createElement } from "react"; export default function Link({ href, children, ...rest }) { return createElement("a", { href, ...rest }, children); }');

const imp = (p) => import(pathToFileURL(path.join(OUT, p)).href);
const React = await imp("node_modules/react/index.js");
const { renderToStaticMarkup } = await imp("node_modules/react-dom/server.node.js");
const { DashboardView, StockView, MethodView } = await imp("components/Views.js");
const { CandleChart } = await imp("components/CandleChart.js");
const { DEFAULT_PREFS } = await imp("lib/summary.js");
const { loadFromText } = await imp("lib/snapshot.js");
const h = React.createElement;

const raw = fs.readFileSync(path.join(ROOT, "data", "demo-snapshot.json"), "utf8");
const loaded = loadFromText(raw);
if (!loaded.ok) throw new Error("real snapshot invalid: " + loaded.error);
const css = fs.readFileSync(path.join(ROOT, "app", "globals.css"), "utf8");
const page = (locale, body) => `<!doctype html><html lang="${locale}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>t</title><style>${css}</style></head><body>${body}</body></html>`;

const pages = {
  "dashboard-es": page("es", renderToStaticMarkup(h(DashboardView, { locale: "es", loaded }))),
  "dashboard-en": page("en", renderToStaticMarkup(h(DashboardView, { locale: "en", loaded }))),
  "stock-es": page("es", renderToStaticMarkup(h(StockView, { locale: "es", loaded, symbol: "SIMA" }))),
  "stock-en": page("en", renderToStaticMarkup(h(StockView, { locale: "en", loaded, symbol: "SIMD" }))),
  "method-es": page("es", renderToStaticMarkup(h(MethodView, { locale: "es", mode: "simulated" }))),
  "error-es": page("es", renderToStaticMarkup(h(DashboardView, { locale: "es", loaded: loadFromText('{"schema_version":1,"meta":{}}') }))),
  "unknown-symbol": page("en", renderToStaticMarkup(h(StockView, { locale: "en", loaded, symbol: "NVDA" }))),
};
for (const [n, html] of Object.entries(pages)) fs.writeFileSync(path.join(OUT, `${n}.html`), html);

// ---- 2. assertions on the rendered markup ------------------------------------------------------------------------------------
const failures = [];
const check = (cond, msg) => { if (!cond) failures.push(msg); };
const count = (s, re) => (s.match(re) ?? []).length;
const sim = loaded.data.symbols.find((s) => s.symbol === "SIMA");

for (const [n, html] of Object.entries(pages)) {
  check(html.includes('data-testid="mode-banner"'), `${n}: mode banner missing`);
  check(/data-mode="simulated"/.test(html), `${n}: banner is not in simulated mode`);
  check(count(html, /<h1[ >]/g) === 1, `${n}: expected exactly one <h1>, found ${count(html, /<h1[ >]/g)}`);
  check(count(html, /<table/g) === count(html, /<caption/g), `${n}: every table needs a <caption>`);
  check(!/NaN|undefined|Infinity|\[object Object\]/.test(html.replace(/<style>[\s\S]*?<\/style>/, "")), `${n}: leaked NaN/undefined/[object Object] into the UI`);
  for (const m of html.matchAll(/<svg[^>]*>/g)) check(/role="img"/.test(m[0]) && /aria-label=/.test(m[0]), `${n}: <svg> without role=img + aria-label`);
  for (const m of html.matchAll(/<input[^>]*>/g)) check(/type="checkbox"/.test(m[0]), `${n}: unexpected input`);
}
check(/SIMULADOS/.test(pages["dashboard-es"]) && /SIMULATED/.test(pages["dashboard-en"]), "banner text not localised");
check(pages["dashboard-es"].includes('data-testid="no-signals"') && /NO SIGNAL/.test(pages["dashboard-es"]), "dashboard must show an explicit NO SIGNAL state when there are none");
check(count(pages["dashboard-es"], /<tr>/g) >= 6, "dashboard table should list 5 symbols + header");
check(/href="\/es\/stock\/SIMA"/.test(pages["dashboard-es"]) && /href="\/en"/.test(pages["dashboard-es"]), "dashboard links / locale switch");
check(pages["stock-es"].includes('lang="es"') && pages["stock-en"].includes('lang="en"'), "lang attribute");
check(count(pages["stock-es"], /<g class="candle (up|down)"/g) === sim.candles.length, `stock page should draw ${sim.candles.length} candles`);
// React 19 hoists <title> to <head>, except inside <svg>: the per-candle tooltips must stay inside their <g class="candle">
check(count(pages["stock-es"], /<g class="candle (?:up|down)"><title>/g) === sim.candles.length, "per-candle <title> tooltips must remain inside the SVG (not hoisted)");
check(count(pages["stock-es"], /<title>/g) >= sim.candles.length + 1, "svg <title> elements missing");
check(pages["stock-es"].includes('data-testid="ov-ema20"') && pages["stock-es"].includes('data-testid="ov-volume"') && pages["stock-es"].includes('data-testid="panel-rsi"'), "default overlays: EMA20, volume, RSI");
check(!pages["stock-es"].includes('data-testid="ov-bollinger"') && !pages["stock-es"].includes('data-testid="panel-macd"'), "bollinger/macd are off by default");
check(count(pages["stock-es"], /data-testid="backtest"/g) === 3 && /SIM</.test(pages["stock-es"]), "three simulated backtests, each tagged SIM");
check(/Backtest \(SIMULADO\)/.test(pages["stock-es"]) && /Backtest \(SIMULATED\)/.test(pages["stock-en"]), "backtest section must say simulated");
check(/NO SIGNAL|SIN SEÑAL/.test(pages["stock-es"]), "per-strategy NO SIGNAL rows");
check(/no es una probabilidad|NOT a probability|NO es una probabilidad/i.test(pages["stock-es"] + pages["stock-en"]), "pattern similarity disclaimer");
check(pages["error-es"].includes('data-testid="error-state"') && /role="alert"/.test(pages["error-es"]) && !/class="candle/.test(pages["error-es"]), "invalid snapshot -> error state, no data");
check(/Symbol not found/.test(pages["unknown-symbol"]) && !/class="candle/.test(pages["unknown-symbol"]), "unknown symbol -> not-found message, no data");
// overlay toggles are driven by `prefs`: verify the chart honours every switch
for (const k of ["ema20", "ema50", "sma200", "bollinger", "volume", "entries"]) {
  const on = renderToStaticMarkup(h(CandleChart, { symbol: "SIMA", locale: "en", candles: sim.candles, indicators: sim.indicators, markers: sim.markers, prefs: { ...DEFAULT_PREFS, [k]: true } }));
  const off = renderToStaticMarkup(h(CandleChart, { symbol: "SIMA", locale: "en", candles: sim.candles, indicators: sim.indicators, markers: sim.markers, prefs: { ...DEFAULT_PREFS, [k]: false } }));
  const id = k === "entries" ? "entry-marker" : `ov-${k}`;
  check(on.includes(`data-testid="${id}"`) && !off.includes(`data-testid="${id}"`), `toggle '${k}' must add/remove its overlay`);
}
check(count(renderToStaticMarkup(h(CandleChart, { symbol: "SIMA", locale: "en", candles: sim.candles, indicators: sim.indicators, markers: sim.markers, prefs: DEFAULT_PREFS })), /data-testid="entry-marker"/g) === sim.markers.length, "one marker per entry flag");

// ---- 3. real browser: layout, overflow, console errors, screenshots ---------------------------------------------------------
const browser = await chromium.launch();
const sizes = { desktop: { width: 1280, height: 900 }, mobile: { width: 390, height: 800 } };
for (const [name, vp] of Object.entries(sizes)) {
  const ctx = await browser.newContext({ viewport: vp });
  for (const n of Object.keys(pages)) {
    const p = await ctx.newPage();
    const errors = [];
    p.on("pageerror", (e) => errors.push(e.message));
    p.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    await p.goto(pathToFileURL(path.join(OUT, `${n}.html`)).href);
    const m = await p.evaluate(() => ({
      overflow: document.documentElement.scrollWidth - window.innerWidth,
      bannerVisible: !!document.querySelector("[data-testid=mode-banner]") && document.querySelector("[data-testid=mode-banner]").getBoundingClientRect().height > 10,
      chartW: document.querySelector("[data-testid=candle-chart]")?.getBoundingClientRect().width ?? null,
      candles: document.querySelectorAll("g.candle").length,
    }));
    check(m.overflow <= 1, `${n}@${name}: horizontal overflow of ${m.overflow}px`);
    check(m.bannerVisible, `${n}@${name}: banner not visible`);
    if (m.chartW !== null) check(m.chartW > vp.width * 0.8 && m.chartW <= vp.width, `${n}@${name}: chart width ${m.chartW} does not fit viewport ${vp.width}`);
    check(errors.length === 0, `${n}@${name}: browser errors: ${errors.join(" | ")}`);
    if (shotsDir && ["dashboard-es", "stock-es", "error-es"].includes(n)) await p.screenshot({ path: path.join(shotsDir, `${n}-${name}.png`), fullPage: n !== "stock-es" || name === "mobile" ? true : false });
    await p.close();
  }
  await ctx.close();
}
await browser.close();

console.log(`rendered ${Object.keys(pages).length} pages x 2 viewports; ${failures.length} failure(s)`);
for (const f of failures) console.log("  FAIL:", f);
fs.rmSync(OUT, { recursive: true, force: true });
process.exit(failures.length ? 1 : 0);
