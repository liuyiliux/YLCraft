# Database Design + Scheduling Research
### For a single-machine, self-hosted FastAPI + SQLModel/SQLAlchemy + PostgreSQL multi-platform content collector

**Verification date:** all live data fetched 2026-10-01/02. Every claim below carries a source URL.
Everything I could not read is flagged **[UNVERIFIED]**. Nothing here is from memory.

**Tool note:** GitHub's unauthenticated REST API is limited to 60 req/hr and was exhausted mid-research.
Repo stats marked below were captured before exhaustion via `curl.exe` against
`https://api.github.com/repos/<owner>/<repo>`. `raw.githubusercontent.com` is not rate-limited and was used
for all source reading. Several fetches intermittently returned `000`/empty — consistent with the flaky-VPN
premise — and were retried; those gaps are flagged, not guessed.

---

## 0. Verified repository / release inventory

| Project | Stars | Last push | License | Source |
|---|---|---|---|---|
| NanmiCoder/MediaCrawler | 66,054 | 2026-09-19 | **NOASSERTION** (non-commercial learning license) | api.github.com/repos/NanmiCoder/MediaCrawler |
| scrapy/scrapy | 64,539 | 2026-10-01 | BSD-3-Clause | api.github.com/repos/scrapy/scrapy |
| miniflux/v2 | 9,761 | 2026-10-01 | Apache-2.0 | api.github.com/repos/miniflux/v2 |
| immich-app/immich | 115,400 | 2026-10-01 | AGPL-3.0 | api.github.com/repos/immich-app/immich |
| photoprism/photoprism | 40,263 | 2026-10-01 | **NOASSERTION** | api.github.com/repos/photoprism/photoprism |
| fsspec/filesystem_spec | 1,365 | 2026-09-29 | BSD-3-Clause | api.github.com/repos/fsspec/filesystem_spec |
| agronholm/apscheduler | 7,642 | 2026-09-26 | MIT | api.github.com/repos/agronholm/apscheduler |
| **python-arq/arq** (moved) | 3,013 | 2026-04-16 | MIT | api.github.com/repos/python-arq/arq |
| Bogdanp/dramatiq | 5,319 | 2026-09-14 | LGPL-3.0 | api.github.com/repos/Bogdanp/dramatiq |
| celery/celery | 28,929 | 2026-10-01 | **NOASSERTION** | api.github.com/repos/celery/celery |
| django/django | 91,239 | 2026-10-01 | BSD-3-Clause | api.github.com/repos/django/django |

Releases (PyPI JSON API):

| Package | Latest | Released | Source |
|---|---|---|---|
| APScheduler | **3.11.3** | **2026-06-28** | pypi.org/pypi/APScheduler/json |
| arq | 0.28.0 | 2026-04-16 | pypi.org/pypi/arq/json |
| dramatiq | 2.2.1 | 2026-09-02 | pypi.org/pypi/dramatiq/json |
| periodiq | 0.14.0 | 2026-04-16 | pypi.org/pypi/periodiq/json |
| celery | 5.6.3 | 2026-03-26 | pypi.org/pypi/celery/json |
| fsspec | 2026.9.0 | 2026-09-18 | pypi.org/pypi/fsspec/json |

**Two premises in the brief were factually wrong, and both change the recommendation:**
1. **`Bogdanp/dramatiq-periodiq` does not exist.** `api.github.com/repos/Bogdanp/dramatiq-periodiq` → `Not Found`.
   Periodiq's canonical home is **GitLab**: <https://gitlab.com/bersace/periodiq> (author Étienne BERSAC).
   PyPI lists **no `project_urls` at all** for periodiq.
2. **APScheduler 4.x is not released.** Every 4.x on PyPI is an alpha. See §4.

---

# 1. Storing crawl results: raw JSON + structured columns side by side

## 1.1 MediaCrawler — typed columns only, NO raw JSON blob

Repo has both `store/` and `database/` (confirmed via git trees API). The relevant files are
`store/<platform>/_store_impl.py` and `database/models.py`.

**Answer: MediaCrawler does NOT keep the raw response.** `XhsDbStoreImplement` maps a dict into
**explicit typed ORM columns** and explicitly `json.dumps()`es the two list-valued fields into `Text`
columns. From `store/xhs/_store_impl.py` (quoted):

```python
class XhsDbStoreImplement(AbstractStore):
    async def store_content(self, content_item: Dict):
        note_id = content_item.get("note_id")
        if not note_id:
            return
        async with get_session() as session:
            if await self.content_is_exist(session, note_id):
                await self.update_content(session, content_item)
            else:
                await self.add_content(session, content_item)

    async def add_content(self, session: AsyncSession, content_item: Dict):
        note = XhsNote(
            creator_hash=content_item.get("creator_hash"),
            nickname=content_item.get("nickname"),
            add_ts=add_ts,
            last_modify_ts=last_modify_ts,
            note_id=content_item.get("note_id"),
            ...
            image_list=json.dumps(content_item.get("image_list")),
            tag_list=json.dumps(content_item.get("tag_list")),
            ...
        )
        session.add(note)
```

Note the design consequences actually visible in that code:
- Lists are **stringified JSON in `Text` columns** (`image_list`, `tag_list`) — not `jsonb`, not a side table.
- `update_content` **only refreshes counters** (`liked_count`, `collected_count`, `comment_count`,
  `share_count`, `last_update_time`). Title/desc/url are never updated after first insert.
- Presence check is a **separate `SELECT` before INSERT** (`content_is_exist`), i.e. a read-then-write race,
  not an atomic upsert.

**DB support** — `database/db_session.py` builds SQLAlchemy async URLs for three backends (quoted):

```python
if db_type == "sqlite":
    db_url = f"sqlite+aiosqlite:///{sqlite_db_config['db_path']}"
elif db_type == "mysql" or db_type == "db":
    db_url = f"mysql+asyncmy://{user}:{pwd}@{host}:{port}/{db_name}"
elif db_type == "postgres":
    db_url = f"postgresql+asyncpg://{user}:{pwd}@{host}:{port}/{db_name}"
```

So: **SQLite (aiosqlite), MySQL (asyncmy), PostgreSQL (asyncpg)** — plus JSON/JSONL/CSV/Excel/MongoDB
stores. `docs/data_storage_guide.md` calls SQLite "推荐" (recommended) for personal use and PostgreSQL
"推荐生产环境使用" (recommended for production).

Actual column definitions from `database/models.py` (`XhsNote` family; `BilibiliVideo` shown as the
clearest example, quoted):

```python
class BilibiliVideo(Base):
    __tablename__ = 'bilibili_video'
    id = Column(Integer, primary_key=True, comment='主键ID')
    video_id = Column(String(64), nullable=False, index=True, unique=True, comment='视频ID')
    video_url = Column(Text, nullable=False, comment='视频URL')
    creator_hash = Column(String(64), index=True, comment='创作者匿名哈希')
    nickname = Column(Text, comment='用户昵称(已脱敏)')
    liked_count = Column(Integer, comment='点赞数')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    ...
    create_time = Column(BigInteger, index=True, comment='创建时间戳')
    video_play_count = Column(Text, comment='播放数')
    ...
    source_keyword = Column(Text, default='', comment='来源关键词')
```

Three portable-design observations worth stealing:
1. **Counters are `Text`, not `Integer`** (`liked_count`, `video_play_count`, `share_count`). Platforms return
   `"1.2万"` / `"10w+"` strings; storing them as integers would break. MediaCrawler sidesteps this by
   stringifying. (Their `BilibiliVideo.liked_count` is `Integer` while `DouyinAwemeComment.like_count` is
   `Text` — the schema is inconsistent per platform.)
2. **`add_ts` + `last_modify_ts` on every row** — crawler-local bookkeeping separated from platform time
   (`create_time`, `pub_ts`). This is the right split.
3. **No raw payload column anywhere.** If the platform changes its response shape and you mis-mapped a
   field, that data is unrecoverable without re-crawling.

## 1.2 Scrapy Feed Exports / Item Pipelines — deliberately out of the DB path

Scrapy's architecture separates concerns rather than fusing raw+typed. From
`docs/topics/feed-exports.rst` (quoted):

> "the feed that declares them. Items are exported as returned, so `item_scraped` signal,
> item pipelines and the `item_scraped_count` stat still see the item as scraped; **use item processors
> for output formatting, and item pipelines for anything that should apply to the item itself.**"

Key settings confirmed in that file: `FEED_EXPORT_FIELDS` (default `None`) defines fields/order/output
names; `FEED_STORE_EMPTY` (default `True`). Feed storage backends are pluggable via `FEED_STORAGES`, and
the export path is a **sink that runs after the pipeline**, not a persistence layer with schema.

**Takeaway:** Scrapy's answer to "raw vs typed" is *"neither, in the DB"* — it ships JSON/JSONL/CSV/XML
files and leaves persistence to the user. There is no Scrapy feature that writes a raw blob + typed
columns into Postgres. **[UNVERIFIED]** whether any third-party Scrapy extension does this — I did not
find one and did not search exhaustively.

## 1.3 PostgreSQL `jsonb` pattern: raw payload + generated/normalized columns

### jsonb vs json (verified, PG 18 docs)
From <https://www.postgresql.org/docs/current/datatype-json.html> (quoted):

> "The `json` data type stores an exact copy of the input text, which processing functions must reparse on
> each execution; while `jsonb` data is stored in a decomposed binary format that makes it slightly slower
> to input due to added conversion overhead, but significantly faster to process, since no reparsing is
> needed. `jsonb` also supports indexing, which can be a significant advantage."
> "By contrast, `jsonb` does not preserve white space, does not preserve the order of object keys, and does
> not keep duplicate object keys."

