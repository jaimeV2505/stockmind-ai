# ADR-0014 Public repository: provider data never enters git; build and deploy from Actions
Supersedes the "commit market-snapshot.json to a private repo" part of ADR-0013. Context: the repository is public and Alpaca does not permit redistributing its data.
Decision: the market snapshot is produced on the Actions runner, baked into a Vercel prebuilt build and deployed with the Vercel CLI; it is git-ignored, never committed,
never uploaded as an artifact/cache, and removed from the runner. Git-triggered Vercel deployments of `main` are disabled (`apps/web/vercel.json`) because such a build would
have no data file; production is deployed only by the workflow. Fail-closed access control (ADR-0013) stays: market mode requires a strong SITE_PASSWORD, verified both at run
time (middleware 503) and before building (workflow policy step). The policy is machine-enforced by `tests/integration/test_repo_policy.py` (11 planted violations caught).
Consequences: code pushes do not auto-deploy; the workflow needs 5 secrets and a Vercel token with deploy rights; log text is public so the exporter prints no data; static pages
are generated at build time (`dynamicParams=false` on stock pages) so the deployed functions never need the data file at runtime.
Residual risks: the Vercel CLI invocation sequence is unverified here; the Vercel deployment URL and the repo being public reveal that the project exists and the universe
(config/universe.json) but no market data; Basic auth protects display, not the Vercel build output from the token holder.
