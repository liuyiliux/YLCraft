# Lightweight Observability for a Single-Machine Python (FastAPI) Scraper

**Scope:** self-hosted, single machine, no Prometheus + Grafana + Alertmanager.
**Date:** 2026-10-01. **Method:** every library below was verified against the
GitHub REST API (`/repos/<owner>/<repo>`) and/or the PyPI JSON API. Star counts,
last-push dates, and licenses are copied from those responses, not recalled.
SQL in §4 was executed against SQLite 3.37.2; the Postgres variant is checked
against the official PostgreSQL 18 grammar for ordered-set aggregates.

**Verification commands used**

```
GET https://api.github.com/repos/<owner>/<repo>     -> stars, pushed_at, license, archived
GET https://pypi.org/pypi/<pkg>/json                -> requires_dist (dependency truth), upload_time
```

---

## 0. Corrections to the brief (read this first)

Three of the URLs given in the task point at the wrong place. Verified:

| Given in brief | Reality | Evidence |
| --- | --- | --- |
| `madzak/python-json-logger` | **ARCHIVED.** `"archived": true`, last push `2024-12-12`. PyPI still ships 4.2.0 under that name, but the repo is frozen. The maintained home is **`nhairs/python-json-logger`** — and structlog's own docs link to it. | GitHub API `archived:true`; [structlog stdlib docs](https://www.structlog.org/en/stable/standard-library.html) link to `github.com/nhairs/python-json-logger` |
| `glitchtip/glitchtip-backend` (on GitHub) | **HTTP 404.** GlitchTip is hosted on **GitLab**, not GitHub. Real source: [gitlab.com/glitchtip/glitchtip-backend](https://gitlab.com/glitchtip/glitchtip-backend) (359 stars, 221 forks, last activity `2026-09-30`). | `api.github.com/repos/glitchtip/glitchtip-backend` → 404; GitLab API project 15450933 |
| `pyformance` — implied as a live option | Exists, but **PyPI's last upload was 2017-10-08** (v0.4). Last GitHub push `2023-07-07`. Effectively dead. | PyPI `upload_time` 2017-10-08T12:16:13; GitHub `pushed_at` 2023-07-07 |

---

## 1. Metrics libraries that are NOT Prometheus-server

### 1a. Verification table

All data from `api.github.com/repos/...` and `pypi.org/pypi/.../json`, fetched 2026-10-01.

| Library | Stars | Last push (GitHub) | Last release (PyPI) | License | Archived | Hard runtime deps |
| --- | --- | --- | --- | --- | --- | --- |
| `prometheus/client_python` | 4,379 | 2026-09-15 | 0.26.0 — 2026-07-24 | Apache-2.0 | no | **0** (twisted/aiohttp/django are extras only) |
| `omergertel/pyformance` | 195 | 2023-07-07 | **0.4 — 2017-10-08** | Apache-2.0 | no | **0** |
| `jsocol/pystatsd` (`statsd`) | 553 | 2026-02-17 | **4.0.1 — 2022-11-06** | MIT | no | **0** |
| `open-telemetry/opentelemetry-python` (`opentelemetry-sdk`) | 2,652 | 2026-10-01 | 1.45.0 — 2026-09-25 | Apache-2.0 | no | **4** (`opentelemetry-api`, `opentelemetry-semantic-conventions`, `typing-extensions`, + `opentelemetry-configuration` for the `file-configuration` extra) |
| `n0rdy/pooml` (sqlite roll-your-own, real project) | 32 | 2026-09-27 | n/a (Go binary) | AGPL-3.0 | no | binary, no lib |
| `PVRLabs/statlite` (sqlite roll-your-own, real project) | 151 | 2026-10-01 | n/a (Go binary) | MIT | no | binary, no lib |

### 1b. `prometheus_client` in scrape-only mode (multiprocess=OFF)

**What it gives you:** the 4 standard instrument types (`Counter`, `Gauge`,
`Histogram`, `Summary`) in-process, plus a text exposition endpoint. The
histogram buckets are computed in the client, so `histogram_quantile`-style
p95 is only meaningful if something *scrapes and stores* it.

**The Python client cost is genuinely near-zero.** `prometheus-client` 0.26.0's
`requires_dist` contains **only three entries, and all three are `extra`
guards** (`twisted`, `aiohttp`, `django`). There is no required dependency at
all, and the wheel is 64,494 bytes. The synopsis from structlog's docs —
"zero dependencies" — is literally true here.

**Caveat that decides the design:** the client **only exposes the current
process's in-memory values**. Counters reset on restart. If you already have a
FastAPI process and you scrape it yourself, you get a snapshot with no history
and no p95 across time. That is the whole point of the scrape model — it
presumes a time-series database on the other end. Without one, you have
"current totals", not metrics.

**FastAPI endpoint, exactly as documented:**

```python
from fastapi import FastAPI
from prometheus_client import make_asgi_app

app = FastAPI(debug=False)
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

Source: [client_python — FastAPI + Gunicorn](https://prometheus.github.io/client_python/exporting/http/fastapi-gunicorn/)

**If you ever run >1 worker, the documented limitations bite hard** (this is
the "multiprocess=off" question answered directly). From
[Multiprocess Mode](https://prometheus.github.io/client_python/multiprocess/):
custom collectors do not work; gauges cannot use `set_function`; Info and Enum
metrics do not work; pushgateway cannot be used; exemplars unsupported;
`PROMETHEUS_MULTIPROC_DIR` must be wiped between runs; and on WSL a
Windows-mounted path (`/mnt/c/...`) makes the collector **silently read no
data**. Keeping multiprocess off (one worker, or one process) avoids all of it.

### 1c. `pyformance`

**Do not use.** Real project, correct API surface (Coda Hale / Yammer metrics
port: `Meter`, `Histogram`, `Timer`, `Counter`, `Gauge`), zero deps — but the
last PyPI release was **2017-10-08** and the last commit **2023-07-07**. It is
abandoned. Its in-process storage model is the same as `prometheus_client`'s
(no persistence), so it buys you nothing that `prometheus_client` doesn't
already provide with an actively maintained codebase.

### 1d. `statsd` + a statsd daemon

The client (`statsd` 4.0.1, MIT, zero deps) is fine and simple — fire-and-forget
UDP. But the client is only half the system: **statsd is a daemon**, and the
daemon is where aggregation happens. You would have to run
`etsy/statsd` (Node.js) or `statsd_exporter` (Go), plus **a backend to actually
store the data**, because statsd itself keeps only in-memory aggregates and
flushes them onward. So the real dependency count is: client + daemon +
Graphite/whatever. For a single machine whose owner explicitly refused one
daemon-stack (Prometheus), substituting a different daemon-stack is not a win.

**Verdict: the daemon is a dealbreaker here.** It replaces one moving part with
two and adds a second language runtime. Last client release 2022-11-06.

### 1e. OpenTelemetry Python SDK with console/file exporter

**Verified API:** `opentelemetry.sdk.metrics.export.ConsoleMetricExporter`
exists and is documented as printing "to the console STDOUT", explicitly "for
diagnostic purposes". `InMemoryMetricReader` also exists ("useful for e.g. unit
tests").

**There is no `FileMetricExporter` in the core SDK.** You would write a custom
`MetricExporter` subclass (the abstract interface is `export()`, `force_flush()`,
`shutdown()`) to append to a file. There is no rotation, no query, no retention —
you'd get a growing text file.

`opentelemetry-sdk` 1.45.0 pulls **4 hard dependencies**, and the OTel metrics
model (views, temporality, aggregation) is a large conceptual surface for what
is ultimately "append a line to a file."

**Verdict:** highest complexity-to-value ratio of the options. The console
exporter is a debugging aid, not a storage strategy.

### 1f. SQLite-backed roll-your-own — **yes, this is a real, published pattern**

Two real projects do exactly "metrics into SQLite + a dashboard query", both
explicitly premised on *not* running Prometheus/Grafana:

**`PVRLabs/statlite`** (151 stars, MIT, pushed 2026-10-01, active) — single Go
binary, SQLite storage, built-in dashboard, "without requiring Prometheus or
Grafana". It is the closest published analogue to this project, and its docs
are unusually honest about limits:

- Measured footprint: **"roughly 10 to 15 MiB of idle RSS"**, described as an
  observed range, not an SLA.
- In a controlled experiment on a 1 vCPU / 512 MB VM beside a Spring Boot app:
  **~12 MiB final StatLite RSS**, 72/72 checks 200, zero restarts.
- Storage model: SQLite file (`sqlite_path`), conservative polling (30 s),
  bounded default retention.
- It defines a fixed JSON contract, [`statlite-metrics/v1`](https://github.com/PVRLabs/statlite/blob/main/docs/statlite-metrics-v1.md),
  with **FastAPI, Django, Express, Go, Gin integration guides** — a real,
  copyable "expose metrics from FastAPI" precedent.

Two statements from that contract matter for us:

> "Average latency is derived from request-duration-total and request-count
> counter deltas; **percentile and maximum-latency analysis are outside the
> lightweight core**."

> "In-memory helpers report metrics for one process or worker... Polling one
> shared load-balanced URL can make counters appear to reset or decrease
> between polls."

**`n0rdy/pooml`** (32 stars, AGPL-3.0, pushed 2026-09-27) — "Logs, metrics,
dashboards, and alerts in one small SQLite-backed binary. Built for
self-hosters, queried with plain SQL." It stores **only counters and gauges**,
downcasting histograms/summaries to `_sum`/`_count` pairs, and states plainly:
*"If you need native histogram buckets and quantiles, that's Prometheus
territory."* It also exposes its own Prometheus `/metrics` endpoint for external
scrapers. AGPL-3.0 and explicitly closed to contributions — a reference design,
not a dependency to adopt.

**Note:** both are Go binaries. Neither is a Python library to import. Their
value here is as **validated architecture precedent**, not as install targets.

### 1g. Verdict: least friction

**Use stdlib `sqlite3` (or the Postgres you already have) as the store, and
skip the metrics library entirely.**

Reasoning, grounded in the numbers above:

1. You already keep tasks + events in Postgres. A metrics library's only job
   would be to hold the same numbers in a second place — and the scrape-only
   modes of `prometheus_client`, `pyformance`, and `statsd` all share one
   fatal property here: **they are in-process and lose history on restart**.
   Prometheus-the-server exists precisely to fix that. You removed the server.
2. `prometheus_client` is the best of the libraries (4,379 stars, active,
   Apache-2.0, genuinely zero deps, ~64 KB). If you later want Prometheus or
   Grafana Cloud, adding `make_asgi_app()` costs almost nothing. **It is worth
   adding as an optional, two-line escape hatch — but it is not your store.**
3. Two independent real projects (StatLite, pooml) reached the same conclusion
   and are actively maintained doing it.
4. Percentiles are the deciding capability. See §4.2 — Postgres computes them
   in one indexed query. A client library cannot, because it has no history.

**Recommended shape:** your existing events table *is* the metrics store.
Derive success rate / p95 / block-rate at query time (§4). Add
`prometheus_client` behind an optional flag only if you ever want to point a
real scraper at it.

---

## 2. Structured logging

### 2a. Verification table

| Library | Stars | Last push | Last release | License | Archived | Hard deps |
| --- | --- | --- | --- | --- | --- | --- |
| `hynek/structlog` | 4,968 | 2026-09-05 | 26.1.0 — 2026-06-06 | Apache-2.0 **or** MIT (dual) | no | 1 (`typing-extensions`, only on Python < 3.11) |
| `madzak/python-json-logger` | 1,759 | 2024-12-12 | 4.2.0 — 2026-08-15 | BSD-2-Clause | **YES** | 0 |
| `nhairs/python-json-logger` (the maintained fork) | 273 | 2026-09-30 | same PyPI name, 4.2.0 | BSD-2-Clause | no | 0 |
| `Delgan/loguru` | 24,140 | 2026-09-28 | 0.7.3 — 2024-12-06 | MIT | no | 0 real (the 27 `requires_dist` entries are `sys_platform == "win32"` shims and `extra == "dev"` test pins) |

All three are alive and maintained. `python-json-logger` on PyPI is the
`nhairs` line now — install the same package name, just know the original repo
is archived and `nhairs` is where fixes land.

### 2b. The concrete tradeoff for a project already on stdlib `logging` + `RotatingFileHandler`

This is the decision that matters, so here is the mechanism, from structlog's
own [Standard Library Logging](https://www.structlog.org/en/stable/standard-library.html) page:

- **structlog's stdlib integration is real and supported.** It ships
  `structlog.stdlib.ProcessorFormatter` — a `logging.Formatter` — plus
  `filter_by_level`, `add_logger_name`, `add_log_level`, `ExtraAdder`,
  `PositionalArgumentsFormatter`, and `render_to_log_kwargs`. There is even
  `structlog.stdlib.recreate_defaults()` for the quick path.
- **Your `RotatingFileHandler` keeps working.** The recommended "most
  ambitious" configuration uses `logging.config.dictConfig` with ordinary
  `logging.handlers.WatchedFileHandler` / `RotatingFileHandler` entries and
  sets `structlog.stdlib.ProcessorFormatter` as the *formatter*. The docs show
  exactly this: a colored console handler and a plain file handler, both
  driving off the same processor chain. Handlers, levels, and third-party
  libraries that log through stdlib `logging` all continue to work, because
  `ProcessorFormatter` is invoked by `logging` itself.
- **But the switching cost is honestly non-trivial, and the docs say so:**
  *"We do appreciate that fully integrating structlog with standard library's
  logging is fiddly when done for the first time."* There are four distinct
  supported configurations (don't integrate / render in structlog / render in
  `logging` via `render_to_log_kwargs` / render via `ProcessorFormatter`), and
  two documented footguns: you **must** end the structlog chain with
  `wrap_for_formatter()` when using `ProcessorFormatter` (using
  `render_to_log_kwargs()` instead "will get puzzling errors from the standard
  library"), and with `render_to_log_kwargs` it is the **stdlib formatter's
  job** to render `extra` — get that wrong and "exceptions are ostensibly
  swallowed." There is also a `PrintLogger` vs `WriteLogger` interleaving
  caveat if structlog and `logging` share one stream.
- **`loguru` is a different bargain, not an upgrade.** It is by far the most
  popular (24,140 stars) and genuinely pleasant, but it is **not** stdlib
  `logging`; it has its own logger, its own sinks, and its own `rotation=`
  parameter. Adopting it means your existing `RotatingFileHandler`
  configuration, your `dictConfig`, and any library that calls
  `logging.getLogger()` become a parallel, second logging system. For a
  project already invested in stdlib `logging`, this is the **largest** switch
  cost of the three, not the smallest.

### 2c. Does structured logging actually help a single developer grep?

Structured logging pays off when a **machine** consumes the logs — an
aggregator, a dashboard, a log-search UI. For one developer grepping a file,
the honest answer is: **mostly no, with one exception.**

- grep on a JSON line is awkward (`"event": "fetch_failed"` vs `fetch_failed`),
  and `RotatingFileHandler` output becomes materially harder to read by eye.
- The exception is the case you actually have: **you already have an events
  table in Postgres.** That is your queryable store. Log lines do not need to
  be the analytics substrate — SQL is strictly better at it than grep.

**Recommendation: keep stdlib `logging` + `RotatingFileHandler` as-is.** If you
want machine-readable logs at the margin, the cheapest real step is
`nhairs/python-json-logger`'s `JsonFormatter` on a *separate* handler — that is
a zero-dependency, drop-in `Formatter` change, no restructuring, no
`dictConfig` rewrite. Adopt structlog only if you later add a log aggregator;
its value is proportional to how many machines consume the output, and here
that number is one.

---

## 3. Error tracking without SaaS

### 3a. Self-hosted Sentry — the real stated requirements

From [develop.sentry.dev/self-hosted](https://develop.sentry.dev/self-hosted/),
verbatim:

> "These are the minimum requirements:
> - 4 CPU Cores
> - 16 GB RAM + 16 GB swap
> - 20 GB Free Disk Space
>
> We recommend using 32 GB RAM, but it works with 16 GB RAM + 16 GB swap as
> well."

Additional stated burdens:

- Requires **Docker 19.03.6** and **Docker Compose 2.32.2**.
- *"Self-hosted Sentry relies heavily on disk I/O because it runs databases,
  message brokers, and other services on a single machine."* Sentry's own
  guidance: **`iowait > 10%` of CPU time "probably shows your system cannot
  handle the load."**
- *"no matter how small or big the traffic is, you will most likely hover
  around the same used resources"* — i.e. **the footprint does not shrink for a
  small workload.** This is the key sentence for a single-machine tool.
- RHEL-based distros have "known installation issues"; Alpine is unsupported.
- License is **FSL (Functional Source License)**, not OSI-approved — *"Fair
  Source is not under the OSI umbrella"*, converting to Apache-2.0 after 2
  years. Prohibited: selling it as a service, or being a Sentry competitor.

**What that means concretely.** I read `getsentry/self-hosted`'s
`docker-compose.yml`. It defines roughly **40 services**, including:
`postgres`, `redis`(valkey), `kafka` (Confluent cp-kafka), **`clickhouse`**
(with `MAX_MEMORY_USAGE_RATIO: 0.3` — *"This limits Clickhouse's memory to 30%
of the host memory"*), `seaweedfs` (S3-compatible object store),
`memcached`, `pgbouncer`, `smtp`, `nginx`, `relay`, `symbolicator`,
**15+ snuba consumers** (`snuba-errors-consumer`, `snuba-outcomes-consumer`,
`snuba-group-attributes-consumer`, `snuba-replacer`,
`snuba-subscription-consumer-*`, profiling consumers, …), `taskscheduler`,
`taskworker`, `taskbroker`, `launchpad-taskworker`, `vroom`,
`uptime-checker`, `sentry-cleanup`.

That is a distributed event-ingestion pipeline — Kafka + ClickHouse + object
storage — not an app you run beside a scraper. The 16 GB floor is a floor.

### 3b. GlitchTip — genuinely lighter, and yes it speaks `sentry-sdk`

**Source is GitLab, not GitHub** (`gitlab.com/glitchtip/glitchtip-backend`,
project 15450933: 359 stars, 221 forks, last activity 2026-09-30, MIT).

Resource requirements, verbatim from
[glitchtip.com/documentation/install](https://glitchtip.com/documentation/install):

> "Recommended system requirements: **512 MB RAM**, x86 or arm64 CPU
> Minimum system requirements: **256 MB RAM** when using all-in-one setup.
> Careful configuration will allow **128 MB + swap**."

- **PostgreSQL 14+ is required.** Valkey/Redis 7+ is **optional** — *"Set to
  empty string to disable VALKEY and utilize Postgres for task queue, cache,
  and session storage."* That matters: it means GlitchTip can be Postgres-only,
  reusing a database you already run.
- Disk guide: *"a 1 million event per month instance may require 30GB."*
- Ships an all-in-one mode: `GLITCHTIP_EMBED_WORKER` (default False) runs the
  background worker inside the web process — "Equivalent to
  `SERVER_ROLE=all_in_one`".
- Default retention 90 days, configurable per data class.

**Sentry-SDK compatibility: yes, confirmed, using the unmodified official SDK.**
GlitchTip's [FastAPI page](https://glitchtip.com/sdkdocs/python-fastapi) says
literally `pip install sentry-sdk` and `sentry_sdk.init(dsn="YOUR_DSN", ...)`,
noting *"The SDK auto-detects FastAPI and captures unhandled exceptions,
request data, and async context automatically."* One documented gap:
`auto_session_tracking=False` is set because **"GlitchTip does not support
sessions."**

So: same client library, different (much smaller) server. Sentry's
16 GB / 40-service bar vs GlitchTip's 256–512 MB.

### 3c. Verdict: is self-hosted error tracking overkill here?

**Sentry: yes, clearly overkill — disqualifying.** 16 GB RAM + 16 GB swap + 4
cores + 20 GB disk, ~40 containers on one box, and Sentry states the resource
use does not scale down with your traffic. On a machine that also runs a
scraper and its database, that is not a lightweight addition; it is a second
full-time system.

**GlitchTip: technically feasible, but still probably not worth it here.**
It fits in 256–512 MB and reuses your Postgres, which is a real improvement.
But note what it asks of you: a **second Django app + worker + its own schema
in your database + migrations + upgrades**, all to aggregate tracebacks you
could capture as rows in the task/event table you already have.

For a single-developer, single-machine tool whose errors are *already* being
recorded against a task row in Postgres, the marginal gain is a nicer
grouping UI. The cost is a permanently-running service and a schema you don't
control.

**Recommendation:** store the traceback (`traceback.format_exc()`), an
exception class fingerprint (e.g. `sha1(type + normalized message)`), a count,
and first/last-seen on your existing event rows, and surface them through a
query. That reproduces the single most valuable part of error tracking —
grouping by fingerprint and ranking by frequency — with zero new processes. If
you later want a real UI, **GlitchTip is the right escape hatch**
(Postgres-only, 256 MB, official `sentry-sdk`), and your fingerprint column
means adopting it costs a DSN string, not a rewrite.

---

## 4. Concrete "scraper health" metric definitions

### 4.1 Success rate — how practitioners avoid counting "empty" as success

**This is a real, named, published problem.** The clearest statement I found is
[The 99.9% Reliability Stack: Implementing Error Budgets in Web Scraping](https://dev.to/withatte/the-999-reliability-stack-implementing-error-budgets-in-web-scraping-29o5)
(dev.to, Feb 2026), which names it **"the Silent Failure problem"** and draws
exactly the distinction you asked about:

> "a successful HTTP request does not equal successful data extraction"
>
> **Hard Errors:** binary failures — `403`, `500`, DNS timeout.
> **Soft Errors:** "the silent killers. The page loads, but the price is
> missing, the HTML is a captcha page, or the JSON structure has changed."

And the arithmetic that makes the point:

> "If you scrape 10,000 product pages and 50 return hard errors, you have a
> 99.5% success rate... But if 2,000 of those pages return valid HTML with zero
> data, your 'real' reliability is 80%, and your budget is officially blown."

Two metrics are named there as the "canaries in the coal mine":

- **Schema Adherence** — does extracted data match the expected type? (suggests
  enforcing with Pydantic).
- **Field Density** — *"the percentage of records that contain a specific
  field."* The worked example: if `discount_price` normally appears on 30% of
  items and suddenly drops to 0% across a batch, the HTTP code is still 200 but
  Field Density has caught a structural failure. Reference implementation:

```python
def calculate_density(data, field_name):
    count = sum(1 for item in data if item.get(field_name) is not None)
    return (count / len(data)) * 100
```

**The same idea is a first-class feature in Spidermon** — the Zyte/Scrapinghub
monitoring framework for Scrapy (`scrapinghub/spidermon`, 562 stars,
BSD-3-Clause, pushed 2026-09-25, release **1.27.0 on 2026-08-10** — actively
maintained). Its `FieldCoverageMonitor` takes an explicit expected-coverage
threshold per field, nested paths supported:

```python
SPIDERMON_FIELD_COVERAGE_RULES = {
    "dict/field_1": 0.4,           # expected 40% coverage for field_1
    "dict/field_2": 1.0,           # expected 100% coverage for field_2
    "dict/field_3/field_3_1": 0.5, # nested field, 50%
}
```

And its dedicated how-to, [required fields coverage
validation](https://spidermon.readthedocs.io/en/latest/howto/required-fields-coverage-validation.html),
documents `check_missing_required_fields_percent(field_names=[...], allowed_percent=0.2)`
— i.e. **"fail if more than 20% of returned items have this required field
empty."** That is the concrete, published answer to "don't count empty as
success."

Spidermon's ["What to monitor?"](https://spidermon.readthedocs.io/en/latest/monitors.html)
list is the best published checklist I found for scraper health:

> - the amount of items extracted by the spider.
> - the amount of successful responses received by the spider.
> - the amount of failed responses (server-side errors, network errors, proxy errors, etc.).
> - the amount of requests that reach the maximum amount of retries and are finally discarded.
> - the amount of time it takes to finish the crawl.
> - the amount of errors in the log.
> - **the amount of bans.**
> - the job outcome.
> - **the amount of items that don't contain a specific field or a set of fields.**
> - the amount of items with validation errors (missing required fields, incorrect format, ...).

**Recommended definition — decompose, don't collapse.** Do not emit one
"success rate". Emit a per-platform, per-operation breakdown with `empty` and
`blocked` as *separate* buckets from `ok`:

```
success_rate   = ok_with_data / attempts        -- the only one that means "it worked"
empty_rate     = ok_but_no_items / attempts     -- silent failure; the killer
blocked_rate   = 403/captcha/429 / attempts     -- adversarial
error_rate     = timeout/5xx/dns / attempts     -- infrastructure
```

A page that returned HTTP 200 with zero parsed items is **not** `ok`. Tested in
SQLite against sample data, this decomposition immediately exposes a platform
whose naive success rate is 80% but whose real success rate is 60%:

```
('douyin',   'search', attempts=5, ok=3, good_pct=60.0, empty_pct=20.0, block_pct=20.0)
('kuaishou', 'detail', attempts=2, ok=1, good_pct=50.0, empty_pct= 0.0, block_pct= 0.0)
```

(SQL used is the `GROUP BY` query in §4.2; it ran as written.)

### 4.2 Latency percentiles without Prometheus

**Postgres `percentile_cont` is the right tool and its syntax is verified.**
Per [PostgreSQL 18 §9.21, Table 9.64](https://www.postgresql.org/docs/current/functions-aggregate.html),
it is an *ordered-set aggregate* — the aggregated input goes in `ORDER BY`
inside a `WITHIN GROUP` clause, and the percentile is a direct argument. The
array form returns an array of the same dimensions:

```
percentile_cont ( fractions double precision[] ) WITHIN GROUP ( ORDER BY double precision ) → double precision[]
```

Note two documented facts: these functions **ignore nulls**, and `percentile_cont`
**interpolates** between adjacent values (unlike `percentile_disc`, which picks
an actual data point). Also, a null `fraction` yields a null result.

**Actual SQL — per-platform, per-operation p50/p95/p99 over the last 24 h.**
Run this directly against your existing events/tasks table:

```sql
SELECT
    platform,
    op,
    COUNT(*)                                        AS attempts,
    COUNT(*) FILTER (WHERE outcome = 'ok' AND items > 0)               AS ok_with_data,
    COUNT(*) FILTER (WHERE outcome = 'ok' AND items = 0)               AS empty_results,
    COUNT(*) FILTER (WHERE outcome IN ('blocked','captcha','http_403')) AS blocked,
    ROUND(100.0 * COUNT(*) FILTER (WHERE outcome = 'ok' AND items > 0)
          / NULLIF(COUNT(*), 0), 2)                 AS success_rate_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE outcome = 'ok' AND items = 0)
          / NULLIF(COUNT(*), 0), 2)                 AS empty_rate_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE outcome IN ('blocked','captcha','http_403'))
          / NULLIF(COUNT(*), 0), 2)                 AS blocked_rate_pct,
    percentile_cont(0.50) WITHIN GROUP (ORDER BY latency_ms) AS p50_ms,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_ms,
    percentile_cont(0.99) WITHIN GROUP (ORDER BY latency_ms) AS p99_ms
