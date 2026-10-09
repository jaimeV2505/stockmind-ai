export const LOCALES = ["es", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "es";
export const isLocale = (x: string): x is Locale => (LOCALES as readonly string[]).includes(x);

const es = {
  appName: "StockMind AI",
  navDashboard: "Panel",
  navMethod: "Método y límites",
  language: "Idioma",
  bannerSimulated: "MODO DEMO — DATOS SIMULADOS. Los símbolos son ficticios. No es información de mercado ni asesoramiento de inversión.",
  bannerDelayed: "DATOS CON RETRASO",
  bannerLive: "DATOS EN VIVO",
  dataAsOf: "Datos hasta",
  generated: "Generado",
  dashboardTitle: "Panel de mercado (simulado)",
  dashboardIntro: "Resultados de los motores de StockMind sobre datos simulados deterministas. Sirve para revisar el producto, no para decidir inversiones.",
  colSymbol: "Símbolo", colName: "Nombre", colClose: "Cierre", colChange: "Var. 1d", colRsi: "RSI 14", colSignals: "Señales hoy", colAction: "Análisis",
  open: "Abrir",
  signalsTitle: "Señales activas",
  noSignalsToday: "Sin señales hoy. NO SIGNAL / EVIDENCIA INSUFICIENTE: el sistema no inventa oportunidades para llenar el panel.",
  stockBack: "Volver al panel",
  chartTitle: "Gráfico de velas diarias",
  chartAria: "Gráfico de velas de {symbol}, {n} sesiones",
  overlays: "Indicadores", ema20: "EMA 20", ema50: "EMA 50", sma200: "SMA 200", bollinger: "Bandas de Bollinger", volume: "Volumen", rsi: "RSI 14", macd: "MACD", entries: "Banderas de entrada",
  signalsPanel: "Estrategias y señales",
  strategy: "Estrategia", version: "Versión", result: "Resultado", noSignal: "SIN SEÑAL", signal: "SEÑAL", supporting: "A favor", contradicting: "En contra", reason: "Motivo",
  backtestTitle: "Backtest (SIMULADO)",
  backtestNote: "Resultado simulado sobre datos simulados. No indica rendimiento futuro. Ejecución en la apertura de la barra siguiente, con comisiones y deslizamiento.",
  mTotalReturn: "Retorno total", mBuyHold: "Comprar y mantener", mTrades: "Operaciones", mWinRate: "% aciertos", mProfitFactor: "Factor de beneficio", mMaxDd: "Máx. drawdown", mExposure: "Exposición", mSharpe: "Sharpe",
  undefinedMetric: "n/d",
  equityAria: "Curva de capital simulada de {strategy}",
  tradesTitle: "Operaciones simuladas", colEntry: "Entrada", colExit: "Salida", colPnl: "P&L", colWhy: "Motivo de salida",
  patternsTitle: "Patrones históricos similares",
  patternsNote: "La similitud es una distancia sin calibrar, NO una probabilidad. Los resultados son estadísticas descriptivas de muestras pasadas y correlacionadas.",
  patternsEmpty: "Sin coincidencias históricas: EVIDENCIA INSUFICIENTE.",
  pSample: "Coincidencias", pMedian: "Mediana a {h} sesiones", pPositive: "Con retorno positivo", pMfe: "MFE mediana", pMae: "MAE mediana", pWorstMae: "Peor MAE", pCi: "IC 95% de la mediana",
  pNoCi: "Sin IC: muestra demasiado pequeña (n < 30).",
  colSimilarity: "Similitud", colWindowEnd: "Fin de ventana", colFwd: "Retorno futuro", colMfe: "MFE", colMae: "MAE",
  riskTitle: "Ejemplo de gestión de riesgo (ilustrativo)",
  riskNote: "Cálculo mecánico sobre el último cierre simulado. No es una recomendación.",
  rEntry: "Entrada de referencia", rStop: "Stop de referencia (2×ATR)", rShares: "Acciones", rRiskAmt: "Riesgo si el stop se ejecuta exactamente", rNotional: "Valor nominal", rBinding: "Límite activo", rRR: "Relación beneficio/riesgo a 3R",
  errorTitle: "No se pueden mostrar los datos",
  errorBody: "El snapshot de datos falta o no es válido. No se muestran precios inventados.",
  notFoundTitle: "Símbolo no encontrado",
  footer: "StockMind AI es una herramienta de investigación y análisis. No es asesoramiento de inversión personalizado ni garantiza resultados.",
  methodTitle: "Método y límites",
  methodBody: [
    "Los datos de esta demo son simulados y deterministas; los símbolos SIMA–SIME son ficticios.",
    "Los indicadores, estrategias, backtests y patrones los calculan los motores Python del repositorio, no un modelo de lenguaje.",
    "Un backtest simulado no predice resultados futuros. Las estrategias incluidas son reglas de manual sin ventaja demostrada.",
    "No hay datos reales de mercado, proveedor, base de datos ni inicio de sesión conectados todavía.",
  ],
} as const;

export type MessageKey = Exclude<keyof typeof es, "methodBody">;
type Dict = Record<MessageKey, string> & { methodBody: readonly string[] };

const en: Dict = {
  appName: "StockMind AI",
  navDashboard: "Dashboard",
  navMethod: "Method & limits",
  language: "Language",
  bannerSimulated: "DEMO MODE — SIMULATED DATA. Symbols are fictional. This is not market information or investment advice.",
  bannerDelayed: "DELAYED DATA",
  bannerLive: "LIVE DATA",
  dataAsOf: "Data as of",
  generated: "Generated",
  dashboardTitle: "Market dashboard (simulated)",
  dashboardIntro: "Output of the StockMind engines on deterministic simulated data. For reviewing the product, not for investment decisions.",
  colSymbol: "Symbol", colName: "Name", colClose: "Close", colChange: "1d chg", colRsi: "RSI 14", colSignals: "Signals today", colAction: "Analysis",
  open: "Open",
  signalsTitle: "Active signals",
  noSignalsToday: "No signals today. NO SIGNAL / INSUFFICIENT EVIDENCE: the system does not invent opportunities to fill the dashboard.",
  stockBack: "Back to dashboard",
  chartTitle: "Daily candlestick chart",
  chartAria: "Candlestick chart of {symbol}, {n} sessions",
  overlays: "Indicators", ema20: "EMA 20", ema50: "EMA 50", sma200: "SMA 200", bollinger: "Bollinger Bands", volume: "Volume", rsi: "RSI 14", macd: "MACD", entries: "Entry flags",
  signalsPanel: "Strategies and signals",
  strategy: "Strategy", version: "Version", result: "Result", noSignal: "NO SIGNAL", signal: "SIGNAL", supporting: "Supporting", contradicting: "Contradicting", reason: "Reason",
  backtestTitle: "Backtest (SIMULATED)",
  backtestNote: "Simulated result on simulated data. Not indicative of future performance. Fills at the next bar's open, with commissions and slippage.",
  mTotalReturn: "Total return", mBuyHold: "Buy & hold", mTrades: "Trades", mWinRate: "Win rate", mProfitFactor: "Profit factor", mMaxDd: "Max drawdown", mExposure: "Exposure", mSharpe: "Sharpe",
  undefinedMetric: "n/a",
  equityAria: "Simulated equity curve of {strategy}",
  tradesTitle: "Simulated trades", colEntry: "Entry", colExit: "Exit", colPnl: "P&L", colWhy: "Exit reason",
  patternsTitle: "Similar historical patterns",
  patternsNote: "Similarity is an uncalibrated distance, NOT a probability. Outcomes are descriptive statistics of past, correlated samples.",
  patternsEmpty: "No historical matches: INSUFFICIENT EVIDENCE.",
  pSample: "Matches", pMedian: "Median over {h} sessions", pPositive: "With positive return", pMfe: "Median MFE", pMae: "Median MAE", pWorstMae: "Worst MAE", pCi: "95% CI of the median",
  pNoCi: "No CI: sample too small (n < 30).",
  colSimilarity: "Similarity", colWindowEnd: "Window end", colFwd: "Forward return", colMfe: "MFE", colMae: "MAE",
  riskTitle: "Risk management example (illustrative)",
  riskNote: "Mechanical calculation on the last simulated close. Not a recommendation.",
  rEntry: "Reference entry", rStop: "Reference stop (2×ATR)", rShares: "Shares", rRiskAmt: "Risk if the stop fills exactly", rNotional: "Notional", rBinding: "Binding constraint", rRR: "Reward/risk at 3R",
  errorTitle: "Cannot display the data",
  errorBody: "The data snapshot is missing or invalid. No invented prices are shown.",
  notFoundTitle: "Symbol not found",
  footer: "StockMind AI is a research and analytics tool. It is not personalised investment advice and does not guarantee results.",
  methodTitle: "Method & limits",
  methodBody: [
    "The data in this demo is simulated and deterministic; symbols SIMA–SIME are fictional.",
    "Indicators, strategies, backtests and patterns are computed by the repository's Python engines, not by a language model.",
    "A simulated backtest does not predict future results. The included strategies are textbook rules with no demonstrated edge.",
    "No real market data, provider, database or login is connected yet.",
  ],
};

export const messages: Record<Locale, Dict> = { es, en };

export function t(locale: Locale, key: MessageKey, vars: Record<string, string | number> = {}): string {
  let s = messages[locale][key];
  for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, String(v));
  return s;
}