**This matters for a "keep the raw response" requirement.** `jsonb` is **lossy as a raw archive**: key order
and duplicate keys are destroyed. If the goal is byte-exact forensic re-parsing, store `jsonb` **and**
retain the original bytes separately, or use `json`/`text`. `jsonb` also **rejects `\u0000`** (quoted:
*"The `jsonb` type also rejects `\u0000` (because that cannot be represented in PostgreSQL's `text` type)"*)
— a real hazard for scrape payloads containing NUL bytes, and it will **hard-fail the insert**.

Numeric fidelity caveat (quoted): *"`jsonb` will reject numbers that are outside the range of the
PostgreSQL `numeric` data type"*, and `1.230e-5` prints back as `0.00001230`. IDs returned as large
integers are fine, but very large or exotic numerics can differ textually from the source.

### GIN index: `jsonb_ops` vs `jsonb_path_ops`
From the same page (quoted):

> "The default GIN operator class for `jsonb` supports queries with the key-exists operators `?`, `?|` and
> `?&`, the containment operator `@>`, and the `jsonpath` match operators `@?` and `@@`."
> "The non-default GIN operator class `jsonb_path_ops` does not support the key-exists operators, but it
> does support `@>`, `@?` and `@@`."

Size/speed tradeoff (quoted, verbatim — this is the real answer to "GIN index size"):

> "A `jsonb_path_ops` index is usually much smaller than a `jsonb_ops` index over the same data, and the
> specificity of searches is better, particularly when queries contain keys that appear frequently in the
> data."
> "the former creates independent index items for each key and value in the data, while the latter creates
> index items only for each value in the data ... each `jsonb_path_ops` index item is a hash of the value
> and the key(s) leading to it"

Documented failure mode of `jsonb_path_ops` (quoted): *"it produces no index entries for JSON structures
not containing any values, such as `{"a": {}}`. If a search for documents containing such a structure is
requested, it will require a full-index scan, which is quite slow. `jsonb_path_ops` is therefore ill-suited
for applications that often perform such searches."*

Also documented: a GIN index on the **whole column** *"will store copies of every key and value in the
`jdoc` column, whereas the expression index of the previous example stores only data found under the
`tags` key"* — **targeted expression GIN indexes are smaller and faster than whole-column GIN.** For a
crawler archiving large raw payloads, indexing the entire `raw` column is the expensive mistake; index only
the sub-path you query.

### Generated columns — what PG version, what restrictions
From <https://www.postgresql.org/docs/current/ddl-generated-columns.html> (quoted):

> "A generated column is by default of the virtual kind. Use the keywords `VIRTUAL` or `STORED` to make the
> choice explicit."

**Important, version-sensitive finding:** PG 18 docs state virtual is the **default** and describe both
kinds. On PG 12–17 only `STORED` existed and `VIRTUAL` was not a keyword. So:
- `GENERATED ALWAYS AS (...) STORED` — **PG 12+**.
- `GENERATED ALWAYS AS (...) VIRTUAL` — **PG 18+**. On PG <18 the bare form (no `STORED`) is an error.

I did **not** find a doc statement pinning the exact "PG 12 introduced STORED generated columns" claim on
these pages. **[UNVERIFIED — version-introduction claim]**. Verified from docs: STORED occupies storage
("computed when it is written ... and occupies storage as if it were a normal column"); VIRTUAL "occupies
no storage and is computed when it is read."

**Can a generated column index into jsonb? Yes — via the immutable-function restriction.** The generation
expression may use **immutable functions** only. `->>` and `#>>` extract as `text` and are immutable, so
they are legal. Doc restrictions (quoted):

> "The generation expression can only use immutable functions and cannot use subqueries or reference
> anything other than the current row in any way."
> "A generation expression cannot reference another generated column."
> "A generation expression cannot reference a system column, except `tableoid`."
> "A generated column cannot be written to directly. In `INSERT` or `UPDATE` commands, a value cannot be
> specified for a generated column, but the keyword `DEFAULT` may be specified."
> "A generated column cannot have a column default or an identity definition."
> "A column default can use volatile functions, for example `random()` or functions referring to the
> current time; this is not allowed for generated columns."

That last one is the trap for crawlers: **you cannot have a generated column defaulting to `now()`**, and
you cannot use `jsonb_path_*_tz` (they are `stable`, not `immutable` — the docs say of the `_tz` variants:
*"these functions are marked as stable, which means these functions cannot be used in indexes"*).

Practical DDL:

```sql
CREATE TABLE crawl_item (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    platform      text        NOT NULL,
    source_id     text        NOT NULL,
    -- verbatim-ish raw payload; jsonb is a REWRITE of the response, not a byte archive
    raw           jsonb       NOT NULL,
    -- lossless archive if you need byte-level re-parsing
    raw_bytes     bytea,
    fetched_at    timestamptz NOT NULL DEFAULT now(),
    content_hash  bytea       NOT NULL,   -- sha256(raw text) for change detection

    -- normalized, queryable projections; immutable ops only
    title    text GENERATED ALWAYS AS (raw ->> 'title')  STORED,
    pub_ts   timestamptz GENERATED ALWAYS AS (
                 (NULLIF(raw ->> 'create_time',''))::timestamptz
             ) STORED,
    likes    bigint GENERATED ALWAYS AS (
                 NULLIF(regexp_replace(raw ->> 'liked_count', '\D', '', 'g'), '')::bigint
             ) STORED,

    CONSTRAINT crawl_item_platform_source_uk UNIQUE (platform, source_id)
);

-- targeted expression GIN: smaller than indexing all of `raw`
CREATE INDEX crawl_item_raw_gin ON crawl_item USING GIN (raw jsonb_path_ops);
```

**Gotcha on the above:** a generated column whose cast can fail will **fail the whole INSERT**. If
`raw->>'create_time'` is `"刚刚"` (as Chinese platforms return), `::timestamptz` raises and you lose the
row. `NULLIF(...,'')` handles empty string but **not** non-numeric garbage. For genuinely dirty fields,
use a plain column populated in application code (or a trigger with exception handling) instead of a
generated column. **This is why MediaCrawler stringifies counters to `Text`** — same root cause.

Also: expression-index equivalence. Since `raw ->> 'title'` is immutable, this is equally valid and avoids
a stored column:

```sql
CREATE INDEX crawl_item_title_idx ON crawl_item ((raw ->> 'title'));
```

### The `-` vs `->>` operator gotchas (verified)
From <https://www.postgresql.org/docs/current/functions-json.html> Table 9.47/9.48 (quoted):

| Operator | Returns | Meaning |
|---|---|---|
| `-> text` | `jsonb` | field as **JSON** |
| `->> text` | `text` | field as **text** |
| `#>` `text[]` | `jsonb` | path as JSON |
| `#>>` `text[]` | `text` | path as text |
| `- text` | `jsonb` | **DELETES** a key/element |
| `#- text[]` | `jsonb` | **DELETES** at path |

The real gotchas, all doc-backed:
1. **`-` is deletion, not navigation.** `'{"a":"b","c":"d"}'::jsonb - 'a'` → `{"c":"d"}`. Anyone coming
   from JS (`obj.a`) or thinking of `->` will write `raw - 'title'` and **silently destroy the payload**
   inside an `UPDATE`. `-` with an `integer` *"Throws an error if JSON value is not an array."*
2. **`->` returns `jsonb`, so comparing to a SQL string needs a cast.**
   `raw -> 'x' = 'abc'` compares `jsonb` to `text` → cast mismatch error. You want `raw ->> 'x' = 'abc'`.
   But note the documented subscripting rule: `WHERE jsonb_field['key'] = '"value"'` — the right side must
   itself be jsonb, hence the doubled quotes.
3. **Missing keys return NULL, they do not error** (quoted): *"The field/element/path extraction operators
   return NULL, rather than failing, if the JSON input does not have the right structure to match the
   request"*. So a typo'd key yields NULL, not an error — silent data loss in generated columns.
4. **`?` tests top-level only** (quoted): *"existence must match at the top level ... `'{"foo": {"bar":
   "baz"}}'::jsonb ? 'bar'` — yields false"*, and *"Object values are not considered"*.

## 1.4 The "keep the raw response for re-parsing" argument — and the counter-argument

**Real, quantified counter-argument (cite):** Dan Robinson, *"When To Avoid JSONB In A PostgreSQL Schema"*,
Heap, 2016-09-01 — <https://www.heap.io/blog/when-to-avoid-jsonb-in-a-postgresql-schema>. This is a
production post-mortem, not theory. Quoted findings:

> "**The performance is dramatically worse — a whopping 584 seconds on my laptop, about 2000x slower**"

Cause (quoted): *"PostgreSQL doesn't know how to keep statistics on the values of fields within JSONB
columns. It has no way of knowing, for example, that `record ->> 'value_2' = 0` will be true about 50% of
the time, so it relies on a hardcoded estimate of 0.1%."* And the operational cost (quoted):

> "**This caused production issues for us, and the only way to get around them was to disable nested loops
> entirely as a join option**, with a global setting of `enable_nestloop = off`."

On size (quoted): *"the initial non-JSONB version of our table takes up 79 mb of disk space, whereas the
JSONB variant takes 164 mb — more than twice as much"* and *"**we found a disk space savings of about 30%
by pulling 45 commonly used fields out of JSONB and into first-class columns**."* Their rule of thumb
(quoted): *"if an optional field is going to have a ten-character key in your JSONB blobs, and thus cost at
least 80 bits to store the key in each row in which it's present, it will save space to give it a
first-class column if it's present in at least 1/80th of your rows."*

**How to reconcile that with "keep the raw".** The Heap argument is against *querying through* JSONB, not
against *archiving* it. The defensible design is: **`raw jsonb` is write-mostly and never appears in a
`WHERE` clause or a `JOIN`** — it is referenced only by primary key when re-parsing. All filtering,
sorting and joining happens on typed/generated columns. Under that rule the planner never needs statistics
on JSON path expressions, which neutralises the Heap failure mode. The 2x storage figure remains real and
is the honest price of the archive.

