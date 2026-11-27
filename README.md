# WebtoonCrawler

### Pulls every comment under a WEBTOON episode - text, author, comment language and an exact UTC timestamp - through WEBTOON's own public comment API.

Live-tested on **2026-11-27 (UTC)** from a Korean IP with plain `requests`, no login and no API key. The collected sample in `samples/webtoons_sample.csv` holds **25 real rows** from that run.

### What it collects

Tower of God, The God of High School and Bastard are Korean webtoons published on the global service; the comments are what non-Korean readers actually say about them, in English and in the site's other service languages.

### How it gets the data

**JSON API.** The comment list is not in the page HTML - it is fetched by the site's own JS from WEBTOON's public community API, which answers a signed-out `requests` call.

```
GET https://www.webtoons.com/p/api/community/v2/posts
    ?pageId=w_<titleNo>_<episodeNo>&pageSize=30&cursor=<pagination.next>
    Language: en          Platform: WEB_PC          Service-Ticket-Id: epicom
```

* The episode list is server-rendered: `https://www.webtoons.com/en/<genre>/<slug>/list?title_no=<n>` → `#_listUl li a[href*='viewer']`, newest first, 9 episodes per page (`.subj span` = episode name, `.date` = date).
* The `pageId` used by the API is `w_<titleNo>_<episodeNo>`.
* Paging: send `result.pagination.next` back as **`cursor=`**. Sending it as `next=` silently returns page 1 again.
* `POST /graphql` is not a GraphQL endpoint (it answers 200 with the home page HTML); the JSON API above is the only route.

### Required Libraries

```
python -m pip install -r requirements.txt
```

`requests`, `beautifulsoup4`, `lxml` — nothing else. No browser, no account, no token.

### Usage

```
python WebtoonCrawler.py                                   # defaults, 25-ish rows
python WebtoonCrawler.py --limit 50 --out my_run.csv
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--series` | 3 Korean webtoons | series URL (`…/list?title_no=N`), repeatable |
| `--episodes` | `1` | newest episodes read per series |
| `--pages` | `1` | comment pages (cursor rounds) per episode |
| `--limit` | `25` | max rows |
| `--out` | `WebtoonCrawlerResults.csv` | output CSV path |

Examples:

```
python WebtoonCrawler.py --limit 5 --out quick.csv
```

The CSV is written UTF-8 with a BOM so Excel opens Korean/Chinese text correctly.

### Output schema

`post_detail, platform, post_like, post_created_time, post_source, genre, author, title, topic, language, post_id`

| JSON field | Column |
|------------|--------|
| `body` | `post_detail` |
| `createdBy.name` | `author` |
| `createdAt` (epoch ms) | `post_created_time` (UTC) |
| `bodyLanguage` | `language` |
| `id` | `post_id` |
| episode viewer URL | `post_source` |

`post_created_time` is **UTC** in `YYYY-MM-DD HH:MM:SS`.

### Notes and limits

* **`post_like` is blank by design.** For signed-out visitors the API returns the `post_like` reaction object with `"emotions": []` and no count, so there is no honest number to record (the crawler does not guess).
* Replies are not fetched: child comments live at `/v2/post/<id>/child-posts` and are counted only through `childPostCount`.
* Only series with `title_no` on the global (`/en/`) service are covered; the Korean service (comic.naver.com) is a different site.

Reply counts such as `childPostCount` (in the API response) tell you how much discussion sits one level down; if replies matter, call `/v2/post/<id>/child-posts` with the same headers.

### Tests

```
python -m tests.test_parsers
```

list_episodes() and crawl() are exercised offline against `tests/fixtures/webtoons_list.html` + `webtoons_comments.json`. No network is needed for the tests.

### Etiquette

The crawler waits 0.8 s between calls to the same host (1.5 s on rate-limited APIs) and backs off on `429/5xx`. Keep that pacing: the sites rate-limit by IP, and a fast loop gets the whole block page instead of data.

---

# 웹툰 크롤러 — 웹툰(webtoons.com) 에피소드 댓글 크롤러

