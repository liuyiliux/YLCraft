# Large-File Media Downloading in Python — Verified Research Report

**Scope:** engineering practices for large-file media downloading. Two targets: (A) `yt-dlp` used as a **library**, (B) resumable HTTP download libraries without yt-dlp.

**Method / evidence standard:** every claim below was read from primary source — raw source files from `raw.githubusercontent.com`, the repo README, the wiki (`raw.githubusercontent.com/wiki/yt-dlp/yt-dlp/*.md`), official docs, or GitHub issue pages. Anything not directly read is marked **UNVERIFIED**. Snapshot: yt-dlp `master` as fetched during this session; stars/last-push from the GitHub REST API at fetch time.

---

## 0. Verification environment note (matters for reproductions)

The machine's network was flaky during this research. Concrete observed failures, and how they were handled:

- `curl` to `raw.githubusercontent.com` failed once with `curl: (6) Could not resolve host` (DNS failure) — resolved by retry.
- `https://api.github.com/repos/<owner>/<repo>` returned **HTTP 403 `API rate limit exceeded for <IP>`** (unauthenticated limit, 60 req/hr per IP) for most of the session. Some repos were read successfully before the limit hit; two were never retrievable via the API and were corroborated from other primary sources instead. This is recorded per-library in the table.

**Retry guidance that follows from observation:** DNS failures here are transient and recover on retry; a 403 from `api.github.com` is *not* transient within the hour and must not be retried in a loop. All source fetches in this report used up to 3 attempts with a short backoff.

---

# TARGET A — `yt-dlp` as a library

Primary sources read:
- `yt_dlp/YoutubeDL.py` (fetched `master`, ~219 KB) — option docs + logic
- `yt_dlp/downloader/common.py`, `yt_dlp/downloader/http.py`, `yt_dlp/downloader/fragment.py`
- `yt_dlp/utils/_utils.py` (exception classes)
- `yt_dlp/cookies.py`, `yt_dlp/options.py` (CLI defaults)
- `README.md`, wiki `FAQ.md` / `Plugins.md` / `Home.md`

## A0. Important documentation finding — the "Embedding yt-dlp" wiki page does not exist

The task named `https://github.com/yt-dlp/yt-dlp/wiki` (Embedding yt-dlp). I fetched the wiki home and the wiki page list. The wiki has **9 pages**: `Home`, `EJS`, `Extractors`, `FAQ`, `Forks`, `Installation`, `Plugin Development`, `Plugins`, `PO Token Guide`. **There is no `Embedding-yt-dlp` wiki page.** Requesting it redirects to the wiki home.

Embedding documentation lives in the **README**, section `# EMBEDDING YT-DLP` (README line 2062), plus `devscripts/cli_to_api.py` for translating CLI flags to `YoutubeDL` params. Do not cite an embedding wiki page — it is not there.

## A1. Resume / partial downloads

### `.part` file naming

`yt_dlp/downloader/common.py`:

```python
def temp_name(self, filename):
    """Returns a temporary filename for the temporary download"""
    if self.params.get('nopart', False) or filename == '-' or \
            (os.path.exists(filename) and not os.path.isfile(filename)):
        return filename
    return filename + '.part'
```

So partial data is written to `<output>.part` unless `nopart` is true, output is stdout (`-`), or the target is not a regular file.

### The "file already fully downloaded" decision (quoted source)

This is the skip decision. `yt_dlp/downloader/common.py`, `FileDownloader.download()`:

```python
nooverwrites_and_exists = (
    not self.params.get('overwrites', True)
    and os.path.exists(filename)
)

if not hasattr(filename, 'write'):
    continuedl_and_exists = (
        self.params.get('continuedl', True)
        and os.path.isfile(filename)
        and not self.params.get('nopart', False)
    )

    # Check file already present
    if filename != '-' and (nooverwrites_and_exists or continuedl_and_exists):
        self.report_file_already_downloaded(filename)
        self._hook_progress({
            'filename': filename,
            'status': 'finished',
            'total_bytes': os.path.getsize(filename),
        }, info_dict)
        self._finish_multiline_status()
        return True, False
```

Three things worth noting, all directly visible above:

1. The "already downloaded" check is **based on the final filename existing**, not on the `.part` file. `continuedl_and_exists` requires `continuedl` true (default), the **final** file to exist as a regular file, and `nopart` false. Semantically: "a `.part` file exists and `continuedl` is on" → resume; "the final file exists and nopart is off" → consider it complete.
2. A **`progress_hook` with `status: 'finished'` is emitted even on this skip path** — so a hook counting completions will fire for files that were never actually downloaded this run.
3. The second return value is `False`, meaning "nothing was actually downloaded", as opposed to `True` on a real download (`return ret, True` at the end of the same method).

**API defaults differ from CLI defaults.** `continuedl` defaults to `True` in the downloader (`self.params.get('continuedl', True)`) and `overwrites` defaults to `True` in the API (`self.params.get('overwrites', True)`). The CLI flag `--force-overwrites` "includes --no-continue" (README line 678-679), and README documents `-c, --continue ... (default)` / `--no-continue`. The `YoutubeDL.py` option doc states: `overwrites: Overwrite all video and metadata files if True, overwrite only non-video files if None and don't overwrite any file if False`.

### What happens on HTTP Range support

`yt_dlp/downloader/http.py` — resume length is taken from the `.part` file, then a `Range` request is issued:

```python
ctx.open_mode = 'wb'
ctx.resume_len = 0
...
if self.params.get('continuedl', True):
    # Establish possible resume length
    if os.path.isfile(ctx.tmpfilename):
        ctx.resume_len = os.path.getsize(ctx.tmpfilename)

ctx.is_resume = ctx.resume_len > 0
```

and the request:

```python
has_range = range_start is not None
if has_range:
    request.headers['Range'] = f'bytes={int(range_start)}-{int_or_none(range_end) or ""}'
```

**Critical robustness detail** — yt-dlp does not trust `Range` to be honoured. It validates `Content-Range` and, if the server ignored the range, it **wipes the local partial file and redownloads from scratch**:

```python
if has_range:
    content_range = ctx.data.headers.get('Content-Range')
    content_range_start, content_range_end, content_len = parse_http_range(content_range)
    # Content-Range is present and matches requested Range, resume is possible
    if range_start == content_range_start and (...):
        ctx.content_len = content_len
        ...
        return
    # Content-Range is either not present or invalid. Assuming remote webserver is
    # trying to send the whole file, resume is not possible, so wiping the local file
    # and performing entire redownload
    elif range_start > 0:
        self.report_unable_to_resume()
    ctx.resume_len = 0
    ctx.open_mode = 'wb'
```

A `416 Range Not Satisfiable` is handled separately: it re-requests without a range and, if the reported `Content-Length` is within **100 bytes** of the local file size, treats the file as already fully downloaded. The source comment explains this tolerance: *"in issue #175 it was revealed that YouTube sometimes adds or removes a few bytes from the end of the file"*. This is a real-world "size drift" tolerance worth copying.

Note also the comment reference to `https://github.com/ytdl-org/youtube-dl/issues/6057#issuecomment-126129799` regarding servers that ignore `Range` while returning the whole file.

`--no-part` (param `nopart`) writes directly into the output file — which disables the `.part`-based resume path entirely, since `continuedl_and_exists` explicitly requires `not nopart`.

## A2. Concurrent fragments

**Option name:** `concurrent_fragment_downloads`.

- **Default: `1`.** From `yt_dlp/options.py`: `'-N', '--concurrent-fragments', dest='concurrent_fragment_downloads', metavar='N', default=1, type=int`.
- From `yt_dlp/downloader/fragment.py` class docstring: `concurrent_fragment_downloads: The number of threads to use for native hls and dash downloads`.
- Implementation: `max_workers = self.params.get('concurrent_fragment_downloads', 1)` driving a `concurrent.futures.ThreadPoolExecutor` (subclass `FTPE`). It applies to **native HLS and DASH** downloads — README: *"Download multiple fragments of m3u8/mpd videos in parallel."* It does **not** speed up a single plain-HTTP progressive file (for that, see `http_chunk_size`, which performs chunked ranged requests of one file).

