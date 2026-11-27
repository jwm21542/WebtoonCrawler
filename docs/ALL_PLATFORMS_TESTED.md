# What actually worked - live feasibility record (all 16 platform-probes)

This is the shared research record behind the seven *Crawler repos: every platform in
the original brief was probed live, and this file keeps the refusals as well as the
successes so the decisions are reproducible. The platform this repository crawls is
this repository crawls **WEBTOON (webtoons.com) - row 1**.

All results below are from live, non-destructive reads made on **2026-11-27 (UTC),
00:20-00:40 KST on 2026-11-28** from a Korean IP address:

* plain HTTP (`python requests`, Chrome 131 user agent, gzip/deflate) first, then
* a real Chrome (desktop, `en-US`/`ko-KR`, not signed in to anything) only for the
  platforms that refused plain HTTP.

Nothing was posted, voted or subscribed anywhere; every call was a GET/POST read
of a public page. Two independent runs were done for the non-obvious endpoints so
a single flaky response is not recorded as a wall.

Legend: **EASY** = plain HTTP, no login, stable markup or JSON ·
**MEDIUM** = plain HTTP but needs a JS-rendered fragment or the site is rate
limiting · **BROWSER** = bot wall for HTTP clients, content renders in a real
browser · **BLOCKED** = no route found (gone, region-locked, or token-gated).

## Summary table

| # | Platform | Category | Tier | Plain HTTP | Wall / refusal seen | Content reachable without login |
|---|----------|----------|------|-----------|---------------------|--------------------------------|
| 1 | webtoons.com (EN/global) | webtoon | **EASY** | `200` | none (`server: nfront`, no Cloudflare) | episode comments via JSON API |
| 2 | tapas.io | webtoon | **EASY→MEDIUM** | `200` | none (`server: nginx`) | episode comments via JSON, list is an HTML fragment |
| 3 | myanimelist.net | webtoon (anime) | **EASY** | `200` | recaptcha script in page footer, **no challenge shown** | full user reviews |
| 4 | api.jikan.moe (Jikan) | webtoon (API) | **BLOCKED** | connect timeout | TCP connect timeout ×2 (25 s, 40 s) - unreachable from this host | - |
| 5 | anilist.co (GraphQL) | webtoon (anime) | **EASY** | `200` | none (`server: cloudflare`, no challenge) | full reviews + vote counts |
| 6 | mangahelpers.com/forum/forums/manhwa.966/ | webtoon (manhwa) | **EASY** | `200` | none (`server: cloudflare`, no challenge) | threads and posts |
| 7 | mydramalist.com | variety (K-drama) | **EASY→MEDIUM** | `200` | none; wrong slug answers `500` with an empty body | reviews (12 per page) |
| 8 | viki.com | variety (K-drama) | **BLOCKED** | `404` on the show URL | browser said **"Viki is not available in your region"** (KR IP); `api.viki.io` `400` without an app token | nothing |
| 9 | forums.soompi.com | variety | **GONE** | `301` | redirects to `https://www.soompi.com`; `/forums` → `404` | forum no longer exists |
| 10 | kprofiles.com/forums/ | variety (+ Korean Food subforum) | **BROWSER** | `403` | Cloudflare **"you have been blocked"** (6 KB page) | full XenForo forum |
| 11 | douban.com | variety / film | **EASY (feed) / BLOCKED (groups)** | `200` / `403` | `/group/topic/<id>/` → `403 没有访问权限` (login only); subject review tab redirects to `sec.douban.com` verification | site-wide review feed |
| 12 | tiktok.com | food | **BLOCKED for HTTP, BROWSER for comments** | `200` but empty data | `/api/comment/list/` → `200 {"status_code":5}` (needs X-Bogus/msToken signature); tag page `__UNIVERSAL_DATA_FOR_REHYDRATION__` holds only app config | comments render in a real browser |
| 13 | yelp.com | food | **BROWSER** | `403` | **DataDome** (`server: DataDome`, 840-byte block page) | full review pages |
| 14 | tripadvisor.com | food | **BROWSER** | `403` | **DataDome** (775-byte block page) | restaurant lists + review snippets |
| 15 | tabelog.com | food | **BROWSER** | `403` | **Cloudflare managed challenge** (`Just a moment...`, `cf_chl_opt`, 5.7 KB) | restaurant lists, ratings |
| 16 | quora.com | food | **BROWSER** | `403` | **Cloudflare challenge** (`Just a moment...`) | topic feeds, full answers |

