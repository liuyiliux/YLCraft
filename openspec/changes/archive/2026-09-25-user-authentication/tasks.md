# Tasks

## Phase 1: 契约与边界

- [x] 1. 明确两类调用方（人类会话 / 外部 Agent Key）的语义与优先级（**已落地**）：语义与优先级写在 `design.md`（人类用户＝登录会话 / 外部 Agent＝`ExternalApiKey`，服务端按"任一通过"判定）；外部 Agent API 指南新增「两类调用方：各自用哪种凭据（规划中，尚未启用）」一节，写明三条边界——① **平台凭证 ≠ 供应商凭证**（`ylk_` 只识别调用方，不替代也不得携带供应商 Key）；② **两类凭据不互相替代**，归属以会话或 Key 的主体为准，迁移前历史数据 `owner_user_id` 为空且仍允许访问；③ **开放公网的前置条件**（登录会话可用、破坏性与消耗型操作要求认证、限流与审计就位）在此只声明边界、**不声明已具备**——手册里不能把做不到的写成能力
- [x] 2. 决定会话方案（**已落地**，写在 `design.md`）：**服务端会话表 `user_sessions` + HttpOnly Cookie 优先**——理由是本项目需要**可即时失效**（登出、踢下线）的能力，无状态 JWT 做不到；若前端将来必须纯静态无状态部署，可退回 Bearer/JWT，但**必须在文档里写明"签发后无法即时吊销"这个代价**（design 已记录该备选与代价）。Cookie 口径：`HttpOnly` + `SameSite=Lax`（或 Strict），公网部署加 `Secure`。
- [x] 3. 定义归属策略（**已落地**，写在 `design.md`）：`owner_user_id` **可空**且 **NULL 视为迁移前遗留数据、仍允许访问**；**新数据必须带 owner**；回填**不在本次做**（先可空、再逐步收紧），读取侧提供开关以便灰度收紧。

## Phase 2: 数据模型与迁移

- [x] 4. 新增 `User` 模型（username/password_hash/display_name/is_active/时间戳）与 Alembic 迁移：`045_add_users_sessions_and_owners` 创建 `users`；`username` 与后续会话 token hash 由数据库唯一索引兜底。模型只留 `password_hash`，不承载明文密码；哈希算法与写入服务留给任务 7，避免本切片提前启用半套认证。
- [x] 5. 新增 `UserSession` 模型（token hash、user_id、过期、撤销标记）与迁移：同一迁移创建可即时吊销的 `user_sessions`，`token_hash` 唯一、关联 `users.id`，并为用户、过期与撤销查询建索引。Cookie 签发、滑动续期及登出撤销仍在任务 8。
- [x] 6. 为 `creative_projects`、`asset_nodes` 及任务类账本增加 `owner_user_id`（可空），不立即回填：覆盖可恢复任务账本 `project_task_records` / `video_generation_tasks` / `model3d_generation_tasks`。所有字段可空并有 `users.id` 外键和索引；迁移不写回历史数据，NULL 继续表示迁移前遗留数据，读取授权策略留给任务 12。

## Phase 3: 认证能力

- [x] 7. 实现密码哈希与校验（passlib/argon2 或 bcrypt），禁止自实现与明文存储：使用 `bcrypt`，密码 UTF-8 最大 72 字节，`hash_password` / `verify_password` 不接受自实现散列或明文存储。
- [x] 8. 实现注册/登录/登出/当前用户接口；登出必须使会话失效：新增 `/api/v1/auth/register`、`/login`、`/logout`、`/me`；会话 token 仅通过 HttpOnly Cookie 返回，库中仅保存 SHA-256 hash；登出把当前 `UserSession.is_revoked` 置 true 后删除 Cookie。
- [x] 9. 实现 `get_current_user` / `get_current_user_optional` 依赖，并与 `optional_external_api_key` 组合为"任一通过"：`get_authenticated_principal` 返回用户或外部 Key 主体；显式无效 Bearer Key 仍返回 401，不会被同请求 Cookie 绕过。尚未把依赖挂到业务端点，任务 13 统一完成。
- [x] 10. 增加登录失败限流（按用户名 + IP）与失败审计日志（脱敏）：进程内滑动窗口由 `YLCRAFT_LOGIN_FAILURE_LIMIT`（默认 5）和 `YLCRAFT_LOGIN_FAILURE_WINDOW_SECONDS`（默认 900）配置；只记用户名/IP，绝不记密码或 token。后续多进程部署可换 Redis。
  - _2026-09-23 可读性补强：达到阈值返回 `429`，响应同时提供 `Retry-After` 秒数和中文冷却提示；成功登录会清除该用户名 + IP 的失败记录。_
