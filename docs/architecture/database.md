# Database (planned; no migrations written yet)
Global shared market data (candles, corporate actions, fundamentals, news) separated from tenant-owned data (watchlists,
portfolios, alert rules, notifications) which gets RLS. OHLCV table partitioned by time (+ symbol hash if needed).
Entity list: see MASTER_PROMPT section 16.
