# ADR-0009 Walk-forward / out-of-sample validation protocol
Decision: rolling train/test folds (test windows non-overlapping by default). Parameters are selected ONLY from the train window
(flags computed from train data alone, backtest on train bars, objective must have >= `min_train_trades`); the chosen parameters are
then evaluated on the next test window with flags computed from train+test history (causal) and a fresh flat backtest. Ties pick the
first candidate in sorted-key grid order. Folds with no eligible candidate are reported as skipped, never dropped silently. Pooled
statistics report OOS trades, win rate, pnl and chained (reinvested) return. Warnings are mandatory: in-sample selection bias with N
candidates, skipped folds, < 30 OOS trades, < 5 folds. `parameter_sensitivity` is explicitly in-sample (robustness landscape).
Tested by poisoning the test window (selection must not change), truncating future data, and mutation checks.
Not covered: purging/embargo for strategies whose labels span folds (not needed while trades never straddle folds), multiple-testing
corrections (deflated Sharpe / White's reality check), combinatorial purged CV, regime-conditional reporting, multi-symbol pooling.
