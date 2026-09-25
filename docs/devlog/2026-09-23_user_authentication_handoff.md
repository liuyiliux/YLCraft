# 2026-09-23 User Authentication Handoff

## Scope and current goal

The active OpenSpec change is `user-authentication`. Its original Phase 2 (models/migrations) and Phase 3 (sessions/password/login rate limiting) are implemented. The immediate product goal is to finish the browser-level acceptance path and then safely complete the remaining ownership and authorization work without weakening the existing external Agent Key behavior.

Read these files before editing:

1. `AGENTS.md`
2. `docs/README.md`
3. `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`
4. `docs/architecture/API_SURFACE.md`
5. `docs/AI_HANDOFF_PROTOCOL.md`
6. `openspec/changes/user-authentication/design.md`
7. `openspec/changes/user-authentication/tasks.md`

Run `git status --short --branch` before touching anything. The worktree is intentionally dirty with user/other-agent changes. Do not revert or overwrite unrelated changes.

## Implemented behavior

### Account and session model

- Migration `045_add_users_sessions_and_owners` creates `users` and `user_sessions`, and adds nullable `owner_user_id` fields to `creative_projects`, `asset_nodes`, `project_task_records`, `video_generation_tasks`, and `model3d_generation_tasks`.
- Migration `046_add_user_email_reservation` adds nullable, unique `users.email`. It is only a database/API reservation. There is no email verification, email login, password reset, provider configuration, or email notification capability. Do not describe those as enabled.
- Human users authenticate via a server-side `user_sessions` record and an HttpOnly `ylcraft_session` cookie. Database storage retains only the SHA-256 hash of the opaque session token.
- External Agents still authenticate with `ylk_...` External API Keys. Human sessions and External API Keys are parallel mechanisms: API endpoints that use `get_authenticated_principal` accept either.
- Password hashes use `bcrypt`; plaintext passwords must never go to logs, source code, documentation, test snapshots, or Git.
- Login failure throttling is an in-process sliding window keyed by `(username, client IP)`: default five failures in 900 seconds; behavior is configurable via `YLCRAFT_LOGIN_FAILURE_LIMIT` and `YLCRAFT_LOGIN_FAILURE_WINDOW_SECONDS`. `429` includes `Retry-After` and a readable cooldown message. This must move to Redis/shared storage before multi-worker/public deployment.

### Historical data ownership

The user explicitly requested that historical data be claimed by the local `root` account. This operational step was completed as one database transaction, only where `owner_user_id IS NULL`:

| Table | Claimed rows |
|---|---:|
| `creative_projects` | 17 |
| `asset_nodes` | 236 |
| `project_task_records` | 109 |
| `video_generation_tasks` | 26 |
| `model3d_generation_tasks` | 9 |

The root account exists in the local database. Its credential is user-provided and must not be copied into a source file, an OpenSpec document, a temporary script, a Git commit, or a handoff note. The account id is not needed for normal development; retrieve it only from the DB when an authorized maintenance action needs it.

The migration itself intentionally does not fill historical ownership. The one-time root claim above is an environment-specific operations action, not code that belongs in the migration. New installations should preserve the documented `NULL = legacy` semantics until an explicitly approved migration/operations plan is made.

### Login page

- The login screen is available at `http://127.0.0.1:3000/login`.
- Generated visual asset: `frontend/public/login/studio-background.png`.
- Page implementation: `frontend/src/pages/auth/LoginPage.tsx`; supporting client auth code is under `frontend/src/auth/` and `frontend/src/api/`.
- The image-generation API key supplied by the user was used only to generate the image and was not retained in the repository. Do not add it to `.env`, source files, tests, or Git.

## Important bug fixed today

PostgreSQL uses `timestamp without time zone` for the account/session tables. `asyncpg` rejects aware Python datetimes for those columns with:

```text
TypeError: can't subtract offset-naive and offset-aware datetimes
```

The affected symptoms were `500` from registration or `POST /api/v1/auth/login` when inserting `users` or `user_sessions`.

Fix now present in `backend/app/db/models/user.py`:

