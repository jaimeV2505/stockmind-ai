"""Repository policy: provider market data must never enter this (PUBLIC) repository. Alpaca does not allow redistributing its data."""
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "market-data.yml"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def in_git_repo() -> bool:
    return git("rev-parse", "--is-inside-work-tree").stdout.strip() == "true"


class TestNoProviderDataInGit(unittest.TestCase):
    @unittest.skipUnless(in_git_repo(), "not a git checkout")
    def test_market_snapshots_are_ignored_and_untracked(self):
        for name in ("market-snapshot.json", "market-snapshot.local.json", "market-snapshot-2026.json"):
            self.assertEqual(git("check-ignore", "-q", f"apps/web/data/{name}").returncode, 0, f"{name} must be git-ignored")
        self.assertEqual(git("ls-files", "apps/web/data/market-snapshot*").stdout.strip(), "")
        tracked = set(git("ls-files", "apps/web/data").stdout.split())
        self.assertEqual(tracked, {"apps/web/data/demo-snapshot.json"}, "only the SIMULATED snapshot may be tracked")

    @unittest.skipUnless(in_git_repo(), "not a git checkout")
    def test_nothing_data_like_is_tracked_outside_the_demo_snapshot(self):
        offenders = [f for f in git("ls-files").stdout.split() if re.search(r"(snapshot|bars|candles|ohlc).*\.(json|csv|parquet)$", f, re.I)
                     and f != "apps/web/data/demo-snapshot.json"]
        self.assertEqual(offenders, [])

    def test_the_data_workflow_cannot_publish_data(self):
        text = WORKFLOW.read_text()
        code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
        for forbidden in (r"\bgit\s+push\b", r"\bgit\s+commit\b", r"\bgit\s+add\b", r"upload-artifact", r"download-artifact", r"actions/cache", r"gh\s+release", r"\bgh\s+pr\b", r"git\s+tag\b"):
            self.assertIsNone(re.search(forbidden, code), f"workflow must not contain {forbidden}")
        self.assertIn("check-ignore", code)                                   # it verifies the policy itself at run time
        self.assertIn("contents: read", code)                                 # token cannot write to the repo
        self.assertNotRegex(code, r"contents:\s*write")
        self.assertIn("rm -f apps/web/data/market-snapshot", code)            # cleanup of the runner
        for secret in ("ALPACA_API_KEY", "ALPACA_API_SECRET", "VERCEL_TOKEN", "VERCEL_ORG_ID", "VERCEL_PROJECT_ID"):
            self.assertIn(f"secrets.{secret}", code)
        self.assertNotRegex(code, r"(?i)pull_request|push:\s*$|\bon:\s*\[?push")   # only schedule / manual: a PR can never trigger it

    def test_secrets_are_never_echoed(self):
        code = WORKFLOW.read_text()
        self.assertIsNone(re.search(r"echo[^\n]*\$\{?\{?\s*(secrets\.|ALPACA|VERCEL_TOKEN|SITE_PASSWORD)", code))
        self.assertIsNone(re.search(r"(?m)^\s*(set -x|.*\bcat\b[^\n]*\.env)", code))

    def test_vercel_only_deploys_from_the_data_workflow(self):
        cfg = json.loads((ROOT / "apps" / "web" / "vercel.json").read_text())
        self.assertIs(cfg["git"]["deploymentEnabled"]["main"], False)

    def test_deployed_market_site_is_password_protected_by_construction(self):
        text = WORKFLOW.read_text()
        self.assertIn("SITE_PASSWORD", text)
        self.assertIn("STOCKMIND_DATA", text)
        self.assertLess(text.index("Policy - the deployment must be password protected"), text.index("vercel build"))   # checked BEFORE building/deploying

    def test_env_example_contains_no_real_looking_secrets(self):
        for line in (ROOT / ".env.example").read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                if re.search(r"KEY|SECRET|TOKEN|PASSWORD", k):
                    self.assertEqual(v.strip(), "", f"{k} must be blank in .env.example")


if __name__ == "__main__":
    unittest.main()