`BROWSER` means a Chrome that loads the site normally got the content with no
login and no captcha to solve; the site only refuses scripted HTTP clients
(missing JS challenge / DataDome fingerprint).

## Exact endpoints and selectors that were verified

### 1. WEBTOON - `webtoons.com`

```
GET https://www.webtoons.com/p/api/community/v2/posts
    ?pageId=w_<titleNo>_<episodeNo>&pageSize=30[&cursor=<pagination.next>]
    Language: en        Platform: WEB_PC        Service-Ticket-Id: epicom
```

`200` JSON. One post carries `body`, `bodyLanguage`, `createdAt` (epoch ms),
`createdBy.name`, `childPostCount`, `id`; the next page cursor is
`result.pagination.next` and must be sent back as `cursor=` (sending it as
`next=` returns page 1 again). Replies: `GET .../v2/post/<id>/child-posts`.

*Episode list* (server-rendered): `https://www.webtoons.com/en/<genre>/<slug>/list?title_no=<n>`
→ `#_listUl li a[href*='viewer']`, newest first, 9 per page, episode name in
`.subj span`, date in `.date`.

`POST /graphql` is **not** a GraphQL endpoint: it answers `200` with the home page
HTML, so the JSON API above is the only way in.

**Not exposed:** like counts. `reactions` lists `post_like` with
`"emotions": []` and no count for signed-out visitors, so `post_like` is left
empty by the crawler rather than guessed.

### 2. Tapas - `tapas.io`

```
GET https://tapas.io/comment/<episode_id>?page=<n>&sort=NEWEST
    X-Requested-With: XMLHttpRequest      Referer: https://tapas.io/episode/<episode_id>
```

`200`, `{"code":200,"data":{"pagination":{"has_next":…},"total_comment_cnt":N,"html":"…"}}`.
The `html` string holds `div.comment-row-wrap#comment-row-<id>` blocks:
`a.writer__name` (author), `p.writer__date` (`Nov 10, 2026`),
`div.js-comment-body` (text), `a#comment-like-<id>[data-cnt]` (likes).

**Decoy:** `GET /episode/<id>/comments?page=1` answers `200` JSON too, but its
HTML is the empty section shell (`js-comment-disabled`, `data-cnt="0"`). The page
also exposes the real count in `.js-comment-body-cnt` (e.g. `204`) - do not read
that as "comments disabled".

Series pages (`/series/<id>/info`) list episodes as `/episode/<digits>`.

### 3. MyAnimeList - `myanimelist.net`

`GET /anime/<id>/reviews?p=<n>` → `200`, server-rendered, ~3 reviews per page.
Selector `.review-element`; fields `.username`, `.update_at` (`Jun 24, 2020`),
`.text`, `.rating` (`Reviewer's Rating: 7`), `.tags .tag` (verdicts such as
`Recommended`, `Funny`). No helpful-vote count in the listing.

The page includes `recaptcha/api.js` in its footer; that is the standard MAL
footer script, not a challenge - no captcha appeared on any of the reads.

### 4. AniList - `graphql.anilist.co`

`POST` with `{"query":…}` → `200` JSON, no API key, no auth header. Reviews:
`Media(id:…).reviews(page:…, perPage:…){nodes{id summary body score rating createdAt user{name}}}`.
`rating` = helpfulness votes, `score` = the reviewer's own 0-100 grade.
Rate limit ~90 req/min, so the crawler sleeps 1.5 s between pages.

