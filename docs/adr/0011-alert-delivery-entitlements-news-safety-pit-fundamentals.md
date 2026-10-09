# ADR-0011 Alert delivery semantics, entitlements, news safety, point-in-time fundamentals

## Alerts (`stockmind_alerts`)
- Rules are EDGE-triggered on the last completed bar (price/RSI crossings use prev<thr<=cur / prev>thr>=cur; volume spike is level-triggered but
  de-duplicated per bar). NaN/inf/insufficient data never fire.
- Event idempotency: `event_key = rule_id:bar_ts` (signals: signal.key). Delivery idempotency key = `event_key|channel`, handed to the sender on
  every attempt. Cooldown is evaluated AFTER idempotency and allows delivery exactly when `cooldown` has elapsed; a cooldown-suppressed event is not consumed.
- Delivery is AT-LEAST-ONCE: PENDING -> SENT | DEAD | SKIPPED. Exponential backoff (base x 2^(n-1), capped, deterministic +-10% jitter), `max_attempts`
  total tries, then dead-letter. `PermanentDeliveryError` skips retries. An unconfigured channel is SKIPPED visibly, never silently dropped and never blocks others.
  RESIDUAL RISK: a crash between a successful provider call and the status write can produce one duplicate; mitigated only if the provider honours the idempotency key.
- Quiet hours are wall-clock in the user's timezone (DST-aware, overnight windows, start inclusive / end exclusive); deferred, never dropped; in-app is exempt;
  a deferral does not consume a retry attempt.
- Persistence must mirror this with UNIQUE(event_key, channel) and a conditional status update (`WHERE status='PENDING'`).

## Entitlements (`stockmind_entitlements`)
- Fail closed: unknown plan/feature/limit => denied. Numbers are illustrative, NOT pricing. Role (authorisation) is separate from Plan (quota): Plan.ADMIN does not grant admin endpoints.
- `UsageMeter.try_consume` is check-and-increment on UTC days; the persisted version needs an atomic conditional UPDATE or it will race under concurrency.

## News safety (`stockmind_news`)
- URL canonicalisation rejects non-http(s), credentials, odd ports, internal/numeric hosts and non-global IPs. LEXICAL ONLY: a fetcher must also resolve DNS and
  re-check the IP at connect time (DNS rebinding is not detectable offline).
- Untrusted text is sanitised (entities decoded, markup/scripts stripped, hidden/bidi characters removed, delimiter forgery neutralised) and FLAGGED by
  heuristic patterns; flags do not block, they inform. Prompt injection cannot be fully prevented; the hard guarantee is on the OUTPUT side: only strict
  schema-valid JSON is accepted, tickers must come from our own association, sources must equal the supplied canonical URL, extra keys (e.g. an `action`) are rejected.
- Dedupe requires word-set AND word-order (bigram) agreement: bag-of-words alone merges opposite stories ("A sues B" / "B sues A") (found by mutation testing).
- No LLM is called anywhere in this repo yet.

## Fundamentals (`stockmind_fundamentals`)
- Facts carry period_end AND filed_at; queries see only filed_at <= ts (restatements invisible until filed). UNAVAILABLE != NOT_MEANINGFUL != a (possibly negative) value.
  P/E is never negative; unavailable components are excluded and listed, not scored as zero; < 50% available weight => no score.
- No ingestion exists (SEC EDGAR / FMP adapters need network and credentials).
