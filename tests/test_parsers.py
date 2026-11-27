"""Offline checks for the parser - no network needed.

    python -m tests.test_parsers        # from the repo root

tests/fixtures/ holds a trimmed copy of the live response captured on
2026-11-27: same markup/keys, long bodies shortened, neighbour items dropped.
"""
import datetime as dt
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


NOW = dt.datetime(2026, 11, 28, 1, 26, tzinfo=dt.timezone.utc)  # 2026-11-28 10:26 KST


class DateWindowTests(unittest.TestCase):
    """--days / --since / --until, offline."""

    def test_parse_date_arg(self):
        self.assertEqual(crawler.parse_date_arg("2026-11-21"), "2026-11-21 00:00:00")
        self.assertEqual(crawler.parse_date_arg("2026-11-21", end_of_day=True),
                         "2026-11-21 23:59:59")
        self.assertEqual(crawler.parse_date_arg("2026-11-21 09:30"), "2026-11-21 09:30:00")
        self.assertEqual(crawler.parse_date_arg("2026-11-21T09:30:45"), "2026-11-21 09:30:45")
        self.assertEqual(crawler.parse_date_arg(""), "")
        self.assertEqual(crawler.parse_date_arg(None), "")
        with self.assertRaises(ValueError):
            crawler.parse_date_arg("21/11/2026")

    def test_days_window(self):
        week = crawler.build_window(days=7, now=NOW)
        self.assertEqual(week.since, "2026-11-21 00:00:00")
        self.assertEqual(week.until, "")
        self.assertTrue(week.active)
        self.assertEqual(crawler.build_window(days=30, now=NOW).since, "2026-10-29 00:00:00")
        self.assertFalse(crawler.build_window(now=NOW).active)

    def test_boundaries_are_inclusive(self):
        window = crawler.build_window(since="2026-11-21", until="2026-11-27")
        self.assertTrue(window.contains("2026-11-21 00:00:00"))
        self.assertTrue(window.contains("2026-11-27 23:59:59"))
        self.assertFalse(window.contains("2026-11-20 23:59:59"))
        self.assertFalse(window.contains("2026-11-28 00:00:00"))

    def test_undated_rows_kept_unless_strict(self):
        self.assertTrue(crawler.build_window(days=7, now=NOW).contains(""))
        self.assertFalse(crawler.build_window(days=7, now=NOW, strict=True).contains(""))

    def test_filter_rows(self):
        rows = [{"post_created_time": "2026-11-27 10:00:00"},
                {"post_created_time": "2026-10-01 10:00:00"},
                {"post_created_time": ""}]
        week = crawler.build_window(days=7, now=NOW)
        self.assertEqual(len(crawler.filter_rows(rows, week)), 2)
        self.assertEqual(len(crawler.filter_rows(rows)), 3)

    def test_crossed_window_needs_a_run_of_older_items(self):
        week = crawler.build_window(days=7, now=NOW)
        older, newer = "2026-01-01 00:00:00", "2026-11-27 00:00:00"
        # one pinned or out-of-order old item must not end a newest-first listing
        self.assertFalse(crawler.crossed_window([older, newer, newer], week))
        self.assertTrue(crawler.crossed_window([newer, older, older, older], week))
        self.assertFalse(crawler.crossed_window([older, older], week, buffer=3))
        # undated items neither count nor reset the run
        self.assertFalse(crawler.crossed_window(["", older, "", older], week))
        # a window without --since can never stop pagination
        self.assertFalse(crawler.crossed_window([older] * 5,
                                               crawler.build_window(until="2026-11-27")))

    def test_cli_flags(self):
        args = crawler.build_parser().parse_args(["--days", "7"])
        self.assertEqual(crawler.window_from_args(args, now=NOW).since, "2026-11-21 00:00:00")
        args = crawler.build_parser().parse_args(["--since", "2026-10-01", "--until", "2026-10-31"])
        window = crawler.window_from_args(args, now=NOW)
        self.assertEqual((window.since, window.until),
                         ("2026-10-01 00:00:00", "2026-10-31 23:59:59"))
        args = crawler.build_parser().parse_args(["--days", "30", "--drop-undated"])
        self.assertTrue(crawler.window_from_args(args, now=NOW).strict)
        with self.assertRaises(SystemExit):
            crawler.build_parser().parse_args(["--days", "7", "--since", "2026-10-01"])



class DateFilterCrawlTests(unittest.TestCase):
    SERIES = "https://www.webtoons.com/en/fantasy/tower-of-god/list?title_no=95"

    class CountingFetcher(FakeFetcher):
        def __init__(self, routes):
            super().__init__(routes)
            self.calls = []

        def _pick(self, url):
            self.calls.append(url)
            return super()._pick(url)

    def fetcher(self):
        return self.CountingFetcher([
            ("/list?title_no=95", fixture("webtoons_list.html")),
            ("/p/api/community/v2/posts", fixture("webtoons_comments.json")),
        ])

    def test_window_keeps_matching_rows(self):
        # comments in the fixture are 2026-11-26; the episode itself is Feb 2025
        rows = crawler.crawl(series_urls=[self.SERIES], episodes_per_series=1,
                             fetcher=self.fetcher(),
                             window=crawler.build_window(since="2025-01-01"))
        self.assertEqual(len(rows), 2)

    def test_window_outside_everything_collects_nothing(self):
        rows = crawler.crawl(series_urls=[self.SERIES], episodes_per_series=1,
                             fetcher=self.fetcher(),
                             window=crawler.build_window(since="2027-01-01"))
        self.assertEqual(rows, [])

    def test_days_7_skips_the_older_episode_without_calling_the_api(self):
        fetcher = self.fetcher()
        rows = crawler.crawl(series_urls=[self.SERIES], episodes_per_series=1,
                             fetcher=fetcher, window=crawler.build_window(days=7, now=NOW))
        self.assertEqual(rows, [])
        self.assertFalse([url for url in fetcher.calls if "/p/api/community" in url],
                         "an episode older than --since should not have its comments fetched")


if __name__ == "__main__":
    unittest.main(verbosity=2)