### 5. MangaHelpers - `mangahelpers.com/forum`

`/forums/manhwa.966/` → `200`, XenForo, 26 threads. `.structItem--thread` +
`a[href*='/threads/']`. Thread pages `…/page-N/` → `200`, 20 `article.message`
each; `time[datetime]` is a full ISO timestamp, `.bbWrapper` the post body,
`.reactionsBar` the reaction names.

### 6. MyDramaList - `mydramalist.com`

`/<id>-<slug>/reviews?page=<n>` → `200`, 12 `.review` blocks per page.
`.review-body` (starts with the score table `Overall 10 Story 10 …`),
`.datetime` (`Apr  1, 2025`), author `a[href^='/profile/']`, and the literal text
"N people found this review helpful".
A wrong slug (e.g. `/9143-goblin`) answers `500` with a **zero-byte** body -
that is a slug problem, not a block, so the crawler is seeded with slugs taken
from `/shows/top`.

### 7. Douban - `movie.douban.com`

`/review/best/?start=<n*20>` → `200`, 10 `.review-item` per page (`server: dae`).
`.name` (author), `.main-meta` (`2026-11-26 13:15:04`), `.subject-img img[alt]`
(title reviewed), `h2 a` (review title), `.short-content` (excerpt; the rest is
behind a JS expand), `.action-btn.up` (有用 votes), `.reply` (`35回应`).
Group topics are signed-in only (`403`), and subject-scoped review tabs bounce to
`sec.douban.com` verification - only the site-wide review feed is open.

## What a real browser reached (and what it would take)

| Platform | What rendered signed-out | Selectors worth scraping if this is built later |
|----------|--------------------------|------------------------------------------------|
| tiktok.com | search results, video pages **and the comment list** (posting asks for login); comment count in the button label ("1개의 댓글") | `[data-e2e="comment-level-1"]`, author `[data-e2e="comment-username-1"]`, text `[data-e2e="comment-level-1"] p`, likes `[data-e2e="comment-like-count"]` |
| yelp.com | search results and business pages, e.g. HANU KOREAN BBQ with 2,405 reviews (a Google sign-in popup appears; closing it leaves the page usable) | review cards `li[class*="y-css"] ul li`, author, date, rating stars, "Helpful/Thanks" counts |
| tripadvisor.com | Seoul restaurant list with ratings, review counts and review snippets | `div[data-automation="serp-card"]`, snippet `span[data-automation="review-snippet"]` |
| tabelog.com | Tokyo restaurant list (Cloudflare challenge cleared by itself in ≈2 s) | list items `a.list-rst__rst-name-target`, review count `span.list-rst__rvw-count-num` |
| quora.com | Korean Food topic with full answers, no login | `div.q-box` answer blocks, author `a[href^="/profile/"]`, "Updated 4y" timestamps |
| kprofiles.com/forums/ | whole XenForo forum incl. the **Korean Food** subforum (39 threads / 691 messages) | `.structItem--thread`, `article.message .bbWrapper` |

Building these means driving a real Chrome (this repo's sibling crawlers already
do that with Selenium, e.g. `RedditCrawler`); `requests` cannot pass DataDome,
the Cloudflare managed challenge or TikTok's signed comment API.

## Practical notes

* Respect `robots.txt`, keep the default pacing (`Fetcher(min_interval=0.8)`,
  1.5 s on AniList) and never run the crawlers as a tight loop; all of these
  sites rate-limit by IP.
* Dates: the sites print dates in the viewer's timezone. Rows store the printed
  calendar date at 00:00:00 UTC unless the source gives an exact epoch
  (WEBTOON, AniList, MangaHelpers) - the README says which platform is which.
* Two platforms changed under the old assumptions: Soompi's forum no longer
  exists, and Tapas is now served as a "Spotlight"-branded Next.js shell whose
  comment data only arrives through `/comment/<id>`.