**Thread-safety caveat (this is a real, sourced caveat, not speculation).** In `fragment.py` there is a custom executor subclass with the comment:

```python
class FTPE(concurrent.futures.ThreadPoolExecutor):
    # has to stop this or it's going to wait on the worker thread itself
```

and on interrupt the code reports `'Interrupted by user. Waiting for all threads to shutdown...'` and shuts the pool down. So cancellation is not instantaneous with `-N > 1`. Additionally, `progress.thread_reset()` is called in the fragment path, which indicates fragment progress accounting is explicitly thread-aware.

**I did not find** a statement in the sources I read that `YoutubeDL` instances are safe to share across threads. On the contrary, see the verified pitfalls list (§A8) — a maintainer states that a non-multithreaded usage of multiple instances is fine, and separately a threading issue exists with impersonation.

## A3. Progress hooks

### Exact documented dict — `progress_hooks`

Quoted verbatim from the `YoutubeDL.py` class docstring (lines ~397-421):

```
progress_hooks:    A list of functions that get called on download
                   progress, with a dictionary with the entries
                   * status: One of "downloading", "error", or "finished".
                             Check this first and ignore unknown values.
                   * info_dict: The extracted info_dict

                   If status is one of "downloading", or "finished", the
                   following properties may also be present:
                   * filename: The final filename (always present)
                   * tmpfilename: The filename we're currently writing to
                   * downloaded_bytes: Bytes on disk
                   * total_bytes: Size of the whole file, None if unknown
                   * total_bytes_estimate: Guess of the eventual file size,
                                           None if unavailable.
                   * elapsed: The number of seconds since download started.
                   * eta: The estimated time in seconds, None if unknown
                   * speed: The download speed in bytes/second, None if
                            unknown
                   * fragment_index: The counter of the currently
                                     downloaded video fragment.
                   * fragment_count: The number of fragments (= individual
                                     files that will be merged)

                   Progress hooks are guaranteed to be called at least once
                   (with status "finished") if the download is successful.
```

Every key the task asked about is confirmed present, with these exact names: `status`, `downloaded_bytes`, `total_bytes`, `total_bytes_estimate`, `speed`, `eta`, `filename`, `fragment_index`, `fragment_count`. Additionally present: `info_dict`, `tmpfilename`, `elapsed`.

**Signature:** the hook is called with **one positional argument** (the dict). It is not called as `hook(status, info_dict)` — `info_dict` is a *key inside* the dict. See the invocation, `downloader/common.py`:

```python
def _hook_progress(self, status, info_dict):
    # Ideally we want to make a copy of the dict, but that is too slow
    status['info_dict'] = info_dict
    # youtube-dl passes the same status object to all the hooks.
    # Some third party scripts seems to be relying on this.
    # So keep this behavior if possible
    for ph in self._progress_hooks:
        ph(status)
```

**Two consequences that matter for embedding, both stated in the source comment itself:** (1) the status dict is **not copied**, it is the same mutable object passed to every hook, so do not mutate it; (2) that shared-object behaviour is deliberately preserved for backward compatibility.

Registration: `ydl.add_progress_hook(ph)` appends to `self._progress_hooks`, and `'progress_hooks': self.add_progress_hook` appears in the `YoutubeDL` params→method mapping, so passing `{'progress_hooks': [fn]}` in the options dict also works.

### `postprocessor_hooks`

```
postprocessor_hooks:  A list of functions that get called on postprocessing
                   progress, with a dictionary with the entries
                   * status: One of "started", "processing", or "finished".
                             Check this first and ignore unknown values.
                   * postprocessor: Name of the postprocessor
                   * info_dict: The extracted info_dict

                   Progress hooks are guaranteed to be called at least twice
                   (with status "started" and "finished") if the processing is successful.
```

Note the statuses are **`started` / `processing` / `finished`** — deliberately different from the download hook's `downloading` / `error` / `finished`.

### Raising / cancelling from a hook

`DownloadCancelled` is imported into `YoutubeDL.py` from `.utils` (line 96). Two documented uses appear in the option docstring:

- `match_filter`: *"Raise utils.DownloadCancelled(msg) to abort remaining downloads when a video is rejected."*
- (compat) *"`raise DownloadCancelled(msg)` in match_filter instead ..."*

Handling: in `__download_wrapper`, `except DownloadCancelled as e: self.to_screen(f'[info] {e}')` and then it re-raises unless `break_per_url` is set. And `_handle_extraction_exceptions` explicitly **re-raises `DownloadCancelled`** rather than absorbing it:

```python
except (CookieLoadError, DownloadCancelled, LazyList.IndexError, PagedList.IndexError):
    raise
```

So `DownloadCancelled` propagates out of `download()`/`extract_info()` and is safe to catch for user-initiated cancellation.

**UNVERIFIED:** whether raising an *arbitrary* exception from inside a `progress_hooks` callback is officially supported, and what yt-dlp does with it. The sources I read document `DownloadCancelled` for `match_filter`, and implement cancellation propagation for it; I did not find a documented contract for raising from a progress hook specifically. Treat "raise from a progress hook" as unsupported/undocumented unless verified against the version you pin.

## A4. Rate limiting / throttling

Exact names, units, and defaults:

| Param | Default | Units / meaning | Source |
|---|---|---|---|
| `ratelimit` | `None` | **bytes/sec.** `ratelimit: Download speed limit, in bytes/sec.` CLI `-r/--limit-rate/--rate-limit`, metavar `RATE`, e.g. `50K`/`4.2M`. As an API param it is a number. | `downloader/common.py` line 51; `options.py` 1016-1018 |
| `throttledratelimit` | `None` (treated as `0`) | **bytes/sec.** *"Assume the download is being throttled below this speed (bytes/sec)"* → re-extracts. CLI `--throttled-rate` (note: CLI flag name differs from param name). | `downloader/common.py` 52; `options.py` 1019-1022 |
| `sleep_interval` | `0` (`or 0`) | **seconds** to sleep before each download; lower bound when paired with `max_sleep_interval`. CLI also `--min-sleep-interval`. | `YoutubeDL.py` 445-448; `options.py` 1209 |
| `max_sleep_interval` | `0` (`or 0`) | **seconds**, upper bound. *"Must only be used along with sleep_interval. Actual sleep time will be a random float from range [sleep_interval; max_sleep_interval]."* | `YoutubeDL.py` 450-454 |
| `sleep_interval_requests` | not read in detail | **seconds to sleep between requests during extraction** | `YoutubeDL.py` 443 |
| `min_sleep_interval` | **not a `YoutubeDL` param** | It is a **CLI alias** of `--sleep-interval`: `'--sleep-interval', '--min-sleep-interval'` both map to the same option. In the API the name is `sleep_interval`. | `options.py` 1209-1214 |
| `sleep_interval_subtitles` | `0` | seconds before each subtitle download | `YoutubeDL.py` 455 |

Randomized sleep implementation (`downloader/common.py`):

```python
min_sleep_interval = self.params.get('sleep_interval') or 0
max_sleep_interval = self.params.get('max_sleep_interval') or 0
...
sleep_interval = random.uniform(
    min_sleep_interval, max_sleep_interval or min_sleep_interval)

if sleep_interval > 0:
    self.to_screen(f'[download] Sleeping {sleep_interval:.2f} seconds {sleep_note}...')
    time.sleep(sleep_interval)
```

`ratelimit` is enforced by **sleeping**, not by shaping the socket — `FileDownloader.slow_down()`:

```python
speed = float(byte_counter) / elapsed
if speed > rate_limit:
    sleep_time = float(byte_counter) / rate_limit - elapsed
    if sleep_time > 0:
        time.sleep(sleep_time)
```

