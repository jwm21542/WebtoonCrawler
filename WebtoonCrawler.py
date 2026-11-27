"""WEBTOON (webtoons.com, English/global) - episode comments.

Verified live 2026-11-27 (plain ``requests``, no login, no cookie):

    GET https://www.webtoons.com/p/api/community/v2/posts
        ?pageId=w_<titleNo>_<episodeNo>&pageSize=30&cursor=<pagination.next>
        headers: Language: en | Platform: WEB_PC | Service-Ticket-Id: epicom

Returns JSON: ``body`` (comment text), ``bodyLanguage``, ``createdBy.name``,
``createdAt`` (epoch ms), ``childPostCount``, ``id`` and ``pagination.next`` for
the next page (the cursor query parameter is ``cursor``; ``next`` only echoes).
Replies live at ``/v2/post/<id>/child-posts``.

``post_like`` is left blank on purpose: the public comment API returns the
``reactions`` array without counts for signed-out visitors (only the viewer's
own reaction), so there is no honest like number to record.

This file is self-contained on purpose (same layout as the other *Crawler repos in
this account): the HTTP layer and the CSV schema helpers live below the crawler, so the
script runs with nothing but `requests` + `beautifulsoup4` installed.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import random
import re
import sys
import time
import urllib.parse
from typing import Any, Iterable

import requests
# ---------------------------------------------------------------------------
# HTTP layer (shared by the *Crawler repos)
# ---------------------------------------------------------------------------
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_UA,
    # No "br": we ask only for encodings `requests` can decode itself.
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class FetchError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, url: str = ""):
        super().__init__(message)
        self.status = status
        self.url = url


class Fetcher:
    """Session wrapper with per-host spacing, retries and readable errors."""

    def __init__(
        self,
        headers: dict[str, str] | None = None,
        min_interval: float = 0.8,
        retries: int = 3,
        timeout: float = 30.0,
        verbose: bool = True,
    ):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        if headers:
            self.session.headers.update(headers)
        self.min_interval = min_interval
        self.retries = retries
        self.timeout = timeout
        self.verbose = verbose
        self._last: dict[str, float] = {}

    # -- politeness ----------------------------------------------------
    def _wait(self, host: str) -> None:
        last = self._last.get(host)
        if last is None:
            return
        gap = time.time() - last
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap + random.uniform(0, 0.2))

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"    {msg}")

    # -- requests ------------------------------------------------------
    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        host = urllib.parse.urlsplit(url).netloc
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("allow_redirects", True)
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            self._wait(host)
            try:
                resp = self.session.request(method, url, **kwargs)
                self._last[host] = time.time()
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                    backoff = 1.5 * attempt + random.uniform(0, 1)
                    self._log(f"HTTP {resp.status_code} on {url} - retry {attempt} in {backoff:.1f}s")
                    time.sleep(backoff)
                    continue
                if resp.status_code >= 400:
                    raise FetchError(
                        f"HTTP {resp.status_code} for {method} {url}", resp.status_code, url
                    )
                return resp
            except requests.RequestException as exc:  # network error
                last_error = exc
                self._last[host] = time.time()
                if attempt < self.retries:
                    backoff = 1.5 * attempt + random.uniform(0, 1)
                    self._log(f"network error ({type(exc).__name__}) - retry {attempt} in {backoff:.1f}s")
                    time.sleep(backoff)
                    continue
        raise FetchError(f"gave up on {method} {url}: {last_error}", None, url)

    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def get_text(self, url: str, **kwargs) -> str:
        resp = self.get(url, **kwargs)
        if not resp.encoding or resp.encoding.lower() in ("iso-8859-1",):
            resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    def get_json(self, url: str, **kwargs) -> Any:
        return self.get(url, **kwargs).json()

    def post_json(self, url: str, payload: dict, **kwargs) -> Any:
        kwargs.setdefault("json", payload)
        resp = self.request("POST", url, **kwargs)
        return resp.json()

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "Fetcher":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def soup(html: str):
    """BeautifulSoup with lxml, falling back to the stdlib parser."""
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "lxml")


# ---------------------------------------------------------------------------
# CSV schema (shared by the *Crawler repos)
# ---------------------------------------------------------------------------
FIELDS = [
    "post_detail",
    "platform",
    "post_like",
    "post_created_time",
    "post_source",
    "genre",
    "author",
    "title",
    "topic",
    "language",
    "post_id",
]

TZ_UTC = dt.timezone.utc


def utc_time(ts: float | int | None) -> str:
    """Epoch seconds/milliseconds -> 'YYYY-MM-DD HH:MM:SS' (UTC)."""
    if ts in (None, ""):
        return ""
    ts = float(ts)
    if ts > 1e11:  # milliseconds
        ts /= 1000.0
    return dt.datetime.fromtimestamp(ts, TZ_UTC).strftime("%Y-%m-%d %H:%M:%S")


_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

_DATE_PATTERNS = [
    # 2026-11-26 13:15:04 / 2026-11-26T05:05:06+09:00
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?"), "ymdhms"),
    # 2026-11-26
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"), "ymd"),
    # Nov 10, 2026 / Apr  1, 2025
    (re.compile(r"^([A-Za-z]{3})[a-z]*\s+(\d{1,2}),\s*(\d{4})$"), "mdy"),
    # 4y / 2y / Jul 8 / 14시간 전 style relatives -> left blank
]


def loose_datetime(text: str | None) -> str:
    """Parse the date strings the sites actually print into UTC 'YYYY-MM-DD HH:MM:SS'.

    Absolute dates are taken as UTC when no zone is given (the sites print the
    viewer's zone, so the value is a date-level approximation, never a lie about
    the day). Relative labels ("2y", "14시간 전") return "" - callers keep the raw
    label in ``title``/``topic`` instead of inventing a timestamp.
    """
    if not text:
        return ""
    text = re.sub(r"\s+", " ", str(text)).strip()
    for pat, kind in _DATE_PATTERNS:
        m = pat.match(text)
        if not m:
            continue
        if kind == "ymdhms":
            y, mo, d, h, mi = (int(x) for x in m.groups()[:5])
            s = int(m.group(6) or 0)
        elif kind == "ymd":
            y, mo, d = (int(x) for x in m.groups())
            h = mi = s = 0
        else:  # mdy
            mo = _MONTHS.get(m.group(1).lower()[:3], 0)
            d, y = int(m.group(2)), int(m.group(3))
            h = mi = s = 0
        try:
            return dt.datetime(y, mo, d, h, mi, s, tzinfo=TZ_UTC).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return ""
    return ""


def clean(value: Any, limit: int = 8000) -> Any:
    """Collapse whitespace and trim over-long bodies (keeps CSV cells sane)."""
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return int(value)
    text = re.sub(r"[ \t\r\f\v]+", " ", str(value))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:limit]


def make_row(
    *,
    post_detail: Any = "",
    platform: str,
    post_like: Any = "",
    post_created_time: Any = "",
    post_source: str = "",
    genre: str = "",
    author: Any = "",
    title: Any = "",
    topic: Any = "",
    language: str = "",
    post_id: Any = "",
) -> dict:
    return {
        "post_detail": clean(post_detail),
        "platform": platform,
        "post_like": clean(post_like),
        "post_created_time": post_created_time or "",
        "post_source": post_source or "",
        "genre": genre,
        "author": clean(author, 200),
        "title": clean(title, 400),
        "topic": clean(topic, 400),
        "language": language,
        "post_id": clean(post_id, 120),
    }


def write_csv(rows: Iterable[dict], path: str) -> int:
    rows = list(rows)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return len(rows)


# ---------------------------------------------------------------------------
# WebtoonCrawler
# ---------------------------------------------------------------------------
import re


PLATFORM = "WEBTOON"
GENRE = "webtoon"
BASE = "https://www.webtoons.com"
API = BASE + "/p/api/community/v2/posts"

DEFAULT_SERIES = [
    "https://www.webtoons.com/en/fantasy/tower-of-god/list?title_no=95",
    "https://www.webtoons.com/en/action/the-god-of-high-school/list?title_no=66",
    "https://www.webtoons.com/en/thriller/bastard/list?title_no=485",
]

_VIEWER_RE = re.compile(r"title_no=(\d+)&(?:amp;)?episode_no=(\d+)")


def _api_headers(fetcher: Fetcher, language: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Language": language,
        "Platform": "WEB_PC",
        "Service-Ticket-Id": "epicom",
        "Referer": f"{BASE}/{language}/",
    }


def list_episodes(fetcher: Fetcher, series_url: str, language: str = "en") -> tuple[str, list[dict]]:
    """Newest-first episodes of one series: [{title, url, title_no, episode_no, date}]."""
    html = fetcher.get_text(series_url)

    doc = soup(html)
    heading = doc.select_one("h1.subj")
    series_title = heading.get_text(strip=True) if heading else ""
    episodes: list[dict] = []
    for item in doc.select("#_listUl li"):
        link = item.select_one("a[href*='viewer']")
        if not link:
            continue
        m = _VIEWER_RE.search(link.get("href", ""))
        if not m:
            continue
        name_el = item.select_one(".subj span")
        date_el = item.select_one(".date")
        href = link["href"]
        if href.startswith("/"):
            href = BASE + href
        episodes.append(
            {
                "title": name_el.get_text(strip=True) if name_el else "",
                "url": href.split("?")[0] + f"?title_no={m.group(1)}&episode_no={m.group(2)}",
                "title_no": int(m.group(1)),
                "episode_no": int(m.group(2)),
                "date": date_el.get_text(strip=True) if date_el else "",
            }
        )
    return series_title, episodes


def crawl(
    series_urls: list[str] | None = None,
    episodes_per_series: int = 2,
    pages: int = 1,
    language: str = "en",
    limit: int | None = None,
    fetcher: Fetcher | None = None,
) -> list[dict]:
    own = fetcher is None
    fetcher = fetcher or Fetcher()
    headers = _api_headers(fetcher, language)
    rows: list[dict] = []
    try:
        for series_url in series_urls or DEFAULT_SERIES:
            try:
                series_title, episodes = list_episodes(fetcher, series_url, language)
            except Exception as exc:  # one dead series must not kill the run
                print(f"  ! {series_url}: {exc}")
                continue
            print(f"  {series_title or series_url}: {len(episodes)} episodes found")
            for ep in episodes[: max(0, episodes_per_series)]:
                page_id = f"w_{ep['title_no']}_{ep['episode_no']}"
                cursor = None
                for _ in range(max(1, pages)):
                    params = {"pageId": page_id, "pageSize": 30}
                    if cursor:
                        params["cursor"] = cursor
                    payload = fetcher.get_json(
                        API, params=params, headers={**headers, "Referer": ep["url"]}
                    )
                    result = payload.get("result", {})
                    posts = result.get("posts", [])
                    for post in posts:
                        author = (post.get("createdBy") or {}).get("name", "")
                        rows.append(
                            make_row(
                                post_detail=post.get("body", ""),
                                platform=PLATFORM,
                                post_like="",
                                post_created_time=utc_time(post.get("createdAt")),
                                post_source=ep["url"],
                                genre=GENRE,
                                author=author,
                                title=series_title,
                                topic=ep["title"],
                                language=str(post.get("bodyLanguage", "")).title(),
                                post_id=post.get("id", ""),
                            )
                        )
                    cursor = (result.get("pagination") or {}).get("next")
                    if not cursor or not posts:
                        break
                print(f"    episode {ep['episode_no']} ({ep['title']}): +{len(rows)} rows so far")
                if limit and len(rows) >= limit:
                    return rows[:limit]
    finally:
        if own:
            fetcher.close()
    return rows[:limit] if limit else rows

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Crawl WEBTOON (webtoons.com) episode comments.")
    p.add_argument("--series", action="append", default=None,
                   help="series URL, e.g. https://www.webtoons.com/en/fantasy/tower-of-god/list?title_no=95 (repeatable)")
    p.add_argument("--episodes", type=int, default=1, help="newest episodes per series (default 1)")
    p.add_argument("--pages", type=int, default=1, help="comment pages (cursor rounds) per episode")
    p.add_argument("--limit", type=int, default=25, help="max rows (default 25)")
    p.add_argument("--out", default="WebtoonCrawlerResults.csv", help="output CSV path")
    p.add_argument("--quiet", action="store_true", help="less per-episode logging")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    rows = crawl(series_urls=args.series, episodes_per_series=args.episodes,
                 pages=args.pages, limit=args.limit)
    if not rows:
        print("no rows collected")
        return 1
    write_csv(rows, args.out)
    print(f"\n{len(rows)} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
