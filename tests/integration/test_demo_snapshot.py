"""The committed web snapshot must be (a) strict JSON, (b) labelled simulated, (c) reproducible from the engines in this repo."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAP = ROOT / "apps" / "web" / "data" / "demo-snapshot.json"


def load_exporter():
    spec = importlib.util.spec_from_file_location("export_demo_snapshot", ROOT / "scripts" / "export_demo_snapshot.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestDemoSnapshot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SNAP.read_text()
        cls.data = json.loads(cls.text)
        cls.mod = load_exporter()

    def test_strict_json_and_labels(self):
        for bad in ("NaN", "Infinity"):
            self.assertNotIn(bad, self.text)
        self.assertEqual(self.data["meta"]["mode"], "simulated")
        self.assertTrue(self.data["meta"]["symbols_are_fictional"])
        self.assertEqual(self.data["meta"]["data_source"], "demo-simulated")
        for s in self.data["symbols"]:
            self.assertTrue(s["symbol"].startswith("SIM"))
            for b in s["backtests"]:
                self.assertIs(b["simulated"], True)
            self.assertEqual(len(s["candles"]), self.data["meta"]["bars_shown"])

    def test_reproducible_from_the_engines(self):
        fresh = json.loads(self.mod.dumps(self.mod.build()))
        self.assertTrue(self.mod._close(self.data, fresh), "committed snapshot differs from a fresh export: run scripts/export_demo_snapshot.py")

    def test_export_is_deterministic_run_to_run(self):
        self.assertEqual(self.mod.dumps(self.mod.build()), self.mod.dumps(self.mod.build()))

    def test_cross_checks_against_engines(self):
        s = self.data["symbols"][0]
        c = s["candles"]
        for x in c:
            self.assertTrue(x["h"] >= max(x["o"], x["c"], x["l"]) and x["l"] <= min(x["o"], x["c"], x["h"]))
        r = s["risk_example"]
        self.assertAlmostEqual(r["entry"], c[-1]["c"], places=3)
        self.assertLess(r["stop"], r["entry"])
        self.assertLessEqual(r["risk_amount"], r["equity"] * r["risk_fraction"] + 1e-6)
        for b in s["backtests"]:
            self.assertEqual(len(b["equity"]), len(c))
            self.assertAlmostEqual(sum(t["pnl"] for t in b["trades"]), b["equity"][-1] - b["config"]["initial_capital"], delta=0.05 * max(1, len(b["trades"])))


if __name__ == "__main__":
    unittest.main()
