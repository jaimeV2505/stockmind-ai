# ADR-0008 Backtest execution conventions (temporal correctness contract)
Decision: flags at bar t (computed from data up to the CLOSE of t) execute at the OPEN of t+1; last-bar flags are ignored.
Slippage is adverse on both legs and also applies to stop fills; gaps through a stop fill at the (worse) open; commissions are
fixed + bps on both legs; one long position at a time; exits beat same-bar entries (no flip); open positions are force-closed at
the last close with costs ("end_of_data"). Inputs must be pre-adjusted for splits/dividends and the adjustment is a REQUIRED,
recorded config field; corporate actions are not modelled. Every result carries `simulated=True` and a reproducibility hash
(config + data + flags). The engine guarantees EXECUTION timing only: it cannot detect look-ahead inside the caller's flags.
Consequences: conservative-by-construction fills; shorts, multi-symbol portfolios, intraday sessions/overnight gaps, partial fills,
borrow/financing costs, walk-forward splits and parameter sweeps are NOT implemented yet (see next-tasks).