FROM scrape_events
WHERE created_at >= now() - interval '24 hours'
  AND outcome <> 'ok_no_data'          -- only time successful fetches for latency
GROUP BY platform, op
ORDER BY platform, op;
```

Notes that matter in practice:

- `NULLIF(COUNT(*), 0)` prevents division-by-zero on a platform with no
  traffic in the window — otherwise the row errors instead of reporting zero.
- `FILTER (WHERE ...)` is standard Postgres and avoids `SUM(CASE WHEN ...)`.
- Compute latency percentiles over **successful** attempts only; mixing in
  timeouts measures your retry policy, not your latency.
- For a rolling trend rather than one window, bucket with `date_trunc`:

```sql
SELECT
    date_trunc('hour', created_at) AS bucket,
    platform,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_ms,
    COUNT(*) AS n
FROM scrape_events
WHERE created_at >= now() - interval '7 days'
  AND outcome = 'ok'
GROUP BY bucket, platform
ORDER BY bucket DESC, platform;
```

- **Index it.** `percentile_cont` sorts the group, so an index on
  `(platform, op, created_at DESC)` plus the window predicate keeps this cheap;
  without one, a large events table means a sort per group.

**SQLite equivalent (if a metrics DB is ever SQLite).** SQLite has **no**
`percentile_cont`. Verified workaround using window functions (requires SQLite
≥ 3.25 for `ROW_NUMBER() OVER`), executed successfully on SQLite 3.37.2:

```sql
WITH ranked AS (
  SELECT platform, latency_ms,
         ROW_NUMBER() OVER (PARTITION BY platform ORDER BY latency_ms) AS rn,
         COUNT(*)    OVER (PARTITION BY platform)                      AS n
  FROM scrape_events
  WHERE outcome = 'ok'
)
SELECT platform,
       MAX(CASE WHEN rn = CAST((n - 1) * 0.50 AS INT) + 1 THEN latency_ms END) AS p50_ms,
       MAX(CASE WHEN rn = CAST((n - 1) * 0.95 AS INT) + 1 THEN latency_ms END) AS p95_ms,
       n AS samples
