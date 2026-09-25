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
(`/main/writer/{book_id}/publish/{item_id}?enter_from=modifydraft`). Creating chapters
still happens in Fanqie — see the next section for why.

### Chapter creation is NOT available as an API (verified 2026-09-25)

This was tested against a real logged-in session, on the user's own throwaway book
《测试啊》(`book_id=7689461729293503512`). **Do not claim auto-chapter-creation is supported.**

| Attempt | Measured result |
| --- | --- |
| `save_draft(book_id, item_id="")` | Rejected: `code=-2004` (chapter-creation related) |
| Click 「新建章节」and watch network | **Zero** author API calls — it is a pure front-end route change |
| Open editor with `item_id=0` | Page loads, but `GET /api/author/edit_article/v0/?...&item_id=0` returns `{"code":-2,"message":"文章ID为空"}` |

Conclusion: **Fanqie does not expose a "create chapter" endpoint.** The chapter id is
generated by Fanqie's own front end, so the only ways to obtain an `item_id` are:

1. The user creates the chapter once in the Fanqie web UI, then YLCraft reads it from
   `GET /book/{book_id}/chapters` (already implemented — that is the auto-mapping panel).
2. Drive the browser (Patchright) to perform the create-and-save flow, which is a much
   larger, more fragile piece of work and has **not** been built.

A useful detail for anyone revisiting this: the editor route is
`/main/writer/{book_id}/publish/{item_id}?enter_from=newchapter`, and loading it triggers
`edit_article` / `check_trafficed_book` — so a future browser-driven flow has a known entry
point. But until such a flow exists, publishing still requires one manual chapter.

The author-profile response also contains `phone_number`, `identity_name_mask` and
`identity_code_mask`. These are passed through for display only: never persist them,
never write them to logs, and never place them in model context.

These platform routes are mounted dynamically from
`backend/app/services/platforms/fanqie/routes.py`, so they do not appear in the generated
`docs/architecture/API_SURFACE.md` (the generator only walks `backend/app/api/v1/` plus a
hardcoded Bilibili entry). This is a pre-existing generator limitation, not a missing route.

## Safe Publishing Flow

1. In Fanqie Web, manually create a dedicated empty test chapter whose title contains `[TEST]`.
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

## Agent Contract

Read-only tools: `list_fanqie_my_books`, `get_fanqie_book_stats`, `get_fanqie_hot_list`, `preview_fanqie_project_publish`, and `get_fanqie_project_publish_status`.

`publish_fanqie_project_chapter` is `write`, receives an explicit `item_id`, and is stopped by Agent runtime confirmation. The built-in Creative Director profile receives all six tools and is instructed to preflight before any publish attempt.

## Current Gaps

- Live draft-save and project-to-Fanqie end-to-end validation still require the user's own cookie and an isolated `[TEST]` chapter.
- Profile, remote chapter-list, and earnings APIs require a logged-in browser capture before implementation.
- The integration saves drafts only. No automatic production publish or automatic remote chapter creation is permitted.
