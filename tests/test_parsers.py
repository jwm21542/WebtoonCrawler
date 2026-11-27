"""Offline checks for the parser - no network needed.

    python -m tests.test_parsers        # from the repo root

tests/fixtures/ holds a trimmed copy of the live response captured on
2026-11-27: same markup/keys, long bodies shortened, neighbour items dropped.
"""
import importlib.util
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")

spec = importlib.util.spec_from_file_location("crawler", os.path.join(ROOT, "WebtoonCrawler.py"))
crawler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crawler)


def fixture(name: str) -> str:
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


class FakeFetcher:
    """Answers the crawler's reads from fixtures, keyed by URL fragment."""

    min_interval = 0.0
    verbose = False

    def __init__(self, routes):
        self.routes = routes

    def _pick(self, url: str):
        for fragment, payload in self.routes:
            if fragment in url:
                return payload
        raise AssertionError(f"FakeFetcher has no route for {url}")

    def get_text(self, url, **kwargs):
        payload = self._pick(url)
        assert isinstance(payload, str), url
        return payload

    def get_json(self, url, **kwargs):
        payload = self._pick(url)
        return json.loads(payload) if isinstance(payload, str) else payload

    def post_json(self, url, payload, **kwargs):
        return self.get_json(url)

    def close(self):
        pass


class WebtoonTests(unittest.TestCase):
    def setUp(self):
        self.fetcher = FakeFetcher([
            ("/list?title_no=95", fixture("webtoons_list.html")),
            ("/p/api/community/v2/posts", fixture("webtoons_comments.json")),
        ])

    def test_episode_list(self):
        title, episodes = crawler.list_episodes(
            self.fetcher, "https://www.webtoons.com/en/fantasy/tower-of-god/list?title_no=95")
        self.assertEqual(title, "Tower of God")
        self.assertTrue(episodes)
        self.assertEqual(episodes[0]["title_no"], 95)
        self.assertEqual(episodes[0]["url"].count("title_no="), 1)

    def test_comments(self):
        rows = crawler.crawl(
            series_urls=["https://www.webtoons.com/en/fantasy/tower-of-god/list?title_no=95"],
            episodes_per_series=1, fetcher=self.fetcher)
        self.assertEqual(len(rows), 2)
        row = rows[0]
        self.assertEqual(row["platform"], "WEBTOON")
        self.assertEqual(row["genre"], "webtoon")
        self.assertTrue(row["post_detail"])
        self.assertRegex(row["post_created_time"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        self.assertTrue(row["post_source"].endswith("title_no=95&episode_no=653"))
        self.assertTrue(row["post_id"])
        self.assertTrue(row["language"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