`throttledratelimit` is a **re-extraction trigger**, not a cap (`downloader/http.py`): `if speed and speed < (self.params.get('throttledratelimit') or 0): ... raise ThrottledDownload`. `ThrottledDownload` subclasses `ReExtractInfo`, which `_handle_extraction_exceptions` catches and retries. Useful against VPN/host throttling: the download restarts with a fresh extractor result rather than just retrying the same URL.

Note the default CLI config in `options.py` line 158 for the `--compat-options`-adjacent defaults map: `'sleep': ['--sleep-subtitles', '5', '--sleep-requests', '0.75', '--sleep-interval', '10', '--max-sleep-interval', '20']`. That is a *compat preset*, not the API default (API defaults are 0/None as tabled above).

## A5. Retries

| Param | API default | CLI default | Meaning |
|---|---|---|---|
| `retries` | used via `RetryManager(self.params.get('retries'), ...)` — **no literal default in the API path** | **10** (`'-R', '--retries', dest='retries', default=10`), or `"infinite"` | *"Number of times to retry for expected network errors."* |
| `fragment_retries` | **0 for API** — documented explicitly | **10** (`--fragment-retries`, default=10) | *"Number of retries for a fragment (default is 10), or 'infinite' (DASH, hlsnative and ISM)"* |
| `file_access_retries` | `3` — `RetryManager(self.params.get('file_access_retries', 3), ...)` | **3** | retries on file access error |
| `extractor_retries` | **3** — `YoutubeDL.py` line 535: *"Number of times to retry for known errors (default: 3)"* | `--extractor-retries` | retries for known extractor errors |
| `retry_sleep_functions` | `{}` (CLI default `{}`) | `{}` | *"Dictionary of functions that takes the number of attempts as argument and returns the time to sleep in seconds. Allowed keys are 'http', 'fragment', 'file_access', 'extractor'"* |

**The `fragment_retries` API/CLI default split is stated in the source**, in `fragment.py`'s class docstring:

```
fragment_retries:   Number of times to retry a fragment for HTTP error
                    (DASH and hlsnative only). Default is 0 for API, but 10 for CLI
```

This is a genuine embedding trap: a library user who does not set `fragment_retries` gets **0 fragment retries** while the CLI user gets 10. For an unstable VPN this is the single most important default to override.

CLI `--retry-sleep` accepts `[TYPE:]EXPR` with `TYPE` in `http|fragment|file_access|extractor` (default `http`), where `EXPR` is `N`, `linear=START[:END[:STEP=1]]`, or `exp=START[:END[:BASE=2]]`.

## A6. Error taxonomy for embedding

All of these are defined in `yt_dlp/utils/_utils.py` and re-exported through `yt_dlp.utils` (they are imported into `YoutubeDL.py` via `from .utils import (...)`). Class hierarchy as read:

```
Exception
└── YoutubeDLError                     # "Base exception for YoutubeDL errors."
    ├── ExtractorError                 # "Error during info extraction."
    │   ├── UnsupportedError           # f'Unsupported URL: {url}', expected=True
    │   ├── RegexNotFoundError         # "Error when a regex didn't match"
    │   ├── GeoRestrictedError         # has .countries
    │   └── UserNotLive
    ├── DownloadError                  # has .exc_info
    ├── EntryNotInPlaylist
    ├── SameFileError
    ├── PostProcessingError
    ├── DownloadCancelled              # .msg
    │   ├── ExistingVideoReached
    │   ├── RejectedVideoReached
    │   └── MaxDownloadsReached
    ├── ReExtractInfo
    │   └── ThrottledDownload
    ├── UnavailableVideoError
    ├── ContentTooShortError
    ├── XAttrMetadataError
    ├── XAttrUnavailableError
    └── UnsafeExecExpansionError
```

Also relevant, but **defined in `yt_dlp/cookies.py`, not `utils`**: `CookieLoadError(YoutubeDLError)`.

Quoted source (verbatim, `_utils.py` lines 967-1067):

```python
class YoutubeDLError(Exception):
    """Base exception for YoutubeDL errors."""
    msg = None

    def __init__(self, msg=None):
        if msg is not None:
            self.msg = msg
        elif self.msg is None:
            self.msg = type(self).__name__
        super().__init__(self.msg)

class ExtractorError(YoutubeDLError):
    """Error during info extraction."""
    ...

class DownloadError(YoutubeDLError):
    """Download Error exception.

    This exception may be thrown by FileDownloader objects if they are not
    configured to continue on errors. They will contain the appropriate
    error message.
    """

    def __init__(self, msg, exc_info=None):
        """ exc_info, if given, is the original exception that caused the trouble (as returned by sys.exc_info()). """
        super().__init__(msg)
        self.exc_info = exc_info
```

**Practical catching strategy from the source, not from advice:** the safest single catch is `YoutubeDLError`. Two important behavioural notes read from `_handle_extraction_exceptions`:

- `ExtractorError` and `GeoRestrictedError` are **caught inside yt-dlp and routed to `report_error`** — they do not necessarily propagate to your caller. So wrapping `extract_info` in `except ExtractorError` may never fire; what you actually observe depends on the `ignoreerrors` param.
- `DownloadCancelled` and `CookieLoadError` are re-raised. `ignoreerrors` (default `False` for API, `'only_download'` for CLI) changes whether arbitrary exceptions are swallowed.

`RegexNotFoundError` is a subclass of `ExtractorError`, so catching `RegexNotFoundError` specifically is only meaningful if you also ensure extraction errors propagate.

**UNVERIFIED:** there is no explicit "these are public/stable API" list for `yt_dlp.utils` that I found in the sources read. The README's embedding section says *"we do not guarantee the return value of `YoutubeDL.extract_info` to be json serializable, or even be a dictionary"* — it makes no stability promise about `utils`. Treat `yt_dlp.utils` as internal-but-imported-by-convention; pin your yt-dlp version.

## A7. Cookies

### `cookiefile` vs `cookiejar`

Docstring: `cookiefile: File name or text stream from where cookies should be read and dumped to`. There is **no** `cookiejar` *param*; `ydl.cookiejar` is a **property**:

```python
@functools.cached_property
def cookiejar(self):
    """Global cookiejar instance"""
    try:
        return load_cookies(
            self.params.get('cookiefile'), self.params.get('cookiesfrombrowser'), self)
    except CookieLoadError as error:
        cause = error.__context__
        self.report_error(str(cause), tb=''.join(traceback.format_exception(cause)))
        raise
```

**The documented caveat the task asks about:** it is a `functools.cached_property`. This is a **source-verified** fact with a direct consequence: the jar is built **lazily on first access** and then **cached on the instance**. So:

- Mutating `ydl.cookiejar` *before* first access is fine (it constructs from `cookiefile`).
- Mutating it *after* first access mutates the cached object — which is the intended way to inject cookies, and it **is** the live jar used by the request handlers (`cookiejar=self.cookiejar` is passed into the request director and into `_calc_headers`).
- Changing `ydl.params['cookiefile']` **after** the property has been resolved will have **no effect**, because the cached value is already computed. To force a rebuild you must clear it: `ydl.__dict__.pop('cookiejar', None)` (that is how `cached_property` values are stored), or set it before first use.

I did **not** find an explicit prose "caveat" about mutating `ydl.cookiejar` in the README — the caveat follows from the `cached_property` decorator in the source above. Flagging the distinction honestly: the decorator is verified; a *documented warning* about it is **UNVERIFIED/not found**.

### `YoutubeDLCookieJar` and `load_cookies`

Both are in `yt_dlp/cookies.py` (public-ish names, imported by `YoutubeDL.py`).

`YoutubeDLCookieJar` subclasses `http.cookiejar.MozillaCookieJar` — so it reads/writes **Netscape/Mozilla `cookies.txt`** format:

