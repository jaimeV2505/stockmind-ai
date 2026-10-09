# ADR-0010 Historical pattern similarity engine
Decision: trend shape = (log price - first log price) / std(log returns): invariant to price scale and volatility. Optional volume
component (z-scored log volume x weight). Euclidean prefilter, then DTW (|x-y| cost, optional Sakoe-Chiba band, normalised by n+m) on
the survivors; deterministic ordering (distance, symbol, end index). Forward outcomes (return, MFE, MAE) are computed at index time
but a candidate is eligible only if its outcome end <= query as_of; own-symbol candidates must finish before the query window
starts; per-symbol minimum separation (default = window) limits overlapping-sample inflation; regime = close vs causal SMA50.
`summarize` reports descriptive statistics (median, quantiles, share_positive, MFE/MAE) with a seeded bootstrap CI for the median only
when n >= 30, mandatory disclaimer notes, and an explicit INSUFFICIENT EVIDENCE for zero matches. Similarity = 1/(1+distance) is an
uncalibrated transform and must never be shown as a probability.
Known limits: survivorship bias depends on the symbols supplied; matches from the same period are cross-sectionally correlated;
no transaction costs in forward returns; DTW is O(window^2) per candidate in pure Python (fine for 10^3-10^4 candidates after the
prefilter; use a vector index/pgvector or numba for larger universes); no adjustment for corporate actions (caller supplies adjusted prices).