- [x] 11. 后端测试：哈希、登录/登出/失效、会话过期、依赖组合、限流：`tests/test_user_auth.py` 覆盖上述场景；模型/迁移契约在 `test_user_auth_models.py`。
  - _2026-09-23 修复：PostgreSQL 当前会话表使用无时区 `timestamp`，模型的四个审计时间默认值也必须写入无时区 UTC；此前遗漏 `updated_at`，会在登录创建会话时触发 asyncpg 的时区类型错误。回归测试固定该契约。_

## Phase 4: 归属与授权

- [x] 12. 写入侧自动填 `owner_user_id`；读取侧按归属过滤（提供开关以便逐步收紧）。
  - _2026-09-22 部分落地：会话用户创建项目、图片/视频/图转 3D 资产和 `project_task_records` / 视频 / 图转 3D 账本时由服务端写入 owner，客户端不接收 owner 参数；项目、素材列表/详情、持久媒体任务读取按「本人或 NULL 遗留数据」过滤。外部 Key 尚无 `user_id` 主体，保持已认证但不伪造 owner，需独立迁移后才能完成其归属语义。其余历史写路径未逐一收口，任务不能勾选。_
  - _2026-09-24 收口：两条上传路径（`/assets/upload`、`/assets/upload-model3d`）改为要求「会话或有效外部 Key」，并把会话主体写入 `owner_user_id`——此前上传只接受 `optional_external_api_key`，产物 owner 为 NULL，不算归属到账号。素材更新、缩略图、恢复也加了归属校验，NULL 遗留数据仍可写（避免开启账号后历史素材变只读）。_
  - _2026-09-24 核实：创作项目侧不需要逐路由补——`_ProjectAuthRouter` 已对全部 `{project_id}` 路由自动注入 `require_project_access`，生成类子路由同样覆盖。曾给 `PATCH /{project_id}` 手加校验，属重复且会双查，已撤销。_
  - _新增 `tests/test_asset_ownership_api.py`（3 例）固定：他人资产更新/恢复 403、匿名 401、NULL 遗留可写、上传无凭据 401 且写入会话 owner。_
- [x] 13. 为破坏性与消耗型操作（删除任务、取消、重试、生成类）增加认证要求。
  - _2026-09-22 部分落地：`/creative-projects` 创建/删除、`/assets/{id}` 删除、`/tasks/{id}` 取消/重试/删除，以及 `/images/generate`、`/videos/generate`、`/model-3d/generate` 走「会话或有效外部 Key」；对持久媒体任务和项目/素材所有者再做越权拒绝。尚未覆盖所有创作项目生成及历史消耗型入口，不能勾选。_
  - _2026-09-24 核实覆盖：`/model-3d/rig`、`/model-3d/retarget`、`/images/generate-outline`、`/images/generate-batch*`、`/images/platform-templates` 写操作、`/asset-hub` 节点/版本/表示写操作均已带认证与归属校验。创作项目全部 `{project_id}` 路由由 `_ProjectAuthRouter` 覆盖。_
  - _本项按任务字面范围勾选：删除任务、取消、重试与生成类入口已全部要求认证并做越权拒绝。剩余的非归属类写入口（见「待办与风险」的独立 change 项）不在本项范围内。_
- [x] 14. 后端测试：归属写入、越权访问被拒、遗留 NULL 数据仍可访问。
  - _2026-09-23 补强：`tests/test_creative_project_workflow_api.py::test_project_routes_write_owner_reject_other_user_and_keep_legacy_visible` 已用真实创作项目路由验证服务端自动写入 owner、另一会话用户读到 403、NULL 遗留项目仍可读。_
  - _2026-09-23 完成：新增 `tests/test_task_ownership_api.py`，走真实 `/api/v1/tasks` 路由验证持久视频/3D 任务账本——归属任务对本人可见可改、对另一会话用户读/取消/重试/删除返回 403、NULL 遗留任务仍可读、匿名调用者只能读到 NULL 且写操作 401、外部 Key 只读可见但不被冒充为人类 owner。_
  - _2026-09-23 顺带修复越权：此前匿名调用者与"内部直调哨兵"共用 `None` 分支，且详情判断里的 `or {task_id}` 会在无遗留记录时放行，导致匿名可读他人持久任务；现改为显式区分匿名 `None` 与非 principal 哨兵，匿名只返回 NULL 遗留记录。_

