# Data flow (target; not yet implemented except the Candle model and DemoProvider)
Provider adapter -> normalise to `Candle` (UTC, provenance fields) -> quality validation -> idempotent upsert keyed by `Candle.key`
-> shared market tables -> indicator/signal workers (deterministic) -> signals + evidence -> alerts/UI.
LLMs sit only on the explanation side (news summaries, signal narratives) and receive structured, validated inputs.
