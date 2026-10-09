"""Real-data pipeline contract (exercised with a SYNTHETIC Alpaca-shaped transport; the real service has never been called)."""
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("exporter", ROOT / "scripts" / "export_demo_snapshot.py")
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)
from stockmind_marketdata import AlpacaDailyBars  # noqa: E402

UTC = timezone.utc


def run(argv, env=None, provider_factory=None):
    buf = io.StringIO()
    env = {} if env is None else env
    ctx = [mock.patch.dict("os.environ", env, clear=True)]
    if provider_factory:
        ctx.append(mock.patch.object(exporter, "AlpacaDailyBars", provider_factory))
    for c in ctx:
        c.start()
    try:
        with redirect_stdout(buf):
            code = exporter.main(argv)
    finally:
        for c in ctx:
            c.stop()
    return code, buf.getvalue()


class TestMarketExport(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.out = self.tmp / "snap.json"

    def test_fake_pipeline_produces_a_labelled_delayed_snapshot_and_excludes_bad_symbols(self):
        code, _ = run(["--source", "market", "--fake-market", "--out", str(self.out)])
        self.assertEqual(code, 0)
        d = json.loads(self.out.read_text())
        m = d["meta"]
        self.assertEqual((m["mode"], m["symbols_are_fictional"], m["feed"], m["adjustment"]), ("delayed", False, "iex", "split"))
        self.assertEqual(m["data_source"], "fake-alpaca-dev")                       # a synthetic run can never pass as real
        self.assertIn("NOT market data", m["note"])
        self.assertEqual([e["symbol"] for e in m["excluded"]], ["GAPX"])
        self.assertIn("data-quality gate failed", m["excluded"][0]["reason"])
        self.assertEqual([s["symbol"] for s in d["symbols"]], ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"])
        self.assertEqual({s["name"] for s in d["symbols"]}, {"SPDR S&P 500 ETF Trust", "Invesco QQQ Trust", "NVIDIA Corporation", "Apple Inc.", "Microsoft Corporation"})
        for s in d["symbols"]:
            self.assertEqual(len(s["candles"]), 252)
            self.assertEqual(s["exchange"], "US")
            self.assertFalse(s["symbol"].startswith("SIM"))
            self.assertEqual({b["config"]["price_adjustment"] for b in s["backtests"]}, {"split-adjusted (alpaca-iex)"})
            self.assertTrue(all(b["simulated"] for b in s["backtests"]))
        text = self.out.read_text()
        self.assertNotIn("NaN", text)
        self.assertNotIn("demo-simulated", text)

    def test_fake_output_into_the_real_data_directory_is_refused(self):
        target = ROOT / "apps" / "web" / "data" / "market-snapshot.json"
        existed = target.exists()
        code, out = run(["--source", "market", "--fake-market", "--out", str(target)])
        self.assertEqual(code, 2)
        self.assertEqual(target.exists(), existed)
        code, _ = run(["--source", "market", "--fake-market"])                  # no --out at all
        self.assertEqual(code, 2)

    def test_missing_credentials_fail_loudly_and_write_nothing(self):
        code, out = run(["--source", "market", "--out", str(self.out)], env={})
        self.assertEqual(code, 2)
        self.assertIn("credentials missing", out)
        self.assertFalse(self.out.exists())

    def test_rejected_credentials_and_outage_have_distinct_exit_codes_and_write_nothing(self):
        def factory_with(status):
            def make(key, secret, feed="iex", **kw):
                return AlpacaDailyBars(key, secret, feed=feed, transport=lambda u, h: (status, {}, b"{}"), sleep=lambda s: None, max_retries=1)
            return make
        env = {"ALPACA_API_KEY": "k", "ALPACA_API_SECRET": "s"}
        code, out = run(["--source", "market", "--symbols", "SPY", "--out", str(self.out)], env, factory_with(401))
        self.assertEqual((code, self.out.exists()), (2, False))
        self.assertIn("credentials", out)
        code, out = run(["--source", "market", "--symbols", "SPY", "--out", str(self.out)], env, factory_with(503))
        self.assertEqual((code, self.out.exists()), (3, False))
        self.assertIn("unavailable", out)

    def test_if_no_symbol_passes_the_quality_gate_nothing_is_written(self):
        def empty(key, secret, feed="iex", **kw):
            return AlpacaDailyBars(key, secret, feed=feed, transport=lambda u, h: (200, {}, b'{"bars": null, "symbol": "SPY"}'), sleep=lambda s: None)
        code, out = run(["--source", "market", "--symbols", "SPY", "--out", str(self.out)], {"ALPACA_API_KEY": "k", "ALPACA_API_SECRET": "s"}, empty)
        self.assertEqual((code, self.out.exists()), (1, False))
        self.assertIn("no symbol passed", out)

    def test_unknown_symbols_get_no_invented_company_name(self):
        code, _ = run(["--source", "market", "--fake-market", "--symbols", "SPY,ZZTOP", "--out", str(self.out)])
        self.assertEqual(code, 0)
        names = {s["symbol"]: s["name"] for s in json.loads(self.out.read_text())["symbols"]}
        self.assertEqual(names.get("ZZTOP"), "ZZTOP")

    def test_check_flag_is_demo_only(self):
        self.assertEqual(run(["--source", "market", "--check"])[0], 2)


if __name__ == "__main__":
    unittest.main()