```python
class YoutubeDLCookieJar(http.cookiejar.MozillaCookieJar):
    """
    See [1] for cookie file format.

    1. https://curl.haxx.se/docs/http-cookies.html
    """
    _HTTPONLY_PREFIX = '#HttpOnly_'
    _ENTRY_LEN = 7
    _HEADER = '''# Netscape HTTP Cookie File
# This file is generated by yt-dlp.  Do not edit.

    '''
```

`load_cookies(cookie_file, browser_specification, ydl)` merges a browser-extracted jar with the file jar:

```python
def load_cookies(cookie_file, browser_specification, ydl):
    try:
        cookie_jars = []
        if browser_specification is not None:
            ...
            cookie_jars.append(extract_cookies_from_browser(...))
        if cookie_file is not None:
            ...
            jar = YoutubeDLCookieJar(cookie_file)
            if not is_filename or os.access(cookie_file, os.R_OK):
                jar.load()
            cookie_jars.append(jar)
        return _merge_cookie_jars(cookie_jars)
    except Exception:
        raise CookieLoadError('failed to load cookies')
```

Two embedding-relevant details: if `cookiefile` is a **path that is not readable**, it is silently skipped (`os.access(..., os.R_OK)`) rather than raising; and **any** exception becomes `CookieLoadError('failed to load cookies')` with the real cause on `__context__` — which is why `YoutubeDL.cookiejar` reaches into `error.__context__` to report the true cause. If you catch `CookieLoadError`, inspect `__context__`.

### Does yt-dlp write back to the cookiefile by default? — YES

```python
def save_cookies(self):
    if self.params.get('cookiefile') is not None:
        self.cookiejar.save()

def close(self):
    self.save_cookies()
```

`close()` is called from `__exit__`, and the README's embedding examples all use `with YoutubeDL(...) as ydl:`. **Therefore: using the context manager with a `cookiefile` writes the cookie jar back to that file on exit.** Consequence for embedding: if you point `cookiefile` at a shared/exported cookies file, yt-dlp will overwrite it. README confirms `--no-cookies` = *"Do not read/dump cookies from/to file"*, i.e. dumping to file is the default when a cookie file is set. Also note `--cookies-from-browser chrome --cookies cookies.txt` is the documented way to *export* browser cookies to a file (FAQ §"How do I pass cookies").

`save()`/`_really_save` write the Netscape 7-field format with `ignore_discard=True, ignore_expires=True` as the defaults in the signature, and `_really_save` skips cookies only when those flags are false — meaning **session cookies and expired cookies are written too** by default.

## A8. VERIFIED pitfalls with URLs (only ones confirmed by reading the page)