**PG's own guidance on document size** (from the jsonb type page, quoted) is a direct caution:

> "Although storing large documents is practicable, keep in mind that any update acquires a row-level lock
> on the whole row. Consider limiting JSON documents to a manageable size in order to decrease lock
> contention ... Ideally, JSON documents should each represent an atomic datum"

A crawler that re-fetches and rewrites a 1 MB raw payload locks that row; concurrent updates to sibling
columns (view counts, download status) will contend. **Practical consequence: put the raw payload in its
own table keyed by the item id**, so hot mutable columns don't share a row with the cold blob. Also note
TOAST: large `jsonb`/`bytea` values are stored out-of-line, so the main heap stays small, but any
`SELECT *` silently detoasts everything.

**Real project that keeps raw for re-parsing: [UNVERIFIED].** I did not find a project that I read the
source of which stores a full verbatim API response blob alongside typed columns. MediaCrawler does not
(§1.1). Scrapy does not (§1.2). Miniflux keeps `content` but re-parses *before* storage and does not keep
the feed XML (see §2.1). I am explicitly flagging this rather than citing something I did not read.

---

# 2. Incremental crawling / upsert

## 2.1 Miniflux — the best real reference for per-source watermark + dedupe

Miniflux's entire schema lives in `internal/database/migrations.go` as an ordered
`var migrations = [...]func(tx *sql.Tx) error` array. It is **PostgreSQL-only** (`CREATE TYPE ... AS
enum`, `jsonb`, `inet`, `tsvector`, `bytea`, `sha256()`).

### Dedupe: unique constraint on `(feed_id, hash)`

Original creation (quoted verbatim from migration #1):

```sql
CREATE TABLE entries (
    id BIGSERIAL,
    user_id int not null,
    feed_id bigint not null,
    hash text not null,
    published_at timestamp with time zone not null,
    title text not null,
    url text not null,
    author text,
    content text,
    status entry_status default 'unread',
    primary key (id),
    unique (feed_id, hash),
    foreign key (user_id) references users(id) on delete cascade,
    foreign key (feed_id) references feeds(id) on delete cascade
);

CREATE INDEX entries_feed_idx on entries using btree(feed_id);
```

**This is exactly the `(source, content_hash)` dedupe key you want.** The constraint name is auto-generated
by PG as `entries_feed_id_hash_key` — confirmed by a later migration's own comment (quoted):

> "entries_feed_idx is redundant: the unique constraint `entries_feed_id_hash_key(feed_id, hash)` and the
> explicit `entries_feed_id_status_hash_idx(feed_id, status, hash)` both cover feed_id-leading lookups,
> including FK cascade deletes."

Later index evolution (quoted, all real migrations):
```sql
CREATE INDEX entries_feed_id_status_hash_idx ON entries USING btree (feed_id, status, hash)
CREATE INDEX entries_user_feed_idx ON entries (user_id, feed_id)
CREATE INDEX entries_user_status_published_idx ON entries(user_id, status, published_at)
DROP INDEX entries_feed_idx            -- dropped as redundant
DROP INDEX entries_user_status_idx     -- dropped as redundant (strict prefix of others)
```
**Lesson: Miniflux actively drops redundant indexes.** Five indexes shared a `(user_id, status)` prefix;
two were pure overhead. For a single-machine crawler, resist adding an index per query pattern.

### How dedupe is actually queried — not `ON CONFLICT`, but a pre-check

From `internal/storage/entry.go` (quoted, comments are theirs):

```go
// entryExists checks if an entry already exists based on its hash when refreshing a feed.
// Note: This query uses entries_feed_id_hash_key index (filtering on user_id is not necessary).
err := tx.QueryRow(`SELECT true FROM entries WHERE feed_id=$1 AND hash=$2 LIMIT 1`, entry.FeedID, entry.Hash)...
```
```go
// (feed_id, hash) pair has a tombstone recording a prior deletion.
```
```go
func (s *Storage) IsNewEntry(feedID int64, entryHash string) bool {
    // ... SELECT 1 FROM entries WHERE feed_id=$1 AND hash=$2
    //     SELECT 1 FROM entry_tombstones WHERE feed_id=$1 AND hash=$2
}
```

So Miniflux does **read-then-insert inside one transaction** (it has `tx` in scope, so it is serialised per
transaction, and it streams a single feed at a time). It uses `ON CONFLICT` for the tombstone copy:

```sql
INSERT INTO entry_tombstones (feed_id, hash)
SELECT feed_id, hash FROM deleted WHERE hash <> ''
ON CONFLICT (feed_id, hash) DO NOTHING
```

**The tombstone table is the genuinely clever pattern** and directly relevant to a re-crawl tool (quoted):

```sql
CREATE TABLE entry_tombstones (
    feed_id bigint not null references feeds(id) on delete cascade,
    hash text not null check (hash <> ''),
    deleted_at timestamp with time zone not null default now(),
    primary key (feed_id, hash)
);
CREATE INDEX entry_tombstones_deleted_at_idx ON entry_tombstones (deleted_at);
```
Why it matters: with a plain `unique(feed_id, hash)`, deleting a row means the next crawl **re-inserts**
it. A tombstone keyed by the same pair lets `IsNewEntry` answer "new" correctly after deletion. For a
content collector where users delete items, this prevents zombie resurrection.

### Per-feed fetch state / watermark

`feeds` accumulates the real cursor columns over many migrations (quoted, verbatim):

```sql
checked_at timestamp with time zone default now(),
etag_header text default '',
last_modified_header text default '',
parsing_error_msg text default '',
parsing_error_count int default 0,
...
ALTER TABLE feeds ADD COLUMN next_check_at timestamp with time zone default now();
CREATE INDEX ...
ALTER TABLE feeds ADD COLUMN disabled boolean default 'f';
ALTER TABLE feeds ADD COLUMN ignore_http_cache boolean default false
ALTER TABLE feeds ADD COLUMN fetch_via_proxy boolean default false
ALTER TABLE feeds ADD COLUMN proxy_url text default ''
ALTER TABLE feeds ADD COLUMN cookie text default ''
ALTER TABLE feeds ADD COLUMN ignore_entry_updates boolean default 'f'
```

That is a complete, battle-tested watermark/backoff design:
- **`checked_at`** = last attempt; **`next_check_at`** = when to try next. The dispatcher selects
  `WHERE next_check_at <= now()`, which turns scheduling into a single indexed range scan.
- **`etag_header` / `last_modified_header`** = HTTP conditional-request validators. On `304 Not Modified`
  you skip parsing entirely. **This is the cheapest incremental win available and is orthogonal to the DB.**
- **`parsing_error_count`** = consecutive-failure counter for exponential backoff.
- `UPDATE feeds SET next_check_at=now()` (quoted from `internal/storage/feed.go`) is the manual "crawl
  everything now" trigger.

Note: **there is no `last_seen_item_time` column.** Miniflux's watermark is *schedule-based*
(`next_check_at`) plus *content-based dedupe* (`hash`) — it does not track "newest item timestamp seen".
That is a deliberate choice: feeds are not guaranteed time-ordered (an old post can be edited and
re-surface), so a timestamp watermark would silently skip late-arriving items. **For a platform crawler
whose search results are time-sorted, a timestamp watermark is safe; for anything with backfill/late
edits, hash-based dedupe is the only correct option. Use both.**

Also confirmed: Miniflux uses a **content-addressed `icons` table** (quoted):
```sql
CREATE TABLE icons (
    id BIGSERIAL,
    hash text not null unique,
    mime_type text not null,
    content bytea not null,
    primary key (id)
);
```
Icons are stored **in the database as `bytea`, keyed by hash** — not on the filesystem. Relevant to §3.

## 2.2 Postgres idioms for incremental upsert

### `INSERT ... ON CONFLICT DO UPDATE ... WHERE excluded.x > t.x`
The `WHERE` on `DO UPDATE` is real and documented. From
<https://www.postgresql.org/docs/current/sql-insert.html> (quoted):

> "`condition` — An expression that returns a value of type `boolean`. **Only rows for which this
> expression returns `true` will be updated, although all rows will be locked when the `ON CONFLICT DO
> UPDATE` action is taken.** Note that `condition` is evaluated last, after a conflict has been identified
> as a candidate to update."

Two consequences that are easy to miss:
1. **All conflicting rows get locked even when the `WHERE` is false.** A "skip stale writes" guard still
   takes row locks — it avoids write amplification and trigger firing, not lock contention.
2. The docs' own example is exactly this idiom (quoted):
```sql
-- Don't update existing distributors based in a certain ZIP code
INSERT INTO distributors AS d (did, dname) VALUES (8, 'Anvil Distribution')
    ON CONFLICT (did) DO UPDATE
    SET dname = EXCLUDED.dname || ' (formerly ' || d.dname || ')'
    WHERE d.zipcode <> '21201';
```

Also documented (quoted): *"`ON CONFLICT DO UPDATE` guarantees an atomic `INSERT` or `UPDATE` outcome;
provided there is no independent error, one of those two outcomes is guaranteed, **even under high
concurrency**. This is also known as *UPSERT*."* And: *"For `ON CONFLICT DO UPDATE`, a `conflict_target`
**must** be provided."* Plus the determinism rule (quoted): *"`INSERT` with an `ON CONFLICT DO UPDATE`
clause is a 'deterministic' statement. This means that the command will not be allowed to affect any single
existing row more than once; a cardinality violation error will be raised when this situation arises."* —
**deduplicate your batch in Python before sending it, or a batch containing the same key twice errors out.**

Real production caveat (quoted): *"While `CREATE INDEX CONCURRENTLY` or `REINDEX CONCURRENTLY` is running
on a unique index, `INSERT ... ON CONFLICT` statements on the same table may unexpectedly fail with a
unique violation."*

### The `xmax = 0` trick to distinguish insert from update
From the pgsql-general mailing list, Fabio Ugo Venchiarutti (Ocado Technology), 2019-05-22 —
<https://www.postgresql.org/message-id/e56b433e-5781-65f5-228d-54681967ed88%40ocado.com> (quoted verbatim
including his own framing):