### webtoons.com 에피소드의 댓글(본문·작성자·댓글 언어·정확한 UTC 시각)을 WEBTOON 자체 공개 댓글 API로 수집합니다.

**2026-11-27(UTC)** 한국 IP에서 일반 `requests`로, 로그인·API 키 없이 실제 테스트했습니다. `samples/webtoons_sample.csv`에는 그 실행에서 나온 **실제 25행**의 결과가 들어 있습니다.

### 무엇을 수집하나

《신의 탑》·《갓 오브 하이스쿨》·《바스타드》처럼 한국에서 연재된 웹툰이 글로벌 서비스에 올라가 있는데, 그 댓글은 비한국 독자가 실제로 하는 말입니다. 댓글 언어(bodyLanguage)도 함께 저장됩니다.

### 동작 방식

**JSON API** 방식입니다. 댓글 목록은 페이지 HTML에 없고, 사이트 자바스크립트가 WEBTOON의
공개 커뮤니티 API를 호출해 가져옵니다. 로그인하지 않은 `requests` 요청에도 정상 응답합니다.

```
GET https://www.webtoons.com/p/api/community/v2/posts
    ?pageId=w_<titleNo>_<episodeNo>&pageSize=30&cursor=<pagination.next>
    Language: en        Platform: WEB_PC        Service-Ticket-Id: epicom
```

* 회차 목록은 서버 렌더링 HTML에서 읽습니다: `…/list?title_no=N` → `#_listUl li a[href*='viewer']`
* 페이지 넘김은 `result.pagination.next`를 **`cursor=`** 로 다시 보내야 합니다(`next=`로 보내면 1페이지가 반복됩니다)
* `POST /graphql`은 GraphQL 엔드포인트가 아닙니다(홈 HTML을 200으로 돌려줌). 위 JSON API가 유일한 경로입니다

### 설치

```
python -m pip install -r requirements.txt
```

`requests`, `beautifulsoup4`, `lxml` 세 개면 됩니다. 브라우저도, 계정도, 토큰도 필요 없습니다.

### 사용법

```
python WebtoonCrawler.py                          # 기본값 실행
python WebtoonCrawler.py --limit 50 --out my_run.csv
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--series` | 한국 웹툰 3종 | 시리즈 URL(`…/list?title_no=N`), 여러 번 지정 가능 |
| `--episodes` | `1` | 시리즈당 읽을 최신 회차 수 |
| `--pages` | `1` | 회차당 댓글 페이지(커서) 수 |
| `--limit` | `25` | 최대 행 수 |
| `--out` | `WebtoonCrawlerResults.csv` | 출력 CSV 경로 |

CSV는 UTF-8(BOM)으로 저장되어 엑셀에서 한글·중국어가 깨지지 않습니다.

### 출력 컬럼

`post_detail, platform, post_like, post_created_time, post_source, genre, author, title, topic, language, post_id`

`post_created_time`은 **UTC** 기준 `YYYY-MM-DD HH:MM:SS` 형식입니다.

### 주의사항

* **`post_like`는 의도적으로 비어 있습니다.** 비로그인 요청에는 `post_like` 반응 객체가 `"emotions": []`로만
  오고 개수가 없습니다. 추정값을 넣지 않았습니다.
* 답글은 수집하지 않습니다(`/v2/post/<id>/child-posts`에 있고, `childPostCount`로 개수만 알 수 있습니다).
* 글로벌(`/en/`) 서비스의 `title_no` 기준입니다. 네이버웹툰(comic.naver.com)은 다른 사이트입니다.

### 테스트

```
python -m tests.test_parsers
```

네트워크 없이 수집해 둔 fixture로 파서를 검증합니다.

### 수집 예절

같은 호스트에 0.8초 간격(속도 제한이 있는 API는 1.5초)을 두고, `429/5xx`에서는 백오프합니다.
사이트는 IP 기준으로 요청을 제한하므로 이 속도를 유지해 주세요. 빠르게 반복하면 데이터 대신 차단
페이지가 돌아옵니다.
