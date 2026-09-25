# Fanqie Author Platform Guide

## Scope

YLCraft integrates the Fanqie author console as a publishing and creator-data platform. It is not a public novel crawler and does not create books, volumes, or chapters on a user's behalf.

The main implementation is split deliberately:

| Layer | Location | Responsibility |
| --- | --- | --- |
| Platform client | `backend/app/services/platforms/fanqie/` | Cookie normalization, request/error handling, hot list, books, statistics, draft save. |
| Connection validation | `backend/app/services/platform_connection/fanqie.py` | Validate a configured Fanqie cookie without writing remote content. |
| Project publishing | `backend/app/services/platforms/fanqie/publish_service.py` | Shared local preflight, then `novel_body` -> Fanqie HTML -> draft request -> `ProjectPublishRecord`. |
| HTTP APIs | `backend/app/services/platforms/fanqie/routes.py`, `backend/app/api/v1/creative_fanqie.py` | Read data, project binding, draft-save and publish-record endpoints. |
| UI | `frontend/src/pages/story/FanqiePublishPanel.tsx`, `frontend/src/pages/my-data/FanqieDataPanel.tsx`, `frontend/src/pages/inspiration/` | Project draft saving, creator data and hot-list inspiration. |
| Agent tools | `backend/app/services/agent/tools/fanqie_tools.py` | Read data, local publish preflight, publish status and confirmed draft save. |

## Credential Rules

- The platform uses `PlatformConnection(platform="fanqie", auth_type="cookie")`.
- The cookie stays in `PlatformConnection.cookie_content`; API responses, Agent tool results, logs and prompts must never return it.
- Project binding and draft-save endpoints reject a missing or non-Fanqie `conn_id` before any remote request. A successful local preflight therefore proves the content and target identifiers are locally executable; it does not prove a cookie is still valid remotely.
- A connection test may call only a verified read endpoint. A failed or expired cookie must return a direct remediation error, never retry silently.
- Never add a one-off script containing real cookies, `msToken`, CSRF tokens, item IDs tied to production chapters, or browser request dumps. Put local cookies in the ignored `.local/` directory or `FANQIE_COOKIE` only for the duration of a test.

## Available APIs

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/fanqie/my/books` | List the current author's books. |
| `GET` | `/api/v1/fanqie/book/{book_id}/stats` | Read verified book statistics. |
| `GET` | `/api/v1/fanqie/hot-list` | Read hot-list inspiration. |
| `GET` | `/api/v1/fanqie/my/profile` | Read author profile (name, description, avatar, points, level). |
| `GET` | `/api/v1/fanqie/book/{book_id}/volumes` | List volumes of a book. |
| `GET` | `/api/v1/fanqie/book/{book_id}/chapters` | List existing chapters; the returned `item_id` is the publish target, so the publish panel can auto-map instead of pasting IDs. |
| `GET` | `/api/v1/fanqie/book/{book_id}/drafts` | List the **draft box**. Drafts are a separate stage from chapters — see below. |
| `GET` | `/api/v1/fanqie/earnings` | Earnings / revenue analysis. |
| `GET` | `/api/v1/creative-projects/{project_id}/fanqie/binding` | Read project publishing target. |
| `POST` | `/api/v1/creative-projects/{project_id}/fanqie/binding` | Set connection, book and volume target for a project. |
| `GET` | `/api/v1/creative-projects/{project_id}/fanqie/publish-preflight` | Validate the local body and resolved target without contacting Fanqie. |
| `GET` | `/api/v1/creative-projects/{project_id}/fanqie/publish-status` | Read local `ProjectPublishRecord` entries. |
| `POST` | `/api/v1/creative-projects/{project_id}/publish-to-fanqie` | Save selected `novel_body` chapters as remote drafts (`action` only accepts `draft`). |

### Captured contracts (2026-09-25)

Author profile, volume list and chapter list were captured from a real logged-in session
(browser-skill driving the user's own Chrome). Evidence was exported to the ignored
`.local/` directory; no cookie or signature value was extracted or stored.

| Capability | Real endpoint | Notes |
| --- | --- | --- |
| Author profile | `GET /api/author/account/info/v0/` | Returns author name, description, avatar, points, level. **It does not return total reads or total followers** — those are per-book / data-centre metrics. |
| Chapter list | `GET /api/author/chapter/chapter_list/v1` | Params: `book_id`, `volume_id`, `page_index` (**0-based**), `page_count`, `status`. Response `data.item_list[]` carries `item_id` (publish target), `index`, `title`, `word_number`, `article_status`. |
| Volume list | `GET /api/author/volume/volume_list/v1` | Chapters are grouped by volume; `volume_id` is required to publish into an existing chapter. |
| Earnings | `GET /api/author/income/book_list/v0/` | Params `page_count` / `page_index` (**0-based**). Returns `total_count`, `is_cp`, `income_book_list[]`. An **empty list is a real result** (the book has no earnings yet), not an error. |

The earnings page lives behind a **hover-expanded second-level menu** whose items have no
anchor tags and no usable accessibility refs; synthesised mouse events do not trigger React
either. It was reached by reading the node's React fiber and invoking its `onClick` handler
directly, which revealed the real route `/main/writer/profit`. A guessed
`/main/writer/income-analysis` returned **404** — do not guess these routes.

Earnings figures are sensitive: display only, never persist, log, or place in model context.

### Creating a draft IS available as an API (corrected 2026-09-26)

> **Correction.** This guide previously stated that Fanqie exposes no chapter-creation
> endpoint and that a manual chapter was required. **That was wrong.** The mistake came
> from capturing only the 「新建章节」 entry (`?enter_from=newchapter`), which really is a
> pure front-end route with zero author API calls, while missing the 「新建草稿」 entry
> (`?enter_from=newdraft`) — which *does* call a real endpoint.

```
POST /api/author/article/new_article/v0/     (form: aid, app_name, book_id)
=> {"code":0,"data":{"item_id":"<new draft id>","volume_id":"...","latest_version":0,
                     "media_id":...,"volume_data":[{volume_id,volume_name}],"is_reuse":1}}