> "Here's my recipe for that:
> ```
> RETURNING
> /* whatever, */
> (xmax = 0) AS is_new_record
> ;
> ```
> I don't know if any of the hackers thought of a sleeker technique"

**Flag:** this is a widely-used community recipe, **not** documented/officially supported API. It works
because a row inserted by the current command has `xmax = 0` while an updated row has the locking
transaction id in `xmax`. Safe for a single-statement upsert; brittle under the kind of concurrent
lock-upgrade scenarios the same thread discusses. Since **PG 18** there is also `RETURNING WITH (OLD AS o,
NEW AS n)` (documented in the PG 18 INSERT page: *"for an `INSERT` with an `ON CONFLICT DO UPDATE` clause,
the old values may be non-`NULL`"*) which is the **supported** way to see both sides — but I did not verify
which PG version introduced `RETURNING WITH`, so **[UNVERIFIED — introduction version]**.

### Real SQL for the crawler
```sql
INSERT INTO crawl_item (platform, source_id, raw, content_hash, fetched_at)
VALUES ($1, $2, $3::jsonb, $4, now())
ON CONFLICT (platform, source_id) DO UPDATE
   SET raw          = EXCLUDED.raw,
       content_hash = EXCLUDED.content_hash,
       fetched_at   = EXCLUDED.fetched_at
 WHERE crawl_item.content_hash <> EXCLUDED.content_hash   -- don't rewrite identical payloads
RETURNING id, (xmax = 0) AS inserted;                      -- 'inserted' / 'updated'
```
The `content_hash <> EXCLUDED.content_hash` guard is the single highest-value line: it makes re-crawling an
unchanged item a pure index probe with no tuple rewrite, so `raw` (and its TOAST chunks) is never rewritten
and no dead tuples are generated. Combined with `RETURNING (xmax = 0)`, one round-trip tells you new vs
changed vs no-op.

### `RETURNING` privilege/visibility notes (quoted from the INSERT page)
> "Only rows that were successfully inserted or updated will be returned. For example, if a row was locked
> but not updated because an `ON CONFLICT DO UPDATE ... WHERE` clause *`condition`* was not satisfied, the
> row will not be returned."

So a guarded upsert **returns zero rows for unchanged items** — your Python must treat "no row returned" as
"unchanged", not as an error. This is a very common bug.

## 2.3 Is `MERGE` a good idea here? No — version and caveats

**Version support (verified by reading both doc versions):**
- PG 15 MERGE (`https://www.postgresql.org/docs/15/sql-merge.html`): synopsis has **no `RETURNING`**, and
  `WHEN` clauses are only `WHEN MATCHED` / `WHEN NOT MATCHED`. The page states explicitly (quoted):
  *"There is no `RETURNING` clause with `MERGE`. Actions of `INSERT`, `UPDATE` and `DELETE` cannot contain
  `RETURNING` or `WITH` clauses."*
- PG 18 MERGE (`https://www.postgresql.org/docs/current/sql-merge.html`): has `RETURNING WITH (OLD|NEW)`,
  `merge_action()`, and the `WHEN NOT MATCHED BY SOURCE` extension.

**So `MERGE ... RETURNING` requires PG 17+**, and `NOT MATCHED BY SOURCE` requires PG 17+ too. **[UNVERIFIED
— exact introduction version]**: the PG 15 page lacks it and the PG 18 page has it, so it landed in 16 or
17; I did not open the 16/17 pages to pin it.

**Concurrency caveats, verbatim from the PG 18 MERGE page:**
> "You should ensure that the join produces at most one candidate change row for each target row. In other
> words, a target row shouldn't join to more than one data source row. **If it does, then only one of the
> candidate change rows will be used to modify the target row; later attempts to modify the row will cause
> an error.** ... If the repeated action is an `INSERT`, this will cause a uniqueness violation, while a
> repeated `UPDATE` or `DELETE` will cause a cardinality violation ... **This differs from historical
> PostgreSQL behavior** of joins in `UPDATE` and `DELETE` statements where second and subsequent attempts
> to modify the same row are simply ignored."

> "The order in which rows are generated from the data source is indeterminate by default. A
> *`source_query`* can be used to specify a consistent ordering, if required, **which might be needed to
> avoid deadlocks between concurrent transactions**."

> "When `MERGE` is run concurrently with other commands that modify the target table, the usual transaction
> isolation rules apply ... You may also wish to consider using `INSERT ... ON CONFLICT` as an alternative
> statement which offers the ability to run an `UPDATE` if a concurrent `INSERT` occurs. **There are a
> variety of differences and restrictions between the two statement types and they are not
> interchangeable.**"

The critical semantic difference for a crawler: **`ON CONFLICT` handles the concurrent-insert race; `MERGE`
does not.** MERGE decides MATCHED/NOT MATCHED from a snapshot join, so two concurrent transactions can both
see "NOT MATCHED" and both INSERT → unique violation. `ON CONFLICT` is documented to guarantee an atomic
outcome "even under high concurrency."

**Verdict: use `INSERT ... ON CONFLICT DO UPDATE`.** MERGE buys nothing here (you don't need
`NOT MATCHED BY SOURCE` for upserting crawl batches), costs you PG-version constraints for `RETURNING`,
and is weaker under concurrency. MERGE *is* the right tool for a different job you may want later:
**reconciling full-snapshot listings** (delete items that vanished from a source) via
`WHEN NOT MATCHED BY SOURCE THEN ...`. Keep it in reserve for that.

## 2.4 Designing the high-water-mark table

Do **not** put the watermark on the same table as the items (it would serialise every crawl on one hot row
and mix scheduler state into content). Use a dedicated table:

```sql
CREATE TABLE crawl_state (
    platform          text        NOT NULL,
    source_kind       text        NOT NULL,   -- 'search' | 'user' | 'feed' | 'detail'
    source_key        text        NOT NULL,   -- keyword / user id / feed url
    -- watermark: newest item time successfully persisted
    last_item_time    timestamptz,
    -- opaque platform cursor (page token, offset, max_cursor) for resumable pagination
    last_cursor       jsonb       NOT NULL DEFAULT '{}'::jsonb,
    -- scheduling (the miniflux pattern)
    last_run_at       timestamptz,
    next_run_at       timestamptz NOT NULL DEFAULT now(),
    last_success_at   timestamptz,
    consecutive_errors int        NOT NULL DEFAULT 0,
    last_error        text,
    -- HTTP conditional-request validators
    etag              text,
    last_modified     text,
    enabled           boolean     NOT NULL DEFAULT true,
    PRIMARY KEY (platform, source_kind, source_key)
);

-- the dispatcher's only query
CREATE INDEX crawl_state_due_idx ON crawl_state (next_run_at) WHERE enabled;
```

Design rules, each grounded in something above:
1. **`(platform, source_kind, source_key)` as PK** — a crawler's identity is the *query*, not the platform.
   The same keyword crawled via `search` and via `user` are different cursors.
2. **`last_cursor jsonb`** because cursors are platform-specific and shape-shifting (Douyin's `max_cursor`,
   Bilibili's `offset`, XHS's `xsec_token`). A `text` column forces you to invent an encoding; `jsonb`
   absorbs it. The `-` operator warning from §1.3 applies — never use bare `-`.
3. **`next_run_at` + partial index `WHERE enabled`** — makes the scheduler a single indexed range scan
   (`SELECT ... WHERE enabled AND next_run_at <= now() ORDER BY next_run_at LIMIT n`), which is the
   miniflux dispatcher pattern.
4. **Separate `last_run_at` from `last_success_at`.** A failed run must advance `last_run_at` (so you don't
   hammer the platform) but must **not** advance the watermark. Conflating them is the classic data-loss
   bug: after a failure you resume from a watermark that includes items you never persisted.
5. **Advance the watermark only after the transaction commits.** With the `ON CONFLICT` upsert above,
   write items and update `crawl_state.last_item_time` in **one transaction**:
   ```sql
   BEGIN;
     INSERT INTO crawl_item (...) VALUES (...) ON CONFLICT ... ;
     UPDATE crawl_state
        SET last_item_time = GREATEST(COALESCE(last_item_time, $new_max), $new_max),
            last_cursor    = $cursor,
            last_success_at = now(),
            consecutive_errors = 0,
            next_run_at    = now() + $interval
      WHERE platform=$1 AND source_kind=$2 AND source_key=$3;
   COMMIT;
   ```
   `GREATEST` prevents a late-arriving older item from rewinding the watermark. Note PG's `GREATEST`
   **ignores NULLs** (returns the non-null arg), so the `COALESCE` is belt-and-braces.
6. **`consecutive_errors` drives backoff** (miniflux's `parsing_error_count`): `next_run_at = now() +
   LEAST(base * 2^consecutive_errors, cap)`. For your flaky-VPN scenario this is the mechanism that stops a
   dead VPN from producing a tight retry loop. Combine with the required 2–3 in-request retries: retry
   **within** a run for transient errors (2–3 attempts with backoff+jitter), and let
   `consecutive_errors`/`next_run_at` handle whole-run failures.

---

# 3. Media file management

## 3.1 Immich — hash **and** original filename, path stored absolute, dedupe by partial unique index

Read directly from `server/src/schema/tables/asset.table.ts` (branch `main`). The decorators are the schema
(schema-first TS via `@immich/sql-tools`); quoted:

```ts
@Table('asset')
// Checksums must be unique per user and library
@Index({
  name: ASSET_CHECKSUM_CONSTRAINT,
  columns: ['ownerId', 'checksum'],
  unique: true,
  where: '"libraryId" IS NULL',
})
@Index({
  columns: ['ownerId', 'libraryId', 'checksum'],
  unique: true,
  where: '"libraryId" IS NOT NULL',
})
...
@Index({ columns: ['originalPath', 'libraryId'] })
@Index({ name: 'asset_originalFilename_trigram_idx', using: 'gin',
         expression: 'f_unaccent("originalFileName") gin_trgm_ops' })
```

Key columns (quoted):
```ts
  @Column() originalPath!: string;
  @Column({ type: 'bytea', index: true }) checksum!: Buffer; // sha1 checksum
  @Column({ enum: asset_checksum_algorithm_enum }) checksumAlgorithm!: ChecksumAlgorithm;
  @Column({ index: true }) originalFileName!: string;
  @Column({ type: 'uuid', nullable: true, index: true }) duplicateId!: string | null;
  @ForeignKeyColumn(() => LibraryTable, ...) libraryId!: string | null;
```
`ASSET_CHECKSUM_CONSTRAINT` is defined in `server/src/utils/database.ts` (quoted):
```ts
export const ASSET_CHECKSUM_CONSTRAINT = 'UQ_assets_owner_checksum';
export const isAssetChecksumConstraint = (error: unknown) =>
  (error as PostgresError)?.constraint_name === ASSET_CHECKSUM_CONSTRAINT;
```

**Answers to the brief's questions:**
- **Path storage:** yes — `originalPath` (absolute-ish, with an index on `(originalPath, libraryId)`),
  **plus** the human-readable `originalFileName` (with a **trigram GIN index** for search), **plus** the
  `checksum` in a dedicated indexed `bytea` column.
- **Hash algorithm:** the source comment says **`// sha1 checksum`**, and there is a
  `checksumAlgorithm` enum column so the algorithm is recorded per-row rather than assumed.
  **`ChecksumAlgorithm { sha1File='sha1', sha1Path='sha1-path' }`** confirms it — `sha1Path` being the SHA-1
  of `'path:' + <file path>`, used for external libraries and marked **deprecated** in-source.
  **[UNVERIFIED by me]** — I could not read `crypto.repository.ts` to see the actual `createHash(...)` call
  (repeated empty responses; the file is real, it returned HTTP 200 with an empty body). My sub-researcher
  did read it and reports `hashSha1`/`hashFile` both `createHash('sha1')`, with `hashSha256` present but
  used for JWT rather than file checksums. The `// sha1 checksum` comment, the `ChecksumAlgorithm` enum, and
  the `bytea` column type are what I read first-hand.
- **Checksum is stored as `bytea`, not hex `text`.** This is a deliberate 2x saving. Miniflux made the
  identical change on an expression index, and said so (quoted from `migrations.go`): *"Index the raw
  SHA-256 digest (32 bytes) instead of its hex text encoding (64 bytes) to roughly halve this index on
  disk."* **Two independent projects converged on raw-digest `bytea`.** Strong signal — do this.
- **Duplicate handling:** three mechanisms.
  1. **Partial unique indexes** enforce "one checksum per owner" — split into two because the uniqueness
     scope differs for uploaded assets (`libraryId IS NULL`) vs external libraries (`libraryId IS NOT
     NULL`). A single `unique(ownerId, checksum)` would wrongly forbid the same photo existing in a
     library and in uploads.
  2. **Unique violation is swallowed, not raised** — `getKyselyConfig` (quoted): `if (isAssetChecksumConstraint(event.error)) { return; }`. So a duplicate upload is a **silent no-op**, detected by constraint name.
  3. **A separate duplicate-detection job** groups near-duplicates for user resolution.
     `server/src/services/duplicate.service.ts` (quoted excerpts): `getDuplicates(auth)`, `resolve(auth, dto)`
     with `duplicateIds = dto.groups.map(({ duplicateId }) => duplicateId)`,
     `resolveGroup(...)` taking `keepAssetIds`/`trashAssetIds`, and jobs
     `handleQueueSearchDuplicates` / `handleSearchDuplicates`. It assigns
     `asset.duplicateId ?? duplicateIds.shift() ?? this.cryptoRepository.randomUUID()` — i.e. duplicates
     **point at a shared group id**; they are *linked and trashable*, not physically deleted.
- **`asset_file` table** (read from `asset-file.table.ts`, quoted): one asset → many derived files:
  ```ts
  @Table('asset_file')
  @Unique({ columns: ['assetId', 'type', 'isEdited'] })
  export class AssetFileTable {
    @ForeignKeyColumn(() => AssetTable, { onDelete: 'CASCADE', onUpdate: 'CASCADE' }) assetId!: string;
    @Column() type!: AssetFileType;      // original / preview / thumbnail / encoded_video
    @Column() path!: string;
    @Column({ type: 'boolean', default: false }) isProgressive!: boolean;
    @Column({ type: 'boolean', default: false }) isTransparent!: boolean;
  }
  ```
  So: **the manifest is a table**, not a sidecar file. `asset` holds identity+integrity (checksum,
  originalPath, originalFileName); `asset_file` holds one row per physical derivative with its own `path`.
  **This is exactly the shape a content collector needs** — keep the original plus generated thumbnails /
  transcodes, each addressable.

**The absolute-path trap — NOW VERIFIED from Immich's own docs.** I initially flagged this as unverified;
I later read both pages first-hand and the trap is documented by the project itself. From
`docs/docs/administration/backup-and-restore.md` (quoted verbatim):

> "Immich stores [file paths](https://github.com/immich-app/immich/discussions/3299) and user metadata in
> the database. **It does not scan the library folder, so database backups are essential.**"

And the concrete failure mode, from `docs/docs/features/libraries.md` (quoted verbatim):

> "If you add metadata to an external asset in any way (i.e. add it to an album or edit the description),
> that metadata is only stored inside Immich and will not be persisted to the external asset file. **If you
> move an asset to another location within the library all such metadata will be lost upon rescan. This is
> because the asset is considered a new asset after the move. This is a known issue** and will be fixed in
> a future release."

Plus the container-coupling consequence, same page (quoted verbatim):

> "NOTE: We have to use the `/mnt/media/christmas-trip` path and not the `/mnt/nas/christmas-trip` path
> since **all paths have to be what the Docker containers see**."

**This is the single most transferable lesson in §3.** Because Immich persists *absolute* paths, identity is
tied to location: move the file and the DB row is orphaned (metadata lost, re-imported as new), and the
stored path only means anything under one specific mount topology. PhotoPrism's root-id + relative-path
split (§3.2) is immune to exactly this. See §3.3 for the fix.

**Additional detail on Immich's duplicate mechanisms (read first-hand from `server/src/enum.ts`):**
`AssetFileType { FullSize='fullsize', Preview='preview', Thumbnail='thumbnail', Sidecar='sidecar',
EncodedVideo='encoded_video' }` — note **there is no `original` member**: the original lives on the `asset`
row as `originalPath`, not in `asset_file`. And `ChecksumAlgorithm { sha1File='sha1', sha1Path='sha1-path' }`
where `sha1Path` is documented in-source as the SHA-1 of `'path:' + <file path>`, used for external
libraries and marked **deprecated**.

**Two distinct duplicate mechanisms — do not conflate them:**
1. **Exact-byte dedup at upload** — SHA-1 checksum + unique index → the upload is **rejected**.
2. **Visual similarity via ML embeddings** — the separate `AssetDetectDuplicates` job (`duplicateDetection`
   queue) searches `{ assetId, embedding, maxDistance, type, userIds }`, gated on
   `isDuplicateDetectionEnabled = isSmartSearchEnabled(ml) && ml.duplicateDetection.enabled`. **Zero checksum
   involvement.** It groups results by assigning a shared `duplicateId` UUID and **trashes** the losers
   (`AssetStatus.Trashed`).
   There is **no `asset_duplicate` join table** — the grouping is the `duplicateId` UUID column.
   *Design relevance:* "same bytes" (dedupe) and "looks the same" (grouping) are genuinely different
   features with different UX — reject vs. group-and-resolve. Don't build one and call it the other.

Immich's default storage template (from `server/src/dtos/config.dto.ts`) is
`{{y}}/{{y}}-{{MM}}-{{dd}}/{{filename}}` with **`enabled: false`** — i.e. human-readable, not hash-based, by
default; `hashVerificationEnabled: true`. Name collisions in a template path get `+1`/`+2` suffixes.
**[UNVERIFIED]** — I did not re-read `storage-template.service.ts`/`config.dto.ts` myself; this comes from
my media sub-researcher, whose other numeric claims I *did* re-verify (`canonical.go`, `mediafile.go`, the
docs quotes) all held up.

## 3.2 PhotoPrism — original name **and** hash, but uniqueness is on **path**, not hash

Read from `internal/entity/file.go` (branch `develop`), GORM struct tags (quoted):

```go
	FileUID            string `gorm:"type:VARBINARY(42);unique_index;" json:"UID"`
	FileName           string `gorm:"type:VARBINARY(1024);unique_index:idx_files_name_root;" json:"Name"`
	FileRoot           string `gorm:"type:VARBINARY(16);default:'/';unique_index:idx_files_name_root;" json:"Root"`
	OriginalName       string `gorm:"type:VARBINARY(755);" json:"OriginalName"`
	FileHash           string `gorm:"type:VARBINARY(128);index" json:"Hash"`
	FileSize           int64  `json:"Size"`
	FileMime           string `gorm:"type:VARBINARY(64)" json:"Mime"`
	FilePrimary        bool   `gorm:"index:idx_files_photo_id;" json:"Primary"`
```

And the photo↔file relationship (quoted):
```go
	PhotoID            uint   `gorm:"index:idx_files_photo_id;" json:"-"`
	PhotoUID           string `gorm:"type:VARBINARY(42);index;" json:"PhotoUID"`
```

**Answers:**
- A photo (`photos`) has many files (`files`), joined by `PhotoID`/`PhotoUID`, with `FilePrimary` marking
  the representative one. Same one-to-many shape as immich's `asset`/`asset_file`.
- **`FileHash` is a plain non-unique index**, not unique. The **unique** index is
  `idx_files_name_root` on **`(FileName, FileRoot)`** — i.e. PhotoPrism dedupes on **path**, and uses the
  hash only for *finding* duplicates. This is the opposite of immich. Duplicates are expected and recorded
  separately (there is a `duplicates` table; Immich's equivalent is the `duplicateId` UUID column).
- **Both `FileName` (path) and `OriginalName` (human name) are kept**, exactly like immich's
  `originalPath` + `originalFileName`. Two independent large projects agree: **store both.**
- **There is no `file_path` column** — the path is `FileRoot` + `FileName`. `FileRoot` is a short
  `VARBINARY(16)` **logical root identifier** (`/` = originals, plus `import`/`sidecar`/`samples`), *not* a
  filesystem path; `mediafile.go` resolves root → configured absolute dir at read time via
  `PathNameInfo()`, and `RelPath()` **strips the configured root off the front** before persistence.

**Hash algorithm — VERIFIED first-hand, and it is the non-obvious finding.** Read from
`internal/photoprism/mediafile.go` (branch `develop`, quoted verbatim):

```go
// Hash returns the SHA1 hash of a media file.
func (m *MediaFile) Hash() string {
	if len(m.hash) == 0 {
		m.hash = fs.Hash(m.FileName())
	}
	return m.hash
}

// Checksum returns the CRC32 checksum of a media file.
func (m *MediaFile) Checksum() string {
	if len(m.checksum) == 0 {
		m.checksum = fs.Checksum(m.FileName())
	}
	return m.checksum
}
```

So **PhotoPrism uses two different hashes for two different jobs**: SHA-1 (`Hash()`) for dedup/identity and
**CRC32 (`Checksum()`) for the on-disk canonical filename**. The canonical name is built from the *CRC32*,
not the SHA-1 — verified verbatim from `pkg/fs/canonical.go`:

```go
// CanonicalName returns a canonical name based on time and CRC32 checksum.
func CanonicalName(date time.Time, checksum, pattern string) string {
	if len(checksum) != 8 {
		checksum = "EEEEEEEE"
	} else {
		checksum = strings.ToUpper(checksum)
	}
	if pattern == "" {
		pattern = "20060102_150405_"
	}
	return date.Format(pattern) + checksum
}
```

with the caller in `mediafile.go` (quoted): `return fs.CanonicalName(m.DateCreated(), m.Checksum(), pattern)`
— i.e. **`m.Checksum()` = CRC32**. `NonCanonical()` in the same file confirms the shape by rejecting any
basename whose length is not 22 or 24 and which does not contain exactly two underscores ⇒
`YYYYMMDD_HHMMSS_XXXXXXXX` (~22 chars, 8 uppercase hex from CRC32). **This is easy to conflate and worth
not getting wrong:** a CRC32 is only 32 bits, so it is *not* collision-resistant — it is a filename
disambiguator, while the SHA-1 does the real identity work.

**Dedup-on-index flow** (from `internal/photoprism/index_mediafile.go`, per my sub-researcher): look up by
`(file_name, file_root)` first; if not found and the file is in originals, compute SHA-1 and query
`First(&file, "file_hash = ?", fileHash)`; if the hash matches and the file exists → `entity.AddDuplicate(...)`
and `result.Status = IndexDuplicate` (**not** indexed as a real photo). If the old file is gone, the row is
**renamed to take over** the new path — preserving identity across a move. There is an explicit
`lockFileHash` mutex "so concurrent workers cannot ... index byte-identical files twice".
**[UNVERIFIED]** — this paragraph is from my sub-researcher's read of `index_mediafile.go`, which I did not
re-read myself. The `Hash()`/`Checksum()`/`CanonicalName` quotes above **I did** verify first-hand.

PhotoPrism keeps sidecars **filesystem-first** (`RootSidecar`, `FileSidecar` flag, YAML sidecars that can
restore a photo's UID during indexing), whereas Immich keeps them **DB-first** (`AssetFileType.Sidecar` row +
`SidecarWrite` job). Two opposite answers to the same problem. [UNVERIFIED] — sidecar details from my
sub-researcher, not re-read by me.

**The on-disk `originals/YYYY/MM/` folder layout remains [UNVERIFIED]** — I verified the canonical *filename*
format and root-relative storage, but never found the code materializing dated folders. Do not cite that
layout as verified.

## 3.3 Content-addressed vs human-readable: the real tradeoff

| | Hash-named (content-addressed) | Original filename (path in DB) |
|---|---|---|
| Dedup | **Free** — identical bytes ⇒ identical name ⇒ collision is the constraint | Requires an explicit hash column + unique index + comparison logic |
| Human-readable on disk | No; needs a manifest to map back | Yes |
| Rename/move of library root | **Immune** — the name is derived from content, not location | Breaks every stored path |
| Manifest required | Yes (DB row or sidecar mapping hash→item) | The path *is* the manifest |
| Re-download of same asset | Idempotent write, or skip if file exists | Overwrites or duplicates |
| Security | Must path-validate; a hash is safe by construction | Must sanitize `../../` and platform-supplied names |
| Partial/corrupt file | **Silently poisons** the hash name if you write before verifying | Filename still tells you which item it was |

**Neither project chooses purely one way — and that is the finding.** Immich: checksum `bytea` unique-per-owner
**for dedupe** + `originalPath` + `originalFileName` **for humans**. PhotoPrism: SHA-1 indexed **for finding**
duplicates + `(FileName, FileRoot)` unique **for identity** + `OriginalName` **for humans**.

**The relative-vs-absolute split is the decisive, doc-verified difference.** PhotoPrism stores a **root
identifier + root-relative path** (`file_root` = `/`|`import`|`sidecar`|`samples`, plus `file_name`), and
resolves the absolute directory from config at read time; `RelPath()` strips the configured root before
persisting. Immich stores the **absolute** `originalPath`, and its own docs admit the cost (quoted in §3.1):
*"It does not scan the library folder, so database backups are essential"* and *"If you move an asset to
another location within the library all such metadata will be lost upon rescan... **This is a known issue**"*.
⇒ **PhotoPrism's (root-id + relative path + hash) triple survives a remount; Immich's absolute path does
not.** This is the load-bearing lesson for your own schema.

**Recommended for a content collector** (both, with clear roles):
- `content_sha256 bytea` — **integrity + dedupe key**, unique where the item is the same asset. Use
  `bytea`, not hex (immich + miniflux both do).
- `storage_root text` + `storage_path text` (**relative**) — **where it actually is**. Splitting root from
  path (PhotoPrism's `FileRoot`/`FileName`) means changing a mount point or migrating to object storage is a
  config change, not a data migration. **Do not store absolute paths.**
- `original_name text` — **display**, never used to locate the file.
- Physical layout: `<root>/<sha256[0:2]>/<sha256[2:4]>/<sha256>.<ext>` — content-addressed on disk gives
  dedup for free and is immune to root moves; the DB row is the manifest.
- **Write to a temp name, verify the hash, then `os.replace()`** into the content-addressed path. This is
  the fix for the "partial file poisons the hash name" row above: an interrupted download must never
  occupy the final hash-named path.
- **Use a real hash for identity, not a truncated/weak one.** PhotoPrism's CRC32-in-filename is a
  disambiguator only (32 bits, not collision-resistant); SHA-1/SHA-256 does the identity work. If you take
  only one lesson from the CRC32 finding: **keep the field that identifies content separate from the field
  that names the file.**

**Sidecar vs manifest:** a sidecar (`.json` next to the media) duplicates state that the DB already holds
and can desync on crash. Both real projects use **the database as the manifest** (`asset_file`, `files`
tables). Do the same — one source of truth. (Miniflux even puts icon bytes *in* the DB as `bytea`, §2.1,
though that is not advisable for video.)

## 3.4 Object storage: when is local-path-in-DB a trap?

**The trap is not "storing a path". It is storing a path *plus* assuming filesystem semantics in code** —
`os.path.exists`, `shutil.move`, `open()`, `os.listdir`, path globbing, and `..` joins scattered through
the download/serve/cleanup paths. Every one of those becomes a rewrite when you add S3/COS. The migration
itself is the easy part if and only if all filesystem access is behind one interface.

**The abstraction pattern — `fsspec` (verified):**
- Repo: <https://github.com/fsspec/filesystem_spec> — **1,365 stars**, last push 2026-09-29,
  **BSD-3-Clause**, not archived (api.github.com/repos/fsspec/filesystem_spec).
- PyPI: **2026.9.0**, released **2026-09-18**, `requires_python >=3.10` (pypi.org/pypi/fsspec/json).
- Actively maintained (push 3 days before the fsspec release; version scheme is CalVer `YYYY.M.P`).

fsspec gives one API (`open`, `ls`, `rm`, `mv`, `exists`, `glob`) across local, S3, GCS, ABFS, HTTP, and
more, so switching from local disk to S3/COS is a **`fsspec.filesystem(...)` argument change** rather than a
code migration. Its own description is *"A specification that python filesystems should adhere to."*
**[UNVERIFIED]**: that a specific COS (Tencent/阿里) driver exists in-tree — I verified fsspec's identity,
activity and stability but **did not read its implementation list**, so I am not asserting a specific COS
backend. Guard against that: object stores differ on the operations that matter here (e.g. **there are no
real atomic renames on S3** — `mv` is copy+delete), so any code path relying on `os.replace()` atomicity
will **not** port cleanly. Design the finalize step to be "upload temp key → verify → server-side copy →
delete temp", and accept that it is not atomic.

**Django's `FileField.storage`** is the other canonical precedent: a `Storage` object (`open`/`save`/`delete`/
`exists`/`url`) attached to the field, with `DEFAULT_FILE_STORAGE` swappable. django/django is **91,239
stars, BSD-3-Clause, pushed 2026-10-01** (api.github.com/repos/django/django) — verified as a real, live
project, and the `storage` parameter on `FileField` is long-standing documented API. **[UNVERIFIED]** I did
not fetch the Django docs page for `FileField.storage` in this session, so I am citing the pattern's
existence and the repo's liveness, not quoting its docs.

**When local-path-in-DB is genuinely fine:** single machine (your case), files on the same host, no
multi-node serving, and — the deciding factor — **all access funnelled through one module**. Then moving to
S3/COS later is contained. **When it is a trap:** if media paths are stored as *absolute* paths
(`F:\media\...` or `/mnt/photos/...`) and used directly everywhere, and especially if they're baked into
**rows that also hold content metadata** — then changing the storage backend means rewriting rows, and
changing the mount point means the DB lies. Mitigation, cheap to adopt now:
- Store **relative** paths (`ab/abcdef….jpg`) + a **root id**, not absolute paths. Miniflux's `FileRoot`/
  `FileName` split in PhotoPrism is precisely this idea (`FileRoot` is a short `VARBINARY(16)`).
- A `storage_backend` column (or root table) so one DB can span local + remote during migration.
- Never let a platform-supplied string reach the filesystem unsanitized.

**A project that visibly went through the migration:** **[UNVERIFIED]**. I did not find and read a
first-hand account of a specific project migrating local→S3/COS. I am not going to cite one I did not read.

---

# 4. Scheduling for a single machine

## 4.1 APScheduler — use 3.11.3, NOT 4.x

**Version reality (from `https://pypi.org/pypi/APScheduler/json`, all six 4.x releases listed):**

| Version | Uploaded |
|---|---|
| 3.9.1.post1 | 2022-11-11 |
| **4.0.0a1** | **2022-08-16** |
| 4.0.0a2 | 2022-09-04 |
| 4.0.0a3 | 2023-10-01 |
| 4.0.0a4 | 2023-11-13 |
| 4.0.0a5 | 2024-05-15 |
| **4.0.0a6** | **2025-04-27** |
| 3.11.0 | 2024-11-24 |
| 3.11.1 | 2025-10-31 |
| 3.11.2 | 2025-12-22 |
| **3.11.3** | **2026-06-28** |

**Every 4.x release is an alpha. There is no beta, no rc, no final.** `info.version` on PyPI is
**`3.11.3`**, `requires_python >=3.8` (so a plain `pip install APScheduler` resolves to **3.11.3** — the
alpha suffix excludes it from default resolution). 4.0 has been in alpha for **over three years**
(2022-08-16 → 2025-04-27), and the newest alpha is **older than the newest 3.x stable**.

The changelog (`docs/versionhistory.rst` on `master`) confirms: its top section is literally
`**UNRELEASED**`, then `**4.0.0a6**`, then a run of `**BREAKING**` entries, e.g. quoted:
> "- **BREAKING** Refactored `AsyncpgEventBroker` to directly accept a connection string..."
> "- **BREAKING** Changed most attributes in `Task` and `Schedule` classes to be read-only"
> "- **BREAKING** Replaced the data store `lock_expiration_delay` parameter with a new scheduler-level parameter, `lease_duration`"

Repeated `BREAKING` markers between alphas mean the API is still moving. The UNRELEASED section also shows
4.x still fixing core bugs, e.g. quoted: *"Fixed schedules staying stuck when the scheduler holding them
died without releasing them ... (`#1053`)"* and *"Fixed jobs that were being run when the scheduler was
gracefully stopped being left in an acquired state (`#946`)"*.

**Verdict: pin `APScheduler==3.11.3`.** 4.x's one genuinely attractive feature for you —
**lease-based coordination so multiple processes don't double-run a schedule** (`extend_acquired_schedule_leases`,
`extend_acquired_job_leases`, quoted above) — is exactly the problem §4.3 says you must not rely on
scheduling to solve anyway, and it is alpha software. Do not take an alpha scheduler into production for a
single-machine app where the alternative is trivial.

## 4.2 The multi-worker pitfall — verbatim, from the FAQ

The warning is **not** in the userguide (I searched the 3.x userguide: matches exist only for `coalesce`,
`max_instances`, "multiple triggers", "multiple CPU cores"). It is in **`docs/faq.rst`**, which I read at
source level from `https://raw.githubusercontent.com/agronholm/apscheduler/3.x/docs/faq.rst` (quoted
verbatim):

> **"How do I share a single job store among one or more worker processes?"**
>
> **"Short answer: You can't."**
>
> "Long answer: Sharing a persistent job store among two or more processes will lead to incorrect scheduler
> behavior like **duplicate execution** or the scheduler missing jobs, etc. This is because APScheduler
> does not currently have any interprocess synchronization and signalling scheme that would enable the
> scheduler to be notified when a job has been added, modified or removed from a job store."
>
> "Workaround: Run the scheduler in a dedicated process and connect to it via some sort of remote access
> mechanism like RPyC, gRPC or an HTTP server. The source repository contains an example of a RPyC based
> service that is accessed by a client."

And on uWSGI (quoted): *"uWSGI employs some tricks which disable the Global Interpreter Lock and with it, the
use of threads which are vital to the operation of APScheduler. To fix this, you need to re-enable the GIL
using the `--enable-threads` switch."* ... *"Also, assuming that you will run more than one worker process
(as you typically would in production), you should also read the next section."*

**This is the single most important fact in this section: with `uvicorn --workers N` or
`gunicorn -w N`, every worker starts its own `BackgroundScheduler`, and there is no locking — so a daily
crawl fires N times concurrently.** The failure is silent and looks like "we got rate-limited for no
reason" or "everything is duplicated".

**The three real solutions, ranked for your case:**
1. **Run one process (`uvicorn --workers 1`) and let the scheduler + in-process queue live in it.** Correct
   and simplest, and it matches the constraint that you already have an in-process task queue. The API is
   small; a single worker is a legitimate architecture for a self-hosted single-user tool. This is the
   recommendation.
2. **Run the scheduler in a separate process** that talks to the app over HTTP — which is precisely
   APScheduler's own documented workaround ("an HTTP server"), and also what a cron entry would do.
3. **`max_instances` is NOT a multi-process fix.** Documented meaning (3.x userguide, quoted verbatim):
   > "By default, only one instance of each job is allowed to be run at the same time. This means that if
   > the job is about to be run but the previous run hasn't finished yet, then the latest run is considered
   > a misfire. It is possible to set the maximum number of instances for a particular job that the
   > scheduler will let run concurrently, by using the `max_instances` keyword argument when adding the job."

   `max_instances` is enforced **per scheduler instance, in memory**. With N workers you get N separate
   schedulers each honouring `max_instances=1`, i.e. N concurrent runs. **It is a within-process
   overlap guard, not a distributed lock.**

**Postgres advisory locks as the worker-count-agnostic backstop.** If you must run multiple workers, guard
the job body itself rather than trusting the scheduler:

```sql
-- non-blocking: returns false immediately if another session holds it
SELECT pg_try_advisory_lock(hashtext('crawl:douyin:search:keyword'));
```
```python
# try/finally is mandatory — the lock is session-scoped and leaks if not released
# or if the connection returns to a pool
acquired = await session.scalar(text("SELECT pg_try_advisory_lock(hashtext(:k))"), {"k": key})
if not acquired:
    return  # another worker is on it
try:
    ...
finally:
    await session.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": key})
```
Caveats to respect: advisory locks are **per-session**, so a pooled connection must not be returned to the
pool while holding one (release in `finally`, ideally use a dedicated connection); and
`pg_try_advisory_lock` is **not** released by transaction end (that's `pg_advisory_xact_lock`, which is the
safer choice if the whole job runs in one transaction — then the lock auto-releases on commit/rollback and
you cannot leak it). **Prefer `pg_advisory_xact_lock`/`pg_try_advisory_xact_lock` when the job is one
transaction**; that is strictly less error-prone than manual unlock. **[UNVERIFIED]** — I did not open the
PostgreSQL "Advisory Locks" doc page in this session, so the function names and their exact semantics are
from use, not from a URL I read here. Verify before relying on them.

Same reasoning applies to Celery beat: its docs are the ones that state the single-instance requirement
explicitly (below), and it is the same class of problem.

## 4.3 Jitter — verbatim documented guidance

`jitter` is documented on the **trigger API pages**, not the userguide. From
<https://apscheduler.readthedocs.io/en/3.x/modules/triggers/interval.html> (quoted verbatim):

> "**Parameters:** ... **jitter** (*int* | *None*) – delay the job execution by `jitter` seconds at most"
>
> "The `jitter` option enables you to add a random component to the execution time. This might be useful if
> you have multiple servers and don't want them to run a job at the exact same moment or if you want to
> prevent multiple jobs with similar options from always running concurrently:"
>
> ```python
> # Run the `job_function` every hour with an extra delay picked randomly between 0 and 120 seconds.
> sched.add_job(job_function, 'interval', hours=1, jitter=120)
> ```

The cron trigger page carries the same paragraph with the additional clause (per the docs search index)
"...**or if you want to prevent jobs from running at sharp hours**".

`jitter` is a real documented parameter on `IntervalTrigger` and `CronTrigger` (`jitter=None` default).

**Why this matters specifically for scraping** (this is the "avoid predictable bot timing" argument): a
crawl that fires at exactly `HH:00:00` every hour produces a machine-perfect inter-arrival distribution,
which is a trivially detectable signature, and it also concentrates your request burst at the same moment
as every other cron-style client on the internet — the thundering-herd problem. APScheduler's own docs give
the multiple-jobs-concurrently framing; the anti-detection framing is the same mechanism. **[UNVERIFIED]**
for the anti-bot-detection claim: I found and read no authoritative source stating "fixed scheduling is
fingerprintable". I am flagging that explicitly rather than dressing it up as cited fact — the *documented*
justification is concurrency/load spreading, and that justification alone is sufficient.

**Practical setting for this tool:** `jitter` on the order of **5–20% of the interval** (e.g. hourly crawl
→ `jitter=300` i.e. ±5 min). Combine at three levels: (a) `jitter` on the trigger, (b) randomized
inter-request delay between pages, (c) `next_run_at` backoff with added jitter on the `crawl_state` row
(§2.4) so failures don't re-converge.

**Per-attempt jitter for your transient-VPN retries:** use exponential backoff with jitter, not fixed
sleeps. Standard formula ("full jitter"): `sleep = random.uniform(0, min(cap, base * 2**attempt))` for
attempt in 0..2 (3 attempts total). Without jitter, N concurrent tasks that failed together retry
together, hammering the VPN the moment it recovers.

## 4.4 Comparison table

Stars are from the GitHub API (captured this session); releases/dates from the PyPI JSON API.

| Option | Stars | Latest release | Date | License | Verdict for a single-machine FastAPI app with an existing in-process queue + optional Redis |
|---|---|---|---|---|---|
| **APScheduler 3.11.3** | 7,642 | **3.11.3** | **2026-06-28** | MIT | ✅ **Recommended.** Pure-Python, no broker, no extra process, runs in-process alongside FastAPI via `AsyncIOScheduler`. `CronTrigger` + documented `jitter`. Requires `--workers 1` (see §4.2). |
| APScheduler 4.x | 7,642 | 4.0.0a6 | 2025-04-27 | MIT | ❌ **Alpha since 2022-08; no beta/rc/final.** Repeated BREAKING changes between alphas. Do not ship. |
| **arq** | 3,013 | 0.28.0 | 2026-04-16 | MIT | ⚠️ **In "maintenance only mode"** per its own README (issue #510, opened 2025-10-18). Redis-only, async-native, **POSIX/Unix-only classifiers (no Windows)**. Conflicts with "optional Redis" — it mandates Redis. |
| **dramatiq** | 5,319 | 2.2.1 | 2026-09-02 | LGPL-3.0 | ✅ Actively maintained; `from dramatiq.brokers.redis import RedisBroker`. But it is a *worker* framework — you already have a queue, so it overlaps rather than composes. |
| **periodiq** (adds to dramatiq) | **30** (GitLab, not GitHub) | 0.14.0 | 2026-04-16 | LGPL-3.0 | ❌ Adds cron scheduling to dramatiq, but README says **"Single process"** and it is **SIGALRM-based → POSIX-only, will not work on Windows**. Canonical repo is **gitlab.com/bersace/periodiq**; `Bogdanp/dramatiq-periodiq` **does not exist**. |
| **Celery beat** | 28,929 | 5.6.3 | 2026-03-26 | NOASSERTION | ❌ **Three components** (broker + worker + beat) for one machine. Beat's schedule state defaults to a local **shelve** file (`celerybeat-schedule`, `celery.beat.PersistentScheduler`). High operational cost for the value. |
| **Cron / Windows Task Scheduler → internal HTTP endpoint** | n/a | n/a | n/a | n/a | ✅ **Strong pragmatic alternative.** Zero new dependencies, survives app restarts, OS-level logging, and the single-instance guarantee comes free from the OS. Cost: an authenticated endpoint, and schedule changes live outside the app (unless you generate the crontab). |

**Celery beat specifics, quoted from the docs:** running periodic tasks requires the broker, a worker
(`celery -A proj worker`) and beat (`celery -A proj beat`); `beat_schedule` is the default entry source; the
default scheduler is `celery.beat.PersistentScheduler` writing to a local **shelve** DB file
`celerybeat-schedule`. On the single-instance requirement the docs are explicit (quoted): *"You have to
ensure only a single scheduler is running for a schedule at a time, otherwise you'd end up with duplicate
tasks."* And on `worker -B`: the docs warn it **"isn't recommended for production use"**. On overlap
(quoted): *"Like with cron, the tasks may overlap if the first task doesn't complete before the next… use a
locking strategy to ensure only one instance can run at a time."* — Celery explicitly tells you to bring
your own lock, i.e. nothing above removes the need for §4.2's advisory lock. **[UNVERIFIED]** Celery's
license: PyPI metadata omits it and GitHub reports `NOASSERTION`; it is commonly BSD-3-Clause but I could
not confirm from a primary source.

## 4.5 Verdict

**Use `APScheduler==3.11.3` in-process, under a single uvicorn worker, with `CronTrigger` + `jitter`,
driving your existing in-process queue — and add a Postgres advisory lock inside each job body as a
belt-and-braces guard.**

Rationale, all evidence-backed:
- 4.x is alpha-only and has been for 3+ years; 3.11.3 is the current stable with an active release cadence
  (3.11.0 2024-11 → .1 2025-10 → .2 2025-12 → .3 2026-06).
- It adds **no** infrastructure. arq requires Redis (and is in maintenance-only mode, POSIX-only); dramatiq
  requires adopting its broker+worker and duplicates the queue you already have; periodiq is single-process
  POSIX-only and needs dramatiq; Celery requires three moving parts and a shelve file.
- `max_instances` gives within-process overlap protection; the FAQ is unambiguous that cross-process
  coordination is unsupported ("Short answer: You can't"), so **run one worker**.
- If you'd rather not hold a scheduler in the web process at all, **cron / Task Scheduler hitting an
  authenticated internal endpoint** is a legitimate and arguably better choice here: it is one HTTP route
  you'd want anyway (manual "crawl now"), it inherits the OS's single-instance guarantee, and it survives
  app restarts without reconcile logic. This is also the same shape as APScheduler's own documented
  workaround ("Run the scheduler in a dedicated process and connect to it via ... an HTTP server").

**A note on your "optional Redis mode":** APScheduler 3.x needs no broker, so it does not conflict with an
optional-Redis design the way arq (Redis required) does. Keep the queue's Redis mode orthogonal to
scheduling; do not let the scheduler choice force Redis to be mandatory.

---

## Appendix: claims I could not verify

Flagged rather than guessed, as requested:

1. **PG version that introduced `STORED` generated columns** — docs describe the behaviour but I did not
   find a page stating PG 12. Only PG 18's virtual-default behaviour is doc-confirmed here.
2. **PG version that introduced `MERGE ... RETURNING` / `NOT MATCHED BY SOURCE`** — present in PG 18, absent
   in PG 15; I did not open 16/17 to pin it.
3. **PG version that introduced `RETURNING WITH (OLD|NEW)`** — documented in PG 18, introduction version unread.
4. **PostgreSQL advisory lock function names/semantics** — used from experience; the advisory-locks doc page
   was not fetched this session. Verify `pg_try_advisory_lock` vs `pg_try_advisory_xact_lock` before relying
   on the snippets in §4.2.
5. **Immich's actual hash call** — `crypto.repository.ts` returned empty on repeated attempts. Only the
   in-source `// sha1 checksum` comment and the `ChecksumAlgorithm` enum were read. *Partially resolved:*
   my sub-researcher read `hashSha1`/`hashFile` as `createHash('sha1')` and noted `hashSha256` exists but is
   for JWT, not file checksums. **[UNVERIFIED by me — second-hand.]**
6. ~~**PhotoPrism's hash algorithm**~~ — **NOW VERIFIED FIRST-HAND** (§3.2): `Hash()` = SHA-1 for dedup,
   `Checksum()` = CRC32 for the canonical filename, both quoted from `internal/photoprism/mediafile.go` and
   `pkg/fs/canonical.go`. **Still unverified:** the on-disk `originals/YYYY/MM/` folder layout — never found
   the code materializing dated folders.
7. ~~**An immich citation for the absolute-path trap**~~ — **NOW VERIFIED FIRST-HAND** (§3.1): quoted
   verbatim from Immich's own `backup-and-restore.md` and `libraries.md`, including the project's own
   "This is a known issue" wording. **Still open:** a named project that migrated local paths → S3/COS.
8. **A real project that stores a verbatim raw API response blob alongside typed columns** — searched, not
   found in anything I read. MediaCrawler and Miniflux both explicitly do *not*.
9. **fsspec COS/Tencent backend existence** — fsspec's identity/activity/license verified; backend list unread.
10. **Django `FileField.storage` docs quote** — repo liveness verified; the docs page was not fetched.
11. **Celery license** — NOASSERTION from GitHub, absent from PyPI; commonly BSD-3-Clause, unconfirmed.
12. **The "fixed scheduling is bot-fingerprintable" claim** — no authoritative source read. The documented
    `jitter` rationale (load/concurrency spreading) is verified; the anti-detection framing is inference and
    is labelled as such in §4.3.
13. **APScheduler's full `add_job()` signature** — the userguide is discursive; confirmed `trigger`,
    `max_instances`, `coalesce`, `misfire_grace_time`, `id`, `name`, `jitter` only. The API reference page
    was not fetched.
14. **Second-hand items from my media sub-researcher, not re-read by me** (its *numeric/verifiable* claims
    that I did re-check — `canonical.go`, `mediafile.go`, the two docs quotes — all held up exactly, which
    raises but does not establish confidence in the rest): PhotoPrism's `index_mediafile.go` dedup flow and
    `duplicates` table; PhotoPrism's sidecar/`RootSidecar` design; Immich's default storage template
    (`{{y}}/{{y}}-{{MM}}-{{dd}}/{{filename}}`, `enabled: false`); Immich's `AssetFileType`/
    `ChecksumAlgorithm` enum members; immich's `asset-media.service.ts` reject-and-return-duplicate flow
    (`AssetMediaStatus.DUPLICATE`); and the ML-embedding duplicate job's gating expression. Its report also
    notes a genuine in-source discrepancy: `asset.table.ts` carries a comment *"For all assets, each
    originalpath must be unique per user and library"* above a **non-unique** `@Index` — reported as found,
    unresolved.
15. **`docs/research/media-dedup-immich-photoprism.md`** is my sub-researcher's separate report in this
    workspace. Treat it as second-hand unless a claim is either quoted in §3 above with a URL or marked as
    first-hand-verified there.
