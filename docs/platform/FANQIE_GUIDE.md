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
| `GET` | `/api/v1/creative-projects/{project_id}/fanqie/binding` | Read project publishing target. |
| `POST` | `/api/v1/creative-projects/{project_id}/fanqie/binding` | Set connection, book and volume target for a project. |
| `GET` | `/api/v1/creative-projects/{project_id}/fanqie/publish-preflight` | Validate the local body and resolved target without contacting Fanqie. |
| `GET` | `/api/v1/creative-projects/{project_id}/fanqie/publish-status` | Read local `ProjectPublishRecord` entries. |
| `POST` | `/api/v1/creative-projects/{project_id}/publish-to-fanqie` | Save selected `novel_body` chapters as remote drafts (`action` only accepts `draft`). |

`/my/profile`, `/book/{book_id}/chapters`, and `/earnings` intentionally return `not_captured` until a user-owned logged-in browser capture establishes their actual contracts. Do not fabricate response fields.

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