- `User.created_at` and `User.updated_at` default to naive UTC.
- `UserSession.created_at` and `UserSession.updated_at` default to naive UTC.
- Their `onupdate` callbacks also return naive UTC.
- `backend/app/api/v1/auth.py` creates login timestamps as naive UTC, so `last_login_at` and `expires_at` match the existing schema.
- `backend/tests/test_user_auth_models.py` has a regression test asserting all four automatic timestamps are naive.

`backend/app/core/user_auth.py` intentionally uses aware UTC for comparison logic, then normalizes database values with `_as_aware(...)`. Do not blindly make that module all-naive: session expiry comparisons need a consistent, aware current time. Values written to the existing database columns must remain naive unless a separately planned schema migration changes them to `TIMESTAMP WITH TIME ZONE`.

## Last known validation

Completed after the timezone correction:

```powershell
cd F:\PycharmProjects\YLCraft\backend
.\venv_win\Scripts\python.exe -m pytest tests/test_user_auth.py tests/test_user_auth_models.py -q
# 9 passed

cd F:\PycharmProjects\YLCraft
openspec validate user-authentication --strict
# Change 'user-authentication' is valid

git diff --check
# no whitespace errors; only existing CRLF conversion warnings
```

Manual HTTP verification was also completed locally:

```text
POST /api/v1/auth/login -> 200
GET /api/v1/auth/me with returned cookie -> 200
```

The backend on port 8000 must be running from `backend/venv_win`; do not use system Python because this repository's dependency set is only guaranteed in the project environment.

## Recommended next plan

### Step 1: Do the real browser smoke test for task 18

This is the highest priority. Do not mark task 18 complete based only on tests. Start the backend and frontend if needed, then use a browser to execute the actual UI path:

1. Open `http://127.0.0.1:3000/login` in a clean browser session.
2. Sign in with the already-created local root account; do not place its password in test files or terminal history that will be committed.
3. Refresh the page and confirm that `AuthProvider` restores the HttpOnly-cookie session through `GET /api/v1/auth/me`.
4. Navigate to Creative Projects, create a small test project, and confirm it appears in the UI.
5. Verify its `owner_user_id` is the logged-in user via an authorized API/DB inspection; do not accept client-supplied owner fields as proof.
6. Run one inexpensive existing generation path only if its provider is locally configured. If a provider is unavailable, record the human-readable failure reason and test owner creation through a non-provider project action instead. Do not claim generation passed when the provider was not exercised.
7. Log out from the UI, refresh, and confirm protected routing redirects to `/login` and the prior session cookie no longer authenticates `GET /auth/me`.
8. Record exact browser observations under task 18 and only mark it complete when all applicable steps pass.

Use browser inspection rather than trusting the UI alone. The app should return `401` cleanly after logout; an unexpected `500` means inspect the backend log and first verify timestamp types as described above.

### Step 2: Finish task 14 before claiming ownership control complete

Current partial coverage is only strong for Creative Projects. Extend focused API tests to real async task/asset routes:

1. Authenticated user A creates/starts a persistent image, video, and model-3D task through real application routes or service boundaries.
2. Assert every persisted record has A's `owner_user_id` set by the server.
3. Authenticate user B and prove reads, cancellation, retry, deletion, and task retrieval reject B for A-owned resources.
4. Seed or retain a `NULL` owner record and prove it remains readable under the legacy policy while it remains intentionally allowed.
5. Test External API Key behavior separately: it is authenticated but currently has no `user_id` mapping. Never invent an owner id for it. State the expected behavior explicitly in a test before changing it.

Keep task 14 unchecked until these real route flows are covered.

### Step 3: Complete task 12 and task 13 as an audited route inventory

Do not make an unscoped authorization sweep. Build a route list first using `docs/architecture/API_SURFACE.md`, `rg` for router declarations, and existing protected endpoints. For every state-changing route, decide and document one of:

- Requires human session or a valid External API Key.
- Requires a human session specifically because an owner relationship is needed.
- Is explicitly anonymous, with a reason.

Then implement server-side owner assignment and authorization at the lowest existing service/router boundary that consistently applies. Rules that must not change without a dedicated OpenSpec decision:

- Browser clients must not be able to supply `owner_user_id`.
- Human session: new owned resources use the session user's id.
- Existing `NULL` rows remain legacy-accessible until an explicit policy change.
- External API Keys are valid calling credentials but have no `User` mapping today. They cannot be silently treated as root or as the latest human user.
- An invalid explicitly supplied bearer key remains `401`; a valid cookie must not make a malformed presented Agent credential disappear.

For each changed HTTP route, regenerate the API surface:

```powershell
cd F:\PycharmProjects\YLCraft
backend\venv_win\Scripts\python.exe tools\generate_api_surface.py
```

Update `docs/architecture/API_SURFACE.md`, `docs/architecture/api_surface.json`, and the appropriate architecture/domain documentation when semantics change.

### Step 4: Make the email reservation production-ready only in a new change

Do not expand `user-authentication` casually with an email system. The current work only reserves an optional unique field and lets registration send it. A separate OpenSpec change is required before enabling any of:

- email verification and token lifecycle
- mail provider credentials and secret storage
- email login
- password reset
- email change / account recovery
- audit logging, rate limits, replay prevention, and expiry

The UI can later show an optional email field, but it must clearly be treated as an account contact/reservation until verification is actually delivered.

### Step 5: Prepare public/multi-worker deployment intentionally

Before internet exposure or multi-worker deployment:

1. Move login throttling from process memory to Redis or another shared atomic store.
2. Require HTTPS and enable `YLCRAFT_SESSION_COOKIE_SECURE=1` (verify the exact environment name in `app/core/user_auth.py`).
3. Define CORS origins narrowly; cookie auth requires explicit credentials behavior.
4. Audit every generation and destructive route for authentication, authorization, rate limits, and an audit event.
5. Decide whether External API Keys need a first-class owning principal; this requires a data-model decision, migration, tests, docs, and a dedicated OpenSpec change.

## Files most likely to change next

| Purpose | Files |
|---|---|
| Account HTTP endpoints | `backend/app/api/v1/auth.py` |
| Session/password/dependency logic | `backend/app/core/user_auth.py` |
| Ownership guard | `backend/app/core/resource_auth.py` |
| Account models | `backend/app/db/models/user.py` |
| Project route/service ownership | `backend/app/api/v1/creative_projects.py`, `backend/app/services/creative_project/service.py` |
| Asset ownership | `backend/app/api/v1/assets.py`, `backend/app/services/asset_hub/*` |
| Task ownership | `backend/app/api/v1/tasks.py`, `images.py`, `videos.py`, `model3d_workspace.py`, `backend/app/services/task_persistence.py` |
| Browser auth/routing | `frontend/src/auth/*`, `frontend/src/App.tsx`, `frontend/src/components/layout/AppLayout.tsx`, `frontend/src/pages/auth/LoginPage.tsx` |
| Specs and docs | `openspec/changes/user-authentication/*`, `docs/architecture/*`, `docs/guides/external-agent-api.md` |

## Required verification before a future handoff or commit

Run focused checks for each edit, then the broad checks affected by the change:

```powershell
cd F:\PycharmProjects\YLCraft\backend
.\venv_win\Scripts\python.exe -m pytest -q

cd F:\PycharmProjects\YLCraft\frontend
npx tsc --noEmit -p tsconfig.json
npx vitest run
npm run build

cd F:\PycharmProjects\YLCraft
openspec validate user-authentication --strict
git diff --check
```

If routes or Agent tools change, regenerate API surface documentation. If OpenSpec tasks/design/specs change, always run strict validation. For browser-facing changes, actually use the browser before marking an acceptance task done.

## Explicit non-goals and guardrails

- Do not commit credentials, session tokens, password values, generated API keys, database URLs, or root account details.
- Do not add a permanent script containing the root password or raw production/local DB credentials. Use short-lived environment variables only for approved maintenance.
- Do not alter historic ownership migration semantics to force a backfill. The root claim was a one-off local operations action requested by the user.
- Do not claim email login/recovery/verification exists. It does not.
- Do not claim public deployment readiness. In-memory rate limiting and remaining route authorization work make that inaccurate.
- Do not reset, checkout, or broadly clean the current worktree; it contains accumulated intentional work.