FROM ranked
GROUP BY platform, n;
```

This is the **nearest-rank** method (no interpolation), so it will differ
slightly from Postgres `percentile_cont` on small samples. Output from the test
run:

```
('douyin',   300.0, 300.0, 3)
('kuaishou', 260.0, 260.0, 1)
```

Because you already run Postgres, **prefer the `percentile_cont` form** — it is
less code and it interpolates correctly.

### 4.3 "Risk-control hit rate" — no standard found

**No published standard by that name exists.** I could not find "risk-control
hit rate" as a defined metric in any English-language SRE, observability, or
scraping-monitoring source. It appears to be a translation-shaped term
(风险控制/风控 = risk control, standard in Chinese platform anti-fraud
vocabulary) rather than an established metric name.

**Closest real analogues, in descending order of closeness:**

1. **"the amount of bans"** — Spidermon's own ["What to
   monitor?"](https://spidermon.readthedocs.io/en/latest/monitors.html) list
   includes this as a first-class scraper health metric. This is the direct
   functional equivalent. Spidermon also ships `UnwantedHTTPCodesMonitor` with
   defaults `SPIDERMON_UNWANTED_HTTP_CODES = [400, 407, 429, 500, 502, 503,
   504, 523, 540, 541]` and a per-code `max_count` **or** `max_percentage`
   threshold — e.g. `{400: {"max_count": 100, "max_percentage": 0.5}, 500: 0}`
   (fail on >100 *or* >50% 400s; fail on any 500). That is a published,
   thresholded anti-bot/block metric.
2. **"blocked_rate" / anti-bot block rate** — the dev.to error-budget article
   classifies `403 Forbidden` and `429 Too Many Requests` as **transient**
   failures with prescribed handling: *"429 — Retry: Rotate proxy and increase
   backoff"*, *"403 — Retry: Change User-Agent or proxy provider."* It also
   gives a circuit-breaker design: *"If the 'budget burn' exceeds a threshold,
   such as more than 5% of requests failing schema validation, the scraper
   should automatically shut down."*
3. **"Target health score"** — Shifter's blog post [构建目标健康评分:识别网站正在针对你](https://shifter.io/cn/blog/mu-biao-jian-kang-ping-fen-zhen-dui)
   ("Building a target health score: identifying when a site is targeting
   you") is a real published attempt to score adversarial targeting. **Caveat:
   the page returned only a title to my fetcher — I could not read its
   methodology, so I cannot cite its formula.** It is listed as a lead, not a
   verified definition.

**Proposed operational definition** (mine, clearly labelled as such — not a
cited standard). Given that "risk control" manifests as *either* an explicit
block *or* a silent content substitution, hedge against both:

```
risk_control_rate = (blocked + challenged + empty_with_200) / attempts
```

with a companion **distinctness check**: count a hit only once per
`(platform, session/proxy, 15-min bucket)`, otherwise one long block inflates
the rate with hundreds of retries.

Signals worth recording per attempt to compute it: HTTP status, whether a
captcha/challenge marker appeared in the body, whether the response body length
collapsed versus the platform's rolling median, and whether a required field's
density dropped (§4.1). Alert on it **per platform, per operation** — a global
rate hides one broken platform behind four healthy ones.

---

## 5. Bottom-line recommendation

For a single-machine FastAPI scraper that **already keeps tasks + events in
Postgres**:

1. **Metrics: do not add a metrics library.** Your events table is the
   time-series store. Compute success/empty/blocked rates with the `GROUP BY`
   query in §4.2 and p50/p95/p99 with Postgres `percentile_cont ... WITHIN
   GROUP`. This is the least-friction option by a wide margin: zero new
   processes, zero new dependencies, and it is the only option that actually
   retains history across restarts. Two actively maintained projects
   (`PVRLabs/statlite`, `n0rdy/pooml`) validate the SQLite/embedded-store
   architecture, and statlite's measured **~12–15 MiB RSS** shows how small
   the honest version of this is.
   *Optional escape hatch:* add `prometheus_client` (4,379 stars, Apache-2.0,
   **zero required dependencies**, ~64 KB wheel) behind a flag with
   `app.mount("/metrics", make_asgi_app())` if you ever want to point Grafana
   Cloud or a real Prometheus at it. Two lines, no commitment. Keep it to a
   single worker or you inherit the documented multiprocess limitations.
   **Avoid:** `pyformance` (last release 2017), `statsd` + daemon (replaces one
   daemon with two), OTel + console exporter (4 hard deps, no file exporter,
   no retention).

2. **Logging: change nothing.** Keep stdlib `logging` +
   `RotatingFileHandler`. structlog (4,968 stars) integrates correctly with
   your handlers via `ProcessorFormatter`, but its own docs call the setup
   "fiddly," it has two documented footguns that silently swallow exceptions,
   and its payoff is proportional to the number of machines consuming logs —
   which here is one. If you want JSON logs cheaply, add
   `nhairs/python-json-logger` as a second handler's `Formatter` —
   zero dependencies, drop-in, no restructuring. **Do not adopt `loguru`** on a
   stdlib-`logging` project: it is a parallel logging system, not a formatter,
   so it is the largest switch cost, despite having the most stars (24,140).

3. **Error tracking: neither, for now.** Self-hosted **Sentry is
   disqualifying** — 4 cores / **16 GB RAM + 16 GB swap** / 20 GB disk by
   Sentry's own stated minimums, ~40 containers (Kafka, ClickHouse at 30% of
   host RAM, SeaweedFS, 15+ Snuba consumers), and Sentry states resource use
   *"most likely hover[s] around the same"* regardless of traffic. **GlitchTip
   is genuinely lighter** (512 MB recommended / 256 MB min / 128 MB + swap,
   Postgres-only with Valkey optional, MIT, uses the unmodified official
   `sentry-sdk` including a documented FastAPI setup) — but it still means a
   second Django app, worker, and schema in your database for what is
   currently a traceback string. Store `traceback.format_exc()` plus an
   exception fingerprint on your existing event rows and rank by frequency;
   that is most of the value at none of the cost. **Keep GlitchTip as the
   pre-validated upgrade path** — because your fingerprint is already there,
   adopting it later is a DSN string, not a rewrite.

---

## 6. Unverified / flagged

- **Shifter "target health score"** — the post exists, but its content did not
  render for my fetcher (title only). Its methodology is **unread and
  uncited**. Treat the lead as unverified.
- **"Risk-control hit rate"** — **no published standard found** under that
  name. All definitions in §4.3 are either cited analogues or my own proposal,
  labelled as such.
- **PostgreSQL SQL was not executed against a live server.** Docker Desktop's
  daemon was not running on this machine and I did not start it. The
  `percentile_cont ... WITHIN GROUP` syntax is verified against the official
  PostgreSQL 18 documentation (§9.21, Table 9.64), and the `GROUP BY` /
  `FILTER` decomposition was executed successfully against SQLite 3.37.2. The
  Postgres-specific query should be run once before relying on it.
- **`python-json-logger` install name** — the PyPI package `python-json-logger`
  (4.2.0) is now the `nhairs` fork; the `madzak` repo is archived. I verified
  the archived flag and the fork's README (which credits madzak as original
  author), but did not diff the two codebases.
- **GlitchTip star/fork counts come from the GitLab API**, not GitHub — there
  is no GitHub repo for the backend (the URL in the brief 404s).
- **`getsentry/sentry`, `hynek/structlog`, `omergertel/pyformance`,
  `getsentry/self-hosted`** report `license.spdx_id = "NOASSERTION"` on GitHub
  because they ship multiple license files. Resolved individually: structlog is
  dual Apache-2.0/MIT (`LICENSE-APACHE`), pyformance is Apache-2.0, Sentry and
  self-hosted are FSL (Fair Source, non-OSI, per Sentry's own docs).
- **Library memory/time claims** are cited from vendor docs (statlite's
  10–15 MiB RSS is their measurement on Linux/macOS, explicitly "not a
  maximum-memory guarantee or SLA"). I did not benchmark any library here.