```

So the full automatic path — **no manual chapter needed** — is:

```python
item_id = (await client.create_draft(book_id))["item_id"]
await client.save_draft(book_id=book_id, item_id=item_id, ...)   # writes the body
```

Verified end-to-end on a real account: `create_draft` → `item_id 7689533897855468056`;
`save_draft` → `latest_version: 1`; reading back via `edit_article` returned the expected
title and body.

**This is a write and is NOT idempotent** — every call adds another draft to the box, so
the HTTP route requires an explicit `confirm=true` and nothing retries it automatically.

Earlier measurements that remain true (they explain the confusion):

| Attempt | Result |
| --- | --- |
| `save_draft` with empty `item_id` | Rejected: `code=-2004` — an `item_id` is required |
| Click 「新建章节」and watch network | Zero author API calls (pure front-end route) |
| Open editor with `item_id=0` | `edit_article` → `{"code":-2,"message":"文章ID为空"}` |
| Open `/publish/?enter_from=newdraft` | **`POST new_article/v0/` → allocates a real `item_id`** |

Route shapes that were confirmed (do not guess them):
`/main/writer/{book_id}/publish/{item_id}?enter_from=modifydraft` for an existing draft,
`?enter_from=newdraft` for a fresh one, `/main/writer/chapter-manage/{book_id}&{title}?type=1`
for chapter management.

### Drafts and chapters are two stages of one record (verified 2026-09-26)

This is the single most confusing thing about publishing to Fanqie, and it was
confirmed against a real account:

```
新建草稿 ──写正文──> 存草稿 ──> 【草稿箱】(item_id writable)
                        │
                        └─「下一步」→ 内容检测 → 发布设置 → 确认发布
                                        │
                                        └─> 【章节管理】(article_status=2 published)
