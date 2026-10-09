# ADR-0006 Swing pivots are reported on their confirmation bar
Decision: `swing_points(k)` emits a pivot at bar i+k (when it becomes knowable) with `*_bars_ago = k`; ties form no pivot.
Rationale: reporting at bar i is look-ahead and silently inflates backtests/similarity results. Consumers (support/resistance,
break-of-structure, pattern detectors) must use the confirmation bar for decisions and may only use `bars_ago` for plotting.
Same rule applies to future indicators: Ichimoku's lagging span (chikou) and any centred window are look-ahead by construction
and must be exposed as plot-only fields or omitted from signal logic.
Testing rule: causality tests truncate at many cut points (a single cut missed a planted look-ahead; found by mutation test).