## Phase 5: 前端与文档

- [x] 15. 增加登录页、会话保持与未登录跳转；请求层统一携带会话凭据。
  - _2026-09-22 落地：`AuthProvider` 通过 `/auth/me` 恢复 HttpOnly 会话；`RequireAuth` 在未登录时保存原目标并跳转 `/login`；注册后自动登录；`AppLayout` 显示当前用户并支持登出。通用 API 客户端携带 `credentials: 'include'`，Cookie 是唯一会话凭据，不存 token。_
  - _2026-09-23 视觉收口：登录页改为全屏摄影棚背景 + 左侧品牌引导 + 右侧窄表单工具面板，移动端改为纵向布局；使用 `frontend/public/login/studio-background.png`，不改变认证交互与校验。_
- [x] 16. 前端登录后把归属信息透传给生成请求，使产物可归属到用户。
  - _2026-09-22 落地：归属由服务端从 Cookie 会话主体推导，前端不接收或伪造 `owner_user_id`。图片、视频、图转 3D 请求及独立生成入口均携带 `credentials: 'include'`；`src/api/auth.test.ts` 固定认证 API 调用的 Cookie 口径。_
- [x] 17. 更新架构文档、API Surface 与外部 Agent API 指南，说明两类凭据与启用公网模式的前置条件。
  - _2026-09-23 完成：`YLCRAFT_SYSTEM_ARCHITECTURE.md`、`external-agent-api.md` 已按事实写明 Cookie 会话、前端守卫、ExternalApiKey 无用户主体映射和公网 HTTPS `Secure` 前置；`tools/generate_api_surface.py` 已生成 Authentication 路由与 JSON 清单。_
- [x] 18. 前端构建 + OpenSpec 严格校验 + 真实浏览器 smoke（登录 → 创建项目 → 生成 → 校验归属）。
  - _2026-09-23 代码侧验证完成：`npx tsc --noEmit -p tsconfig.json`、`npx vitest run`（19 files / 330 tests）、`npm run build` 均通过，`openspec validate user-authentication --strict` 通过。_
  - _2026-09-23 真实浏览器 smoke 完成（headless Chrome，1440x900）：`POST /auth/login -> 200`；刷新后 `GET /auth/me -> 200` 且 Header 显示登录用户；`POST /creative-projects -> 200` 且服务端写入的 `owner_user_id` 等于会话用户 id；注销后 `GET /auth/me -> 401`、匿名访问 `/story` 被重定向到 `/login`。_
  - _2026-09-23 生成与归属实测：图像页发起真实文生图，`POST /images/generate -> 200`（siliconflow-Kolors），返回素材节点写入 `asset_nodes`，只读数据库查询确认该节点 `owner_user_id` 与 `users.username='root'` 的 id 一致。验收临时项目已删除，账号凭据未写入仓库。_

## 待办与风险（非任务）

- **2026-09-23 本地运维数据认领已执行**：已创建本地 `root` 账号，并在单一数据库事务内将 `creative_projects`、`asset_nodes`、`project_task_records`、`video_generation_tasks`、`model3d_generation_tasks` 中原 `owner_user_id IS NULL` 的历史记录全部归属该账号；账号凭据未写入仓库或提交 Git。

- **邮箱上线预留（未启用）**：`users.email` 已加为可空唯一字段，注册请求可选择性保存；当前没有邮件验证、邮箱登录、通知或找回密码。上述能力应以独立 change 接入发送供应商、验证 token、改绑与审计，避免本地开发阶段误发邮件。

- **解锁 #25 遗留限制**：完成后，公网模式可改为要求"会话 或 ExternalApiKey"，从而不再出现"开启强鉴权即界面 401"。需验证：界面登录后调用 `GET /assets/{asset_id}` 与任务读接口返回 200。

- **剩余非归属类写入口需独立 change（2026-09-24 核实）**：`/assets/{id}/provenance-clean`、标签相关写入（`/assets/tags`、`/asset-hub` 标签写路径）、`/asset-hub/seed-tags`，以及部分 Agent 工具直调路径仍无认证要求。它们不写 `owner_user_id`、不改变归属，但属服务端写操作；本次不为凑进度扩大范围，故记为结论而非残留勾选。收口时应与「外部 Key 补 `user_id` 主体」一起做，避免同一批接口分两次改语义。
- 首版不做第三方登录、RBAC、找回密码。