```

Consequences that are easy to get wrong:

- A draft **does not** appear in `chapter_list`, and a published chapter **does not**
  appear in `draft_list`. Querying only one of them will look like "nothing exists".
- Both share the same `item_id`. Writing a body to a draft's `item_id` works
  (`save_draft` → `latest_version` increments), which is how YLCraft's
  "save to Fanqie draft" path operates.
- So the intended workflow is: YLCraft writes into a draft, then **the user** opens
  Fanqie and clicks 「下一步 → 发布」. YLCraft deliberately does not publish.

| Stage | Endpoint | Response field | `index` |
| --- | --- | --- | --- |
| Draft box | `GET /api/author/chapter/draft_list/v1` | `data.draft_list[]` | always `-1` |
| Chapter list | `GET /api/author/chapter/chapter_list/v1` | `data.item_list[]` | 1-based order |

Two traps, both pinned by tests in `tests/test_fanqie_drafts.py`:

1. **Do not guess the path.** `draft/list/v1` and `article/draft_list/v0/` both
   returned **404**; the real one is `chapter/draft_list/v1`.
2. **The response field is `draft_list`, not `item_list`.** Reading `item_list` from the
   draft endpoint silently yields `[]`, which looks exactly like "no drafts".

The publish panel therefore loads **both** lists and labels drafts as 【草稿】, and offers
「打开番茄建章」 / 「在番茄打开本章」 buttons that open the corresponding Fanqie page
(`/main/writer/{book_id}/publish/{item_id}?enter_from=modifydraft`).

The panel also has 「让 YLCraft 新建番茄草稿」, which calls
`POST /api/v1/fanqie/book/{book_id}/drafts?confirm=true` and fills in the new `item_id`,
so **no manual chapter is required** — see "Creating a draft IS available" below.

The author-profile response also contains `phone_number`, `identity_name_mask` and
`identity_code_mask`. These are passed through for display only: never persist them,
never write them to logs, and never place them in model context.

These platform routes are mounted dynamically from
`backend/app/services/platforms/fanqie/routes.py`, so they do not appear in the generated
`docs/architecture/API_SURFACE.md` (the generator only walks `backend/app/api/v1/` plus a
hardcoded Bilibili entry). This is a pre-existing generator limitation, not a missing route.

## Safe Publishing Flow

1. Create a target draft — pick **either** route:
   - click 「让 YLCraft 新建番茄草稿」in the publish panel
     (`POST /api/v1/fanqie/book/{book_id}/drafts?confirm=true` → new `item_id`), **or**
   - create an empty chapter/draft manually in Fanqie Web and select it from the panel.
   Use a throwaway book and title test entries with `[TEST]`.
   Draft creation is a **write and is not idempotent** — never retry it automatically.
2. In YLCraft platform connections, save and validate the Fanqie cookie.
3. Bind the project to that connection, `book_id`, `volume_id`, and volume name.
4. Select the exact project `novel_body` content and the isolated test chapter `item_id`.
5. Run the shared local preflight endpoint (or Agent tool `preview_fanqie_project_publish`). It resolves explicit values over the project binding, checks the content type/body and verifies the referenced connection exists and is `fanqie`; it reports `missing` fields without using or returning a cookie or contacting Fanqie.
6. Only after a user confirms the exact target may the UI draft-save action or `publish_fanqie_project_chapter` run. The Agent tool is a `write` tool, does not silently retry, and records the result locally.
7. Verify the returned `remote_version` and the resulting `ProjectPublishRecord` before attempting a second update.

For an explicit live smoke check, use the safe script:

```powershell
$env:FANQIE_COOKIE = Get-Content -Raw .\.local\fanqie-cookie.txt
& backend\venv_win\Scripts\python.exe tools\test_fanqie_client.py --live `
  --book-id <test-book-id> --volume-id <test-volume-id> --item-id <test-item-id>
Remove-Item Env:FANQIE_COOKIE
```

The script refuses to write without the required IDs and forces `[TEST]` into the title. It is the only supported live test harness.

For a repeatable check of the **whole publish loop** (project → binding → auto draft →
publish → record), use:

```powershell
& backend\venv_win\Scripts\python.exe tools\e2e_fanqie_project_publish.py --port 8024 --cleanup
```

Verified green on a real account (2026-09-26): `status=success`, `remote_version=1`,
and a remote `draft_list` re-read showed `title='[YLCraft E2E] 第1章'`, `word_number=280`.

It issues a temporary external API key and revokes it at the end, and hard-fails if
pointed at the finished book 《短剧世界不准我降智》. **It writes to the real draft box.**

Two response-parsing traps it pins down:

- `publish-to-fanqie` returns each item as `{"content_id","success","record"|"error"}` —
  `record` is **nested**; reading `status` flat silently yields `None`. An early version of
  the script reported "failed" while the DB row was already `status=success`.
- `publish-status` returns `data` as a **flat list**, not `{"records": [...]}`.

Always re-read the remote after publishing — a `success` response is not proof the
content landed.

## Agent Contract

Read-only tools: `list_fanqie_my_books`, `get_fanqie_book_stats`, `get_fanqie_hot_list`, `preview_fanqie_project_publish`, and `get_fanqie_project_publish_status`.

`publish_fanqie_project_chapter` is `write`, receives an explicit `item_id`, and is stopped by Agent runtime confirmation. The built-in Creative Director profile receives all six tools and is instructed to preflight before any publish attempt.

## Current Gaps

- Live draft-save and project-to-Fanqie end-to-end validation still require the user's own cookie and an isolated `[TEST]` chapter.
- Profile, remote chapter-list, and earnings APIs require a logged-in browser capture before implementation.
- The integration saves drafts only. No automatic production publish or automatic remote chapter creation is permitted.