1. **Multiple `YoutubeDL` objects open simultaneously — "not well tested".**
   [yt-dlp issue #4826](https://github.com/yt-dlp/yt-dlp/issues/4826) (question, closed as completed). The reporter asked whether `with YoutubeDL(opts1) as ydl1, YoutubeDL(opts2) as ydl2:` is safe, since constructing an instance is expensive. A maintainer replied:
   > "As far as I know, it should be fine. But this use-case is not well tested, so I can't be 100% sure. If you find any issues, let me know and we can fix it"

   and later, on shared resources:
   > "Do the two classes share any common resources? The same cookie file, for example. If not, all of these should work"
   > "No. Cache files are open and closed as required. Since your code isn't multithreaded, it is fine"

   **The "it is fine" verdict is explicitly conditioned on non-multithreaded use and on not sharing a cookie file.** Pitfall: two instances sharing one `cookiefile` will both write it on `close()`.

2. **`YoutubeDL` instances are NOT picklable; `extract_info` result is not guaranteed picklable.**
   [yt-dlp issue #9487](https://github.com/yt-dlp/yt-dlp/issues/9487) — multiprocessing/asyncio use raised `TypeError: cannot pickle '_io.TextIOWrapper' object`. Maintainer answer:
   > "`YoutubeDL` instances are not picklable. Create it inside each process. The returned `info_dict` is picklable in most cases, but not guaranteed and need to be sanitized"

   with the corrected pattern `with YoutubeDL({...}) as ydl: return ydl.sanitize_info(ydl.extract_info(url, download=False))`. **This is the citable basis for "create the instance inside the worker, sanitize before crossing a process boundary."**

3. **Threading + `impersonate` breaks; also `RuntimeError: cannot schedule new futures after interpreter shutdown`.**
   [yt-dlp issue #15073](https://github.com/yt-dlp/yt-dlp/issues/15073) — running the same embedded download in a `threading.Thread` fails with `yt_dlp.networking.exceptions.RequestError: Impersonate target "" is not available...` while the main-thread call works. The same issue reports `RuntimeError: cannot schedule new futures after interpreter shutdown` and `NoSupportingHandlers: Unable to handle request: Unsupported extensions: impersonate (requests, urllib)`. **Threading is not a verified-safe embedding model.**

4. **stdout is not a stable interface.** README, `# EMBEDDING YT-DLP`:
   > "Your program should avoid parsing the normal stdout since they may change in future versions. Instead, they should use options such as `-J`, `--print`, `--progress-template`, `--exec` etc"

   Plus `quiet: Do not print messages to stdout.` and `noprogress: Do not print the progress bar` are real params (both in the option docstring). For a library, use `progress_hooks`, not stdout.

5. **`extract_info` return value is not guaranteed to be a dict or JSON-serializable.** README embedding tip:
   > "we do not guarantee the return value of `YoutubeDL.extract_info` to be json serializable, or even be a dictionary. It will be dictionary-like, but if you want to ensure it is a serializable dictionary, pass it through `YoutubeDL.sanitize_info`"

6. **`extract_info` can return `None`.** Source, `__extract_info`: `if ie_result is None: self.report_warning(...); return`. And in `process_ie_result`, `url_transparent` handling has the comment *"extract_info may return None when ignoreerrors is enabled and extraction failed with an error, don't crash and return early in this case"* followed by `if not info: return info`. So **`if not info:` guarding is source-justified**, and with `ignoreerrors` enabled a `None` return is expected rather than exceptional.

7. **No embedding wiki page.** Verified: the wiki has 9 pages and `Embedding-yt-dlp` is not among them (the URL redirects to the wiki Home).
   [wiki Home](https://github.com/yt-dlp/yt-dlp/wiki)

8. **ffmpeg location.** `ffmpeg_location: Location of the ffmpeg binary; either the path to the binary or its containing directory` (`YoutubeDL.py` option docstring, under "options used by the post processors"). FAQ confirms ffmpeg is required to merge separate audio/video formats: *"You will need ffmpeg to download and merge such formats."*
   [FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ)

**Pitfalls I could NOT verify — explicitly flagged rather than asserted:**
- **Memory leaks** in long-running embedded use: I found **no** credible citable source (issue/wiki/SO page read) establishing a memory leak. **UNVERIFIED.**
- **Blocking the asyncio event loop**: yt-dlp is synchronous and *does* block, but I found no official doc page stating a recommended async integration pattern. The only citable adjacent evidence is issue #9487, where the maintainer's guidance is to run it in a separate **process**, not to await it. **UNVERIFIED as a documented pitfall.**
- **"Reusing a YoutubeDL object" is broken**: issue #4826 discusses repeated `__enter__`/`__exit__` of the same instance but the thread does not conclude it is supported or unsafe. **UNVERIFIED.**

## A9. `sanitize_info` / `process_ie_result` / `download_archive` for library use

### `sanitize_info`

Signature: `def sanitize_info(info_dict, remove_private_keys=False)`. It is a `@staticmethod`, so callable as `YoutubeDL.sanitize_info(info)` or `ydl.sanitize_info(info)`.

```python
def sanitize_info(info_dict, remove_private_keys=False):
    """ Sanitize the infodict for converting to json """
    if info_dict is None:
        return info_dict
    ...
    def filter_fn(obj):
        if isinstance(obj, dict):
            return {k: filter_fn(v) for k, v in obj.items() if not reject(k, v)}
        elif isinstance(obj, (list, tuple, set, LazyList)):
            return list(map(filter_fn, obj))
        elif isinstance(obj, ImpersonateTarget):
            return str(obj)
        elif obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        else:
            return repr(obj)
    return filter_fn(info_dict)
```

Key behaviours: **`None` in → `None` out** (so it is safe to chain on a possibly-`None` result, matching pitfall #6); it recursively converts dict/list/tuple/set/`LazyList` and `repr()`s anything else, which is what makes the result JSON-serializable. It also `setdefault`s `epoch`, `_type`, and `_version`. With `remove_private_keys=True` it drops `requested_downloads`, `requested_formats`, `requested_subtitles`, `requested_entries`, `entries`, `filepath`, `_filename`, `filename`, `infojson_filename`, `original_url`, `playlist_autonumber` and any key starting with `__`. Because it is a **`@staticmethod`**, calling it on an instance is fine but it does not use instance state. Note `LazyList` results get **materialised** — relevant if you were relying on laziness.

`YoutubeDL.filter_requested_info` is documented as an alias for backward compatibility.

### `process_ie_result`

```python
def process_ie_result(self, ie_result, download=True, extra_info=None):
    """
    Take the result of the ie(may be modified) and resolve all unresolved
    references (URLs, playlist items).

    It will also download the videos if 'download'.
    Returns the resolved ie_result.
    """
```

Its dispatch is on `result_type = ie_result.get('_type', 'video')` with branches for `url`, `url_transparent`, `video`, `playlist`/`multi_video`, `compat_list`, else `raise Exception(f'Invalid result type: {result_type}')`. It handles `extract_flat` short-circuiting, playlist recursion protection via `self._playlist_urls`, and calls `process_video_result(ie_result, download=download)` for videos. For embedding, the practical implication is that `process_ie_result` is the "resolve and optionally download" layer beneath `extract_info`, and `download=False` on it (or on `extract_info`) is how you get metadata only. Note the docstring on `extract_info(..., process=True)`: *"Must be True for download to work."*

### `download_archive`

```python
def in_download_archive(self, info_dict):
    if not self.archive:
        return False

    vid_ids = [self._make_archive_id(info_dict)]
    vid_ids.extend(info_dict.get('_old_archive_ids') or [])
    return any(id_ in self.archive for id_ in vid_ids)

def record_download_archive(self, info_dict):
    fn = self.params.get('download_archive')
    if fn is None:
        return
    vid_id = self._make_archive_id(info_dict)
    assert vid_id
    self.write_debug(f'Adding to archive: {vid_id}')
    if is_path_like(fn):
        with locked_file(fn, 'a', encoding='utf-8') as archive_file:
            archive_file.write(vid_id + '\n')
        self.archive.add(vid_id)
```

Param doc: `download_archive: A set, or the name of a file where all downloads are recorded. Videos already present in the file are not downloaded again.` It accepts **a `set` or a file path** — so a library can pass an in-memory `set` and skip file I/O entirely. The file is opened with `locked_file` (inter-process locking). FAQ: *"Note that only successful downloads are recorded in the file."* Related params: `break_on_existing`, `force_write_download_archive`, `break_per_url`. `in_download_archive` accepts `_old_archive_ids` for migration.

**Relationship to resume, and a real gotcha:** `download_archive` is a content-identity skip (you already fetched this video id), entirely separate from `.part` resume (you have partial bytes of this file). Using an archive for a re-downloadable media pipeline means a previously-recorded id is skipped **before any download attempt** — see `_match_entry`, which raises `ExistingVideoReached` / reports `'has already been recorded in the archive'`.

---

# TARGET B — resumable HTTP downloads (no yt-dlp)

## B0. Candidate verification — three of the task's candidate coordinates are wrong

This matters because the task handed over specific repo URLs. Verified with live HTTP requests:

| Candidate as given | Result | Correct location |
|---|---|---|
| `iAklan/pySmartDL` | **HTTP 404 — does not exist** | `iTaybb/pySmartDL` (HTTP 200) |
| `gwwg/downloadkit` | **HTTP 404 — does not exist**; could not be confirmed to exist anywhere | **Gitee** (canonical): `https://gitee.com/g1879/DownloadKit`; GitHub mirror `g1879/DownloadKit`. PyPI `downloadkit` is by **g1879**, not `gwwg` |
| `mjishnu/pypdl` | HTTP 200 | correct |
| `pawamoy/aria2p` | HTTP 200 | correct |
| `aria2/aria2` | HTTP 200 | correct |

`pySmartDL` on PyPI: `project_urls`… `Homepage: http://pypi.python.org/pypi/pySmartDL/`, and the README inside the PyPI metadata states `Project page: https://github.com/iTaybb/pySmartDL/`. The `AbirHasan2005/pySmartDL` repo also exists (HTTP 200) but appears to be a fork/mirror — **UNVERIFIED** which is canonical; the PyPI metadata points at `iTaybb`.

## B1. Comparison table

Star/date values from the GitHub REST API (`https://api.github.com/repos/<owner>/<repo>`) unless noted. The API was rate-limited (HTTP 403) for much of this session; the "source" column records exactly where each number came from. Values marked **search API** were obtained by a second pass via `/search/repositories?q=repo:owner/name`, which has a **separate quota** from the core bucket and worked while the core API returned `403 rate limit exceeded`. Stars for pypdl (110), aria2p (572) and aria2 (42,885) were cross-checked against the HTML repo pages and matched exactly.

| Library | Stars | Last push | Archived | License | Resume mechanism | Concurrency | Checksum | Progress callback |
|---|---|---|---|---|---|---|---|---|
| **`pypdl`** (`mjishnu/pypdl`) | **110** (API) | **2025-10-23T10:18:50Z** (API) | No (API) | MIT (PyPI) | Per-segment `.N` files + JSON sidecar `<file>.json` storing `{url, etag, segments}`; resumes only if ETag matches | `segments` (default **5**) × `Pypdl(max_concurrent=...)` (default **1**); `multisegment=True` default | Yes — `hash_algorithms` (during download, cached) + `FileValidator.validate_hash(correct_hash, algorithm)` | `callback(status: bool, result: FileValidator|None)`; plus polled attributes `progress`, `speed`, `eta`, `completed` |
| **`aria2p`** (`pawamoy/aria2p`) | **572** (API) | **2026-09-29T13:55:58Z** (API) | No (API) | ISC (API) | **Wrapper — no HTTP code of its own.** Delegates to the `aria2c` daemon over JSON-RPC (`.aria2` control file) | Delegates: `--split` **5**, `--max-connection-per-server` **1**, forwarded via opaque `options` | Delegates: `--checksum=TYPE=DIGEST` | ❌ none; polled `Download.progress`, `download_speed`, `eta`, `progress_string()` |
| **`pySmartDL`** (`iTaybb/pySmartDL`) | **208** | **2026-04-13T17:08:59Z** | No | Unlicense | `Range: bytes=start-end` per thread; each thread its own file `dest + ".%03d" % i`, merged post-pool. **No `.part`/state file for cross-run resume** (see §B3) | `threads=5` (ctor); auto-downgraded to **1** if `is_HTTPRange_supported()` is false | `add_hash_verification(algorithm, hash)` + `fetch_hash_sums()` (SHA256SUMS/SHA1SUMS/MD5SUMS) + `HashFailedException` | ❌ no callback; polled `get_progress()`, `get_progress_bar()`, `get_speed()`, `get_eta()` | GitHub search API |
| **`DownloadKit`** (`g1879/DownloadKit`) | **35** | **2025-03-25T03:24:47Z** | No | BSD-3-Clause | `Range: bytes={a}-{b}` per task; writes into **one** file at `seek` offsets (no merge step); offset = existing file size when `file_exists='add'` | `roads=10` (ctor, simultaneous missions); `split=True`; `block_size='50M'` per chunk; 128k read block | ❌ none found in source | ❌ no callback; `mission.rate`, `mission.wait()` | GitHub search API |
| **`DownloadKit`** | **N/A — not on GitHub** (Gitee: `gitee.com/g1879/DownloadKit`) | PyPI last release **2024-11-30** (v2.0.7) | N/A | BSD (PyPI) | Auto-retry and multi-thread chunking (PyPI description, Chinese); **source not read — UNVERIFIED** | "多线程…大文件自动分块用多线程下载" (multi-threaded, large files auto-chunked across threads) per PyPI description; **param not read — UNVERIFIED** | Not mentioned in PyPI description — **UNVERIFIED** | Not mentioned in PyPI description — **UNVERIFIED** |
| `requests` + manual `Range` | 54,371 (API) | 2026-09-28 (API) | No | Apache-2.0 | You implement it | You implement it | You implement it | You implement it |
| `httpx` | 15,524 (API) | 2026-03-29 (API) | No | BSD-3-Clause | You implement it (has both sync and async clients) | You implement it | You implement it | You implement it |

Repo-level facts for the "no library" baseline: `psf/requests` 54,371 stars / pushed 2026-09-28T16:55:48Z / Apache-2.0; `encode/httpx` 15,524 stars / pushed 2026-03-29T00:19:16Z / BSD-3-Clause. `aria2/aria2` itself: **42,885 stars**, pushed **2026-06-25T14:49:35Z**, GPL-2.0, 1,179 open issues. `yt-dlp/yt-dlp` for reference: 194,684 stars, pushed 2026-09-27T22:09:13Z.

**Maintenance verdict:** `pypdl` is the only pure-Python candidate I could verify as both real, GitHub-hosted, and actively released (1.5.7 on 2025-10-23, matching its `pushed_at`). `pySmartDL` is also actively pushed (2026-04-13) but its **PyPI releases stopped in 2020**, so "actively maintained" is true of the repository, not of the published package — do not describe it as a maintained dependency. `aria2p` is maintained but is only an RPC wrapper and requires the external `aria2c` binary. `DownloadKit` is the smallest project (35 stars), is canonically **Gitee**-hosted, and by source inspection has neither checksum nor progress callback.

**Capability matrix (which library actually has all four features):**

| | resume w/ remote-identity validation | true multi-segment | checksum | progress callback |
|---|---|---|---|---|
| `pypdl` | ✅ (URL+ETag) | ✅ | ✅ | ✅ |
| `pySmartDL` | ⚠️ within-run only; no state file | ✅ | ✅ | ❌ (polling) |
| `DownloadKit` | ✅ (size offset) | ✅ | ❌ | ❌ (polling) |
| `aria2p` + `aria2c` | ✅ most mature | ✅ | ✅ | ❌ (polling) |

`pypdl` is the only one with all four in pure Python.

## B2. `pypdl` — verified implementation details

Source read: `pypdl/pypdl.py`, `pypdl/utils.py`, `pypdl/downloader.py` at `raw.githubusercontent.com/mjishnu/pypdl/main/`.

**Location & identity:** `pypdl/pypdl/pypdl.py` exists; the package layout is `__init__.py`, `consumer.py`, `downloader.py`, `producer.py`, `pypdl.py`, `utils.py`. Authorship/metadata from PyPI: author "Jishnu M", MIT, "Production/Status :: 5 - Production/Stable", requires Python >= 3.8, depends on `aiohttp`/`aiofiles`.

### Resume: Range header + per-segment files + ETag-validated JSON sidecar

The resume decision (`utils.py`):

```python
progress_file = file_path + ".json"
overwrite = True

if await aio_os.path.exists(progress_file):
    async with fopen(progress_file, "r") as f:
        progress = json.loads(await f.read())
        if not etag_validation or (
            progress["etag"]
            and (progress["url"] == url and progress["etag"] == etag)
        ):
            segments = progress["segments"]
            overwrite = False

async with fopen(progress_file, "w") as f:
    await f.write(
        json.dumps(
            {"url": url, "etag": etag, "segments": segments},
            indent=4,
        )
    )
```

So the meta file is **`<file_path>.json`** with exactly `{"url", "etag", "segments"}`, and resume is accepted **only if both the URL and the ETag match** (when `etag_validation=True`, the default). This is a stronger and safer contract than yt-dlp's 100-byte size tolerance: if the ETag changed, the partial data is discarded rather than appended to.

The actual ranged resume (`downloader.py`):

```python
if await aiofiles.os.path.exists(segment_path):
    downloaded_size = await aiofiles.os.path.getsize(segment_path)
    if overwrite or downloaded_size > size.value:
        await aiofiles.os.remove(segment_path)
    else:
        self.curr = downloaded_size
...
if self.curr < size.value:
    start = size.start + self.curr
    kwargs.setdefault("headers", {}).update(
        {"range": f"bytes={start}-{size.end}"}
    )
    await self.download(url, segment_path, "ab", **kwargs)

if self.curr != size.value:
    raise Exception(
        f"Incorrect segment size: expected {size} bytes, received {self.curr} bytes")
```

Segment/size parsing (`utils.py`) records `accept-ranges: h.get("accept-ranges", "").lower() == "bytes"` and reads `content-range`'s total via `metadata["content-range"].split("/")[-1]`, and detects `content-length`. **Flagging a real finding:** `accept-ranges` is parsed and stored, but in the code I read the Range request is issued based on `multisegment`/segment table rather than being gated on that parsed `accept-ranges` boolean. I did not trace every call site, so whether a server lacking `Accept-Ranges` is defensively handled is **UNVERIFIED**. Test this yourself against a non-Range server before relying on it.

Segments are individual files named `f"{file_path}.{segment}"` (0-based), with inclusive byte ranges (`Size(start, end)` where `self.value = end - start + 1  # since range is inclusive[0-99 -> 100]`), and any remainder is added to the last segment: `if segment == segments - 1: end += add_bytes`.

### Concurrency

Two distinct knobs, do not confuse them:

- **`segments`** (default **5**) — how many pieces one *file* is split into; these download concurrently via asyncio.
- **`max_concurrent`** (default **1**) — how many *tasks/files* download at once. Set on the constructor: `Pypdl(max_concurrent=2, allow_reuse=True)`.
- `multisegment: bool = True` default — single vs multi-segment.
- `speed_limit: float = 0` — **MB/s** (not bytes/s, unlike yt-dlp's `ratelimit`).

Implementation is `asyncio` + `aiohttp` + `aiofiles` with `iter_chunked(MEGABYTE)` (1 MiB = 1048576), and a `concurrent.futures` pool for the task level. `download()` writes with mode `"wb"` for single-segment and `"ab"` (append) for segment resume.

### Checksum

`hash_algorithms: Union[str, List] = None` — computed **during** download and cached: `_calculate_hash` uses `hashlib.new(algorithm)` per algorithm over file chunks, storing hex digests in `self._cache`. Validation is `FileValidator.validate_hash(correct_hash, algorithm)`, implemented as `return bytes.fromhex(file_hash) == bytes.fromhex(correct_hash)`. The callback receives the `FileValidator`, so validation can happen right after completion.

### Progress

- **Callback:** `callback: Callable = None`, documented as *"The function must accept 2 positional parameters: `status` (bool) indicating if the download was successful, and `result` (FileValidator object if successful, None if failed)."* Note this fires **only on completion**, not continuously.
- **Continuous progress** is by **polling attributes**, not callbacks: `progress` (percent), `current_size`, `remaining_size`, `size`, `speed` (MB/s), `eta`, `time_spent`, `completed`, `success`, `failed`, `total_tasks`, `completed_tasks`, `task_progress`.
- `block=False` returns an `EFuture`/`AutoShutdownFuture`; the README states calling `.result()` is **essential** when `block=False` "so everything is properly cleaned up".
- `display: bool = True` prints its own console progress; set `display=False` to suppress.

### Other API surface worth knowing for a media pipeline

- `Pypdl(allow_reuse=False, logger=..., max_concurrent=1)`; methods `start()`, `stop()`, `shutdown()`, `set_allow_reuse()`, `set_logger()`, `set_max_concurrent()`.
- `start()` raises `RuntimeError` if a download is already in progress: `raise RuntimeError(f"Pypdl already running {tasks}")`, and `TypeError` if both `tasks` and `url` are given.
- `mirrors` — retry a failed download against alternate URLs.
- `retries: int = 0` — **default is zero**, same trap as yt-dlp's `fragment_retries` API default.
- `overwrite: bool = True` — default overwrites, so a naive re-`start()` throws away resume state rather than resuming. **Set `overwrite=False` to get resume behaviour.** This is the most important gotcha in the library.
- Passes through aiohttp kwargs: `params`, `data`, `json`, `cookies`, `headers`, `auth`, `allow_redirects`, `max_redirects`, `proxy`, `proxy_auth`, `timeout` (default `aiohttp.ClientTimeout(sock_read=60)`), `ssl`, `proxy_headers`. README explicitly warns: *"multi-range headers are not supported"* — you cannot send a `Range` requesting multiple ranges.

## B3. `pySmartDL` — verified implementation details (and an important caveat)

Source read: `pySmartDL/pySmartDL.py` at `raw.githubusercontent.com/iTaybb/pySmartDL/master/` (25,872 bytes).

**It is not GitHub-API-verified via the core endpoint** (rate-limited), but the code is real and readable, and its metadata was later obtained via the **search API**: **208 stars, last push 2026-04-13T17:08:59Z, not archived, Unlicense**. Note the split: the **repository is actively pushed**, but the **newest PyPI release is 1.3.4 from 2020-09-19**, and PyPI lists Python 3.4–3.8 only. "Actively maintained" is therefore true of the repo and false of the published package.

**Constructor signature (verified):**

```python
def __init__(self, urls, dest=None, progress_bar=True, fix_urls=True, threads=5, timeout=5,
             logger=None, connect_default_logger=False, request_args=None, verify=True):
    ...
    self.threads_count = threads
```

**Concurrency = `threads`, default `5`.** Two important behaviours around it:

```python
if not utils.is_HTTPRange_supported(self.url, timeout=self.timeout):
    self.logger.warning("Server does not support HTTPRange. threads_count is set to 1.")
    self.threads_count = 1
if os.path.exists(self.dest):
    self.logger.warning('Destination "{}" already exists. Existing file will be removed.'.format(self.dest))
```

This is a genuinely good pattern worth copying: **probe for Range support before segmenting**, and fall back to a single thread when the server does not support it. (Contrast with `pypdl`, where I could not confirm the parsed `accept-ranges` value gates the request.)

**⚠ The critical caveat: `SmartDL` deletes an existing destination file.** The warning above is emitted in the constructor, and the only re-download avoidance is hash-based:

```python
if self.verify_hash and os.path.exists(self.dest):
    if utils.get_file_hash(self.hash_algorithm, self.dest) == self.hash_code:
        self.logger.info("Destination '%s' already exists, and the hash matches. No need to download." % self.dest)
```

So **without `add_hash_verification(...)` configured, an existing destination is removed rather than resumed.** "Resume" here means the `resume()` method continuing a *paused in-process download* (`pause()`/`resume()`/`retry()` are documented in the docstring), **not** cross-process crash recovery.

**Cross-run resume: no state file.** A second independent source read (`pySmartDL/download.py`) confirms the per-thread Range request and explicit HTTP 416 handling:

```python
def download(url, dest, requestArgs=None, context=None, startByte=0, endByte=None, ...):
    req = urllib.request.Request(url, **requestArgs)
    if endByte:
        req.add_header('Range', 'bytes={:.0f}-{:.0f}'.format(startByte, endByte))
    ...
    except urllib.error.HTTPError as e:
        if e.code == 416:   # Requested Range Not Satisfiable -> wait & retry
```

No `.part` file and no state/meta file were found; `filesize_dl` starts at 0 per thread and the destination is opened `'wb'` (truncating). Its only cross-run "resume" is the hash shortcut. **UNVERIFIED:** the body of `post_threadpool_actions` (which concatenates the per-thread files) could not be fetched — the segment file naming `dest+".%.3d"` and the pool launch *are* verified, the concatenation implementation is not. Treat "no cross-run resume" as strongly indicated but not exhaustively proven, since the file was not read end-to-end.

**Segmentation and assembly (verified):**

```python
args = utils.calc_chunk_size(self.filesize, self.threads_count, self.minChunkFile)
...
for i, arg in enumerate(args):
    req = self.pool.submit(
        download, self.url, self.dest+".%.3d" % i, self.requestArgs, self.context,
        arg[0], arg[1], self.timeout, self.shared_var, self.thread_shared_cmds, self.logger)
```

Each thread writes its own file `dest.000`, `dest.001`, … (3-digit zero-padded index), and a `post_threadpool_actions` thread combines them (`utils.combine_files`). Partial files live **beside** the destination with a numeric suffix — there is **no JSON/ETag sidecar**, so nothing validates that the remote file is unchanged.

**Integrity check on completion (verified):**

```python
if expected_filesize:  # if not zero, expected filesize is known
    threads = len(args[0])
    total_filesize = sum([os.path.getsize(x) for x in args[0]])
    diff = math.fabs(expected_filesize - total_filesize)
    # if the difference is more than 4*thread numbers (because a thread may download 4KB extra per thread because of NTFS's block size)
    if diff > 4*1024*threads:
        SmartDLObj.logger.warning(errMsg)
        SmartDLObj.retry(errMsg)
```

Its tolerance is `4 KiB × threads` (an NTFS block-size allowance), compared with yt-dlp's flat 100 bytes. Failed hash verification triggers `try_next_mirror(HashFailedException(...))` — mirrors are a first-class concept here (the constructor takes a **list** of `urls`).

**Progress:** no callback. `get_progress()` returns *"the current progress of the download, as a float between 0 and 1"*; there is also `get_progress_bar(length=20)`, a `status` attribute (values seen: `"downloading"`, `"combining"`), and a `thread_shared_cmds['limit'] = speed/self.threads_count` speed-limiting mechanism.

## B3b. `DownloadKit` — source-verified, but two features are absent

Hosted canonically on **Gitee** (`gitee.com/g1879/DownloadKit`); a GitHub mirror exists at `g1879/DownloadKit` (**35 stars, last push 2025-03-25T03:24:47Z, BSD-3-Clause** via search API). PyPI `downloadkit` (note: the distribution name is `DownloadKit`) is by **g1879**, not the `gwwg` handle in the brief — `gwwg/downloadkit` returns 404 and I could not confirm such a project exists anywhere.

Verified constructor defaults: `def __init__(self, goal_path=None, roads=10, session=None, file_exists='rename', driver=None)`, with `self.split = True` and `self.block_size = '50M'`.

**Range gating and split logic** (`DownloadKit/downloadKit.py::_download`):

```python
if file_exists == 'add' and full_Path.exists():
    mission.data.offset = full_Path.stat().st_size
...
if split and file_size and file_size > self.block_size and r.headers.get('Accept-Ranges') == 'bytes':
    first = True
    chunks = [[s, min(s + self.block_size, file_size) - 1] for s in range(0, file_size, self.block_size)]
    chunks[-1][-1] = ''
```

and the per-task request:

```python
kwargs['headers']['Range'] = f"bytes={task.range[0]}-{task.range[1]}"
```

```python
def _do_download(r, task, first=False):
    block_size = 131072  # 128k
    ...
    task.add_data(next(r_content), seek=b * block_size + task.mission.data.offset)
```

Two things stand out. First, this library **does gate segmentation on `Accept-Ranges: bytes`** — the defensive check whose absence I could not rule out in pypdl. Second, resume offset is derived purely from **existing file size** (`file_exists='add'`), with **no ETag/Last-Modified validation**, so a changed remote file at the same URL would be silently spliced.

**Significant structural difference: there is no merge step.** Tasks write into the *same* destination file at `seek` offsets (`seek=b * block_size + task.mission.data.offset`), unlike pypdl (per-segment files + `combine_files`) and pySmartDL (per-thread files + concatenation). Concurrency is `roads=10` simultaneous missions, each driven by a `Thread`.

**No checksum and no progress callback were found** in `downloadKit.py` or `mission.py`; progress is polled via `mission.rate` / `mission.wait()` / `show()`. **UNVERIFIED as a negative:** the full repo tree could not be enumerated (only `__init__.py`, `downloadKit.py`, `mission.py` were confirmed to exist), so a helper in a module not located remains possible. Source comments are GBK-encoded Chinese and render as mojibake when read as UTF-8; the code logic is unaffected.

## B4. `aria2c` — verified flags from the official manual

Read from <https://aria2.github.io/manual/en/html/aria2c.html>. Defaults quoted directly:

| Flag | Default | Doc text |
|---|---|---|
| `-c, --continue` | (off) | *"Continue downloading a partially downloaded file. Use this option to resume a download started by a web browser or another program which downloads files sequentially from the beginning. Currently this option is only applicable to HTTP(S)/FTP downloads."* |
| `-x, --max-connection-per-server` | **1** | *"The maximum number of connections to one server for each download."* |
| `-s, --split` | **5** | *"Download a file using N connections. … The number of connections to the same host is restricted by the --max-connection-per-server option."* |
| `-k, --min-split-size` | **20M** | *"aria2 does not split less than 2\*SIZE byte range."* Possible values `1M`–`1024M`. |
| `--checksum=TYPE=DIGEST` | (none) | *"Set checksum. TYPE is hash type. … This option applies only to HTTP(S)/FTP downloads."* |
| `-V, --check-integrity` | **false** | validates piece/file hashes; re-downloads damaged pieces |
| `-m, --max-tries` | **5** | *"Set number of tries. 0 means unlimited."* |
| `--retry-wait` | **0** | seconds between retries; also governs 503 retry |
| `--lowest-speed-limit` | **0** | *"Close connection if download speed is lower than or equal to this value(bytes per sec)."* — the analogue of yt-dlp's `throttledratelimit` |
| `--max-concurrent-downloads` (`-j`) | **5** | number of *items* downloaded concurrently (distinct from `--split`) |
| `--load-cookies` / `--save-cookies` | (none) | Firefox3/Chromium SQLite or Netscape cookies.txt |

**Resume semantics — the key difference from yt-dlp** (manual, "Resuming Download" and "Control File"):

> "Usually, you can resume transfer by just issuing same command (aria2c URI) if the previous transfer is made by aria2. If the previous transfer is made by a browser or wget like sequential download manager, then use `--continue` option to continue the transfer."

> "aria2 uses a control file to track the progress of a download. A control file is placed in the same directory as the downloading file and its file name is the file name of downloading file with `.aria2` appended. For example, if you are downloading `file.zip`, then the control file should be `file.zip.aria2`. … Usually a control file is deleted once download completed. If aria2 decides that download cannot be resumed (for example, when downloading a file from a HTTP server which doesn't support resume), a control file is not created. Normally if you lose a control file, you cannot resume download."

So aria2's partial state is a **`.aria2` control file**, and resume is **automatic for aria2-initiated downloads** (`-c` is only needed to adopt a foreign partial file). This is a meaningfully different model from yt-dlp's `.part` + "final file exists ⇒ skip".

`aria2p` (572 stars, pushed 2026-09-29, ISC) is a **wrapper**: it needs the `aria2c` binary and talks to it over JSON-RPC. This is confirmed from its own source — the package docstring reads *"Command-line tool and library to interact with an aria2c daemon process with JSON-RPC"*, with `DEFAULT_HOST = "http://localhost"`, `DEFAULT_PORT = 6800`, `DEFAULT_TIMEOUT: float = 60.0`, and endpoint `f"{self.host}:{self.port}/jsonrpc"`. It contains **no HTTP download code of its own**; resume/concurrency/checksum are whatever you pass through the opaque `options` argument to `add()`/`add_uris()`/`add_magnet()`/`add_torrent()`/`add_metalink()`. Progress is **polled, not pushed**: `Download.progress` (`completed_length / total_length * 100`), `progress_string()`, `download_speed`, `eta` (a `timedelta`), `completed_length`, `total_length`, plus `verify_integrity_pending`. Note the cost: shipping a C++ daemon plus an RPC service, and no callback API.

---

# Cross-cutting findings relevant to an unstable VPN

These follow from the source facts above:

1. **The single most dangerous default for this use case is `fragment_retries` = 0 via the API** while the CLI gets 10 (`fragment.py` docstring). If you embed yt-dlp for HLS/DASH media over a flaky link, explicitly set `fragment_retries` (and `retries`).
2. **`pypdl` defaults to `overwrite=True` and `retries=0`** — both must be overridden for resumable behaviour (PyPI API reference).
3. **Resume correctness differs by library and should drive the choice.** yt-dlp tolerates ±100 bytes of size drift (issue #175 comment) and wipes the partial on a bad `Content-Range`; pypdl keys on `(url, etag)` and deletes the segment on mismatch. ETag-keyed resume is the safer contract for a pipeline that re-fetches the same URL after a VPN drop.
4. **yt-dlp gains nothing from `concurrent_fragment_downloads` on a plain progressive HTTP file** — it is HLS/DASH only (`fragment.py` docstring). For multi-connection download of a single plain file you need pypdl/aria2, or yt-dlp's `http_chunk_size`.
5. **`throttledratelimit` (yt-dlp) and `--lowest-speed-limit` (aria2)** are the two mechanisms that detect "the connection is alive but stalled" — which is the characteristic failure of an unstable VPN — as opposed to pure error-based retry.

---

# Explicitly unverified items (consolidated)

- `pySmartDL`'s `post_threadpool_actions` body (the segment-concatenation step) — unfetchable; segment naming and pool launch are verified, the merge implementation is not.
- `pySmartDL` cross-run resume as an exhaustive negative — no `.part`/state file observed, but the file was not read end-to-end.
- `DownloadKit` checksum support as an exhaustive negative, and its full file list (only `__init__.py`, `downloadKit.py`, `mission.py` confirmed to exist).
- `aria2p`'s resume semantics beyond "opaque `options` pass-through" — no call was traced through to a live aria2c daemon.
- Whether `gwwg/downloadkit` exists anywhere (the GitHub URL 404s; PyPI's `downloadkit` belongs to g1879).
- **No runtime/execution verification was performed for any library.** Every finding about Target B is a static source + documentation read. No packages were installed and no downloads were performed.
- `pushed_at` is GitHub's push timestamp, not necessarily the last commit date on the default branch.
- `aria2p`'s Python-level progress-callback API.
- Whether raising an arbitrary exception from a yt-dlp `progress_hooks` callback is supported.
- Whether yt-dlp has a documented memory leak in embedded/long-running use — no citable source found; do not assert this.
- Whether there is an official yt-dlp recommendation for asyncio integration.
- Whether `yt_dlp.utils` exceptions are formally a stable public API.
- Whether pypdl defensively handles servers that omit `Accept-Ranges` (parsed and stored, but I did not confirm it gates the Range request).
- Whether `AbirHasan2005/pySmartDL` or `iTaybb/pySmartDL` is canonical (PyPI metadata points to `iTaybb`).
- Exact yt-dlp `retries` **API** default: `RetryManager(self.params.get('retries'), ...)` has no literal fallback in the API path, and the docstring says only `retries: Number of times to retry for expected network errors.` without a default. CLI default is 10. **Set it explicitly.**
