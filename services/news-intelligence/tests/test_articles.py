import random
import unittest
from datetime import datetime, timedelta, timezone

from stockmind_news import Article, associate, canonical_url, classify_events, dedupe

UTC = timezone.utc
T = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


def art(title="NVIDIA beats earnings expectations", source="Reuters", url="https://www.reuters.com/markets/nvda-earnings",
        published=T, body="", hint=(), ingest_delay=timedelta(minutes=5)):
    return Article(title, source, url, published, published + ingest_delay, body, tuple(hint))


class TestCanonicalUrl(unittest.TestCase):
    def test_normalisation(self):
        variants = ["HTTPS://WWW.Reuters.com/markets/nvda-earnings/?utm_source=x&utm_medium=y#frag",
                    "https://www.reuters.com//markets//nvda-earnings/", "https://www.reuters.com:443/markets/nvda-earnings?fbclid=abc",
                    "https://www.reuters.com./markets/nvda-earnings"]
        self.assertEqual({canonical_url(v) for v in variants}, {"https://www.reuters.com/markets/nvda-earnings"})
        self.assertEqual(canonical_url("https://a.com/p?b=2&a=1&utm_x=9"), "https://a.com/p?a=1&b=2")
        self.assertEqual(canonical_url("https://a.com"), "https://a.com/")
        self.assertNotEqual(canonical_url("https://a.com/p?id=1"), canonical_url("https://a.com/p?id=2"))   # real params kept

    def test_ssrf_style_and_garbage_rejected(self):
        bad = ["file:///etc/passwd", "javascript:alert(1)", "ftp://a.com/x", "http://127.0.0.1/", "http://[::1]/", "http://10.0.0.5/",
               "http://192.168.1.1/", "http://169.254.169.254/latest/meta-data", "http://localhost/", "http://localhost.localdomain.internal/",
               "http://db.corp/x", "http://user:pw@example.com/", "http://2130706433/", "http://0x7f.0.0.1/", "http://example.com:8080/",
               "http://intranet/", "", "   ", "http://", "https://a.com/" + "x" * 3000, "http://[::ffff:127.0.0.1]/", "http://100.64.0.1/"]
        for u in bad:
            with self.subTest(u=u[:60]), self.assertRaises(ValueError):
                canonical_url(u)

    def test_public_ips_allowed(self):
        self.assertEqual(canonical_url("http://8.8.8.8/x"), "http://8.8.8.8/x")


class TestArticle(unittest.TestCase):
    def test_times_and_attribution_validated(self):
        with self.assertRaises(ValueError):
            Article("t", "s", "https://a.com/x", T, T - timedelta(seconds=1))                 # ingested before published
        with self.assertRaises(ValueError):
            Article("t", "s", "https://a.com/x", datetime(2026, 1, 1), T)                     # naive
        with self.assertRaises(ValueError):
            Article("  ", "s", "https://a.com/x", T, T)
        with self.assertRaises(ValueError):
            Article("t", "", "https://a.com/x", T, T)
        with self.assertRaises(ValueError):
            Article("t", "s", "http://127.0.0.1/x", T, T)

    def test_publication_and_ingestion_times_kept_distinct(self):
        a = art(ingest_delay=timedelta(hours=3))
        self.assertEqual(a.ingested_at - a.published_at, timedelta(hours=3))
        self.assertEqual(art().id, art(url="https://www.reuters.com/markets/nvda-earnings?utm_source=z").id)


