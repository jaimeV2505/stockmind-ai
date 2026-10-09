# ADR-0007 Strict validation at the Candle boundary; reject, never silently repair
Decision: `Candle` rejects non-finite/non-numeric prices, malformed symbol/currency/exchange/source, naive or non-UTC timestamps,
and ingestion earlier than open. Adapters normalise (upper-case symbols, UTC, session-open stamps for 1d) before constructing.
`validate_series` is per-symbol/exchange/timeframe and reports (not repairs) gaps, forming bars, misaligned stamps, mixed
provenance. Indicators propagate NaN (fail closed) and never skip bars. Rationale: silent repair hides provider faults and creates
fabricated or look-ahead data (audit H-1..H-7). Consequence: adapters carry the normalisation burden; a gap-repair policy
(re-seed vs refuse) is still undecided (audit M-6).
