# ADR-0004 Simulated data is explicit and never a silent fallback
Decision: `DataMode.SIMULATED` + mandatory `-simulated` source suffix enforced in `Candle`; quality validation flags mixed
modes; live mode must fail loudly on provider outage. Rationale: prevents fabricated signals from being shown as real.