class TestDedupe(unittest.TestCase):
    def test_same_url_and_syndicated_titles(self):
        a = art()
        b = art(source="Yahoo", url="https://finance.yahoo.com/news/abc", title="NVIDIA Beats Earnings Expectations!", published=T + timedelta(hours=2))
        c = art(url="https://www.reuters.com/markets/nvda-earnings?utm_campaign=x", published=T + timedelta(hours=1))
        d = art(title="Apple unveils new iPhone lineup", url="https://x.com/apple")
        r = dedupe([a, b, c, d])
        self.assertEqual({k.title for k in r.kept}, {a.title, d.title})
        self.assertEqual(r.duplicates, {b.id: a.id, c.id: a.id})
        self.assertEqual(r.also_reported_by[a.id], ("Yahoo",))          # attribution of syndicated copies preserved

    def test_window_and_short_titles(self):
        a, b = art(), art(url="https://other.com/n", published=T + timedelta(hours=49))
        self.assertEqual(len(dedupe([a, b]).kept), 2)                                        # identical title, 49h apart: separate stories
        s1, s2 = art(title="NVDA up", url="https://a.com/1"), art(title="NVDA down", url="https://a.com/2")
        self.assertEqual(len(dedupe([s1, s2]).kept), 2)                                      # short, different titles never merged
        self.assertEqual(len(dedupe([s1, art(title="nvda UP!", url="https://a.com/3")]).kept), 1)

    def test_similar_but_different_stories_not_merged(self):
        a = art(title="Apple to acquire AI startup for $2 billion", url="https://a.com/1")
        b = art(title="Apple to acquire AI startup for $2 billion", url="https://a.com/2", published=T + timedelta(hours=1))
        c = art(title="Apple faces antitrust probe over App Store fees", url="https://a.com/3")
        self.assertEqual(len(dedupe([a, b, c]).kept), 2)

    def test_word_order_matters_opposite_stories_are_not_merged(self):
        short = [art(title="Apple sues Google", url="https://a.com/1"), art(title="Google sues Apple", url="https://a.com/2")]
        long_ = [art(title="Apple sues Google over search patents", url="https://a.com/3"),
                 art(title="Google sues Apple over search patents", url="https://a.com/4")]
        self.assertEqual(len(dedupe(short).kept), 2)
        self.assertEqual(len(dedupe(long_).kept), 2)
        suffixed = [art(title="NVIDIA beats earnings expectations", url="https://a.com/5"),
                    art(title="NVIDIA beats earnings expectations - Reuters", url="https://b.com/6")]
        self.assertEqual(len(dedupe(suffixed).kept), 1)                                      # harmless suffix still merges

    def test_input_order_does_not_matter(self):
        items = [art(url=f"https://s.com/{i}", title=t, published=T + timedelta(minutes=i * 7), source=f"S{i}")
                 for i, t in enumerate(["NVIDIA beats earnings expectations", "Nvidia beats earnings expectations!", "Tesla recalls vehicles in Europe",
                                        "Tesla recalls vehicles in europe", "Fed holds rates steady", "Oil prices fall sharply on supply news"])]
        base = dedupe(items)
        for seed in range(5):
            random.Random(seed).shuffle(items)
            r = dedupe(items)
            self.assertEqual((r.kept, r.duplicates, r.also_reported_by), (base.kept, base.duplicates, base.also_reported_by))


class TestAssociate(unittest.TestCase):
    UNIVERSE = {"NVDA": ["NVIDIA", "Nvidia Corporation"], "AAPL": ["Apple Inc"], "A": ["Agilent Technologies"], "IT": ["Gartner"],
                "BRK.B": ["Berkshire Hathaway"]}

    def test_cashtag_hint_alias_precedence_and_sorting(self):
        a = art(title="$NVDA surges as NVIDIA reports; Apple Inc watches", body="Analysts at Berkshire Hathaway also commented.", hint=("AAPL",))
        m = {x.symbol: x for x in associate(a, self.UNIVERSE)}
        self.assertEqual({s: x.via for s, x in m.items()}, {"NVDA": "cashtag", "AAPL": "hint", "BRK.B": "alias"})
        self.assertEqual([x.symbol for x in associate(a, self.UNIVERSE)], sorted(m))

    def test_no_false_positives(self):
        a = art(title="IT spending rises as A new report shows Applebee's gains", body="$nvda mention in lowercase; $ZZZZ unknown; price $NVDAX",
                hint=("TSLA",))
        self.assertEqual(associate(a, self.UNIVERSE), [])      # bare 'IT'/'A', lowercase cashtag, unknown symbols, 'Applebee's' != Apple

    def test_alias_word_boundaries(self):
        self.assertEqual([m.symbol for m in associate(art(title="Pineapple Inc earnings"), self.UNIVERSE)], [])
        self.assertEqual([m.symbol for m in associate(art(title="apple inc raises guidance"), self.UNIVERSE)], ["AAPL"])


class TestEvents(unittest.TestCase):
    def test_labels(self):
        a = art(title="NVIDIA reports Q3 results, CEO announces new GPU launch", body="The SEC is also reviewing the Fed commentary.")
        self.assertEqual(classify_events(a), ("earnings", "executive_change", "macro", "product", "regulatory"))
        self.assertEqual(classify_events(art(title="Company opens new cafe")), ())


if __name__ == "__main__":
    unittest.main()
