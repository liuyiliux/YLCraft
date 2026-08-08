# Tasks

> **进度总览（2026-08-08）**：✅ Phase 0 / 1 / 2 / 4 / 5 代码完成；✅ Phase 3 的 C/D 接口 + 前端「我的数据」完成；✅ Phase 6 离线测试、发布预检 API/UI、Agent 工具和文档完成；🟡 E 组（作家资料/章节/收益，任务 21/23/25）待用户登录态抓包；⏳ 真实测试章与项目端到端联调（7/31/32）待用户环境。
> 详见 `proposal.md`（实施状态 + What changes 表）与 `design.md`（接口/前端落地细节）。

## Phase 0: FanqieClient 核心（已验证接口落地）

- [x] 1. 新建 `app/services/platforms/fanqie/{apis,client,routes,utils}.py` 骨架，`client.py` 定义 `@register_platform("fanqie") class FanqieClient(BasePlatformClient)`。
- [x] 2. 实现 `parse_netscape_cookie(text) -> dict`（`fanqie/utils.py`），并加 `normalize_cookie` 兼容 Netscape/原始两种 `cookie_content`。
- [x] 3. 实现 `get_hot_list(type=0)`（`GET douyin_hot_list/v0/`），返回 `data` 字典 —— **已实测 200/code:0**。
- [x] 4. 实现 `save_draft` / `save_draft_from_markdown`（`POST cover_article/v0/`）—— **已实测 200/code:0**。
- [x] 5. 实现 `_call()` 统一出口：校验 HTTP、解析 JSON、按 `code` 分类 `CookieExpiredError` / `ParamError` / `RiskControlError` / `FanqieError`（登录页重定向也判为 CookieExpired）。
- [x] 6. 实现 `markdown_to_fanqie_html(md)` 简易转换（段落包 `<p>`、行内 `<br>`、HTML 转义、粗体/斜体/代码）。
- [ ] 7. 用**独立测试章节**（标题含 `[TEST]`、独立 `item_id`）真实验证 `save_draft` 返回 `latest_version` —— 待用户用自有 cookie + 自建测试章跑 `tools/test_fanqie_client.py --live`（脚本已就绪，离线单测已过）。
- [x] 8. 收敛为 `tools/test_fanqie_client.py`：默认只跑离线单测；`--live` 强制 `[TEST]` 标题 + 独立章 ID + cookie 仅从文件/环境变量读取，绝不入库、绝不复用线上内容。

## Phase 1: 创作项目发布闭环（核心场景）

- [x] 9. 新增 `ProjectPublishRecord` 模型（`project_id / content_id / conn_id / book_id / item_id / chapter_number / action / remote_version / post_url / status`），见 `design.md` 映射章节↔番茄 item_id。**已在 `db/models/creative_project.py` 落地，纳入 `init_db()` 自动建表。**
- [x] 10. 项目绑定存储：在 `CreativeProject.settings_json.fanqie` 存 `{ conn_id, book_id, volume_id, volume_name }`，由 `FanqiePublishService.get_binding/set_binding` 读写。**另：`PlatformType.FANQIE` 已加（`platform_connection.py` + `database.py` 的 `_PG_ENUM_VALUES`），否则无法创建 fanqie 凭证。**
- [x] 11. 新增 `app/services/platforms/fanqie/publish_service.py`：`FanqiePublishService.publish_chapter()`（校验 novel_body 非空 → 校验凭证 → 建 pending 记录 → `ClientConfig(cookie=conn.cookie_content)` + `FanqieClient.save_draft(markdown_to_fanqie_html)` → 写 success/failed）、`publish_chapters_bulk()`（单章异常隔离）、`get_publish_status()`。**5 方法 + `_serialize`，3 项单测全过。**
- [x] 12. 路由：**新建独立 `app/api/v1/creative_fanqie.py`**（async session，避开 `creative_projects.py` 的 8s2b 隐患），挂载前缀 `/api/v1/creative-projects`，提供 `POST /{project_id}/publish-to-fanqie`、`POST /{project_id}/fanqie/binding`、`GET /{project_id}/fanqie/binding`、`GET /{project_id}/fanqie/publish-status`；`main.py` 的 `_register_routes()` 已 try/except 注册。**逐章回执，绝不静默重试。**
- [x] 13. 前端 `pages/story/*` 工作台：新建 `FanqiePublishPanel.tsx`（Modal：选 fanqie 连接 / 读存绑定 / 填 item_id / 保存草稿 / 展示 `ProjectPublishRecord` 列表 + 安全 Alert）；`story/index.tsx` 正文区 `extra` 加「保存到番茄草稿」按钮（`disabled={!novelBody}`），挂载面板。**esbuild 语法校验 PASS。**
- [x] 14. `frontend/src/api/index.ts` 加 `setFanqieBinding` / `getFanqieBinding` / `publishChapterToFanqie` / `getFanqiePublishStatus` 4 个函数，复用已有 `listPlatformConnections`。**esbuild 语法校验 PASS。**

## Phase 2: 平台管理接入（零模型改造）

- [x] 15. `PlatformType.FANQIE` 已在 Phase 1 加到 `platform_connection.py` + `database.py` 枚举。**本项补 `api/v1/platforms.py` 的 `SUPPORTED_PLATFORMS` 增加 fanqie 条目**（label=番茄小说, auth_types=[cookie], view/publish/credential 标注），前端据此可创建番茄连接。已验证 `SUPPORTED_HAS_FANQIE=True`。
- [x] 16. 新建 `services/platform_connection/fanqie.py`：`extract_account_info_from_cookie(cookie_str)`（同步 httpx，对齐 bilibili 模板）——用已验证只读接口 `get_my_books` 探活（code==0 即 cookie 存活），并从 cookie 解析 writer_id 写回 `account_id`/`account_url`；作家昵称/头像待 Phase 3 抓包。`service.py` 的 `_test_cookie` 在「直接有效」与「自动转换」两个分支均接入 fanqie（写回 account 字段），已验证 `WIRE_OK`。
- [x] 17. 确认天然适配：**未改任何模型**。`PlatformConnection.cookie_content`（Netscape）+ `AuthType.COOKIE` + `/api/v1/platforms` 的 cookie 凭证读写已覆盖 fanqie；测试连接、保存 cookie 全部复用现有路径。
- [x] 18. `services/platforms/__init__.py` 自动发现列表 `"fanqie"` 已在 Phase 0 加好。**本项在 `main.py` 的 `_register_routes()` try/except 挂载 `fanqie_router`，前缀 `/api/v1/fanqie`，tags `["Crawler — Fanqie"]`**（对齐 bilibili 的 `/api/v1/bilibili`）。
- [x] 19. 重写 `services/platforms/fanqie/routes.py`：**3 个已验证接口走真实调用**（`GET /my/books`→`get_my_books`、`GET /book/{id}/stats`→`get_book_stats`、`GET /hot-list`→`get_hot_list`，均只读）；**3 个占位**（`/my/profile`、`/book/{id}/chapters`、`/earnings` 返回 `not_captured` 明确提示，待 Phase 3 抓包）。含 async 会话依赖、`_get_client`（按 conn_id 取 cookie 建 `FanqieClient`）、`_fanqie_error_to_http`（401/400/403/502）。已验证注册 6 条路由。

## Phase 3: 我的数据（抓包补齐）

- [x] 20. 端点表回填：`design.md` 已记录 C/D 真实路径（`book_list/v0`、`book_common_v1/v0`）+ 真实参数（page_count/page_index、stats_type）；E 组（章节/收益/作家资料）端点路径待用户登录态抓包。
- [ ] 21. 实现 `get_my_profile(writer_id)` → `UserProfile`（昵称 / 头像 / 总阅读 / 总粉丝）—— **待抓包**（E 组）。
- [x] 22. 实现 `get_my_books(...)` → 书籍列表（已验证 `book_list/v0`，已对齐真实分页参数 page_count/page_index，返回 `data.item_list`）。
- [ ] 23. 实现 `get_book_chapters(book_id)` → 章节列表（E 组待抓；回填后可自动映射 `item_id`，替代手动粘贴）—— **待抓包**。
- [x] 24. 实现 `get_book_stats(book_id, stats_type=1)` → 阅读量 / 追读 / 投票 / 推荐票（已验证 `book_common_v1/v0`，已加 `stats_type` 支持数据中心各 Tab）。
- [ ] 25. 实现 `get_earnings(writer_id, period)` → 收益 / 分成 / 打赏 —— **待抓包**（E 组）。
- [x] 26. 各方法映射为 `routes.py`：C/D 已真实映射（`/my/books`、`/book/{id}/stats` 透传结构化 data）；E 组三个端点保留 `not_captured` 占位，待抓包后替换。
- [x] 26b. **前端「我的数据」页接入番茄**（本次 B 任务）：`api/index.ts` 加 `getFanqieMyBooks` / `getFanqieBookStats`；新建 `pages/my-data/FanqieDataPanel.tsx`（自包含：选番茄连接 → 书籍网格 → 点选看统计卡片 + stats_type 切换「基础/质量/流量」→ 热榜 Tab 卡片 + 引导去灵感广场）；`pages/my-data/index.tsx` 加平台 `Segmented`（B站/番茄），修复 early-return（两类都无才提示），番茄分支渲染 `FanqieDataPanel`。esbuild 语法校验 PASS。

## Phase 4: 热榜灵感

- [x] 27. 接入 `get_hot_list`（已验证），前端「灵感」入口展示热门故事；提供「转成创作项目选题」按钮（调 `creative-projects` 建项目/大纲草稿）。**实现：`api/index.ts` 加 `getFanqieHotList`；新建 `pages/inspiration/index.tsx`（选连接→加载热榜→卡片展示→「转为创作选题」Modal 调 `createCreativeProject(source_type=fanqie_hot, source_ref={book_id...})`→navigate('/story')）；`App.tsx` 路由 `/inspiration` + `AppLayout.tsx` 侧边栏「灵感广场」（BulbOutlined）。esbuild 语法校验 PASS。**

## Phase 5: 通用发布页 / Agent 集成（可选）

- [x] 28. 补全 `POST /api/v1/platforms/{conn_id}/publish`（article 类型）→ `FanqieClient.save_draft`：番茄要求显式 `target.book_id / volume_id / item_id`，支持 `dry_run` 校验，避免自由撰稿遗漏远端章节目标。
- [x] 29. 暴露 Agent tools（发布 / 查数据），受平台管理凭证约束，含预检与确认：`fanqie_tools.py` 提供书架/统计/热榜、项目发布预检、发布记录和远端草稿写入；Cookie 不进入模型上下文，`publish_fanqie_project_chapter` 标记为 `write` 并由运行时确认拦截。真实写入仍只允许独立 `[TEST]` 章节。UI 和 Agent 预检均复用 `FanqiePublishService.preview_chapter()`。

## Phase 6: 验证与文档

- [x] 30. 单元测试：`parse_netscape_cookie`、错误分类（mock `code!=0` / 302 登录页）、`markdown_to_fanqie_html`（离线 pytest 覆盖；真实登录页重定向仍在 live 验证中）。
- [ ] 31. 集成验证：独立测试章节 `save_draft` + `publish` 真实走通；`get_hot_list` / `get_my_books` / `get_book_stats` 真实返回；cookie 过期场景提示正确。
- [ ] 32. 创作项目发布联调：建项目 → 生成 `novel_body` → 绑定番茄 → 发布到测试章 → 校验 `ProjectPublishRecord`。
- [x] 33. 更新平台管理文档：新增 `docs/platform/FANQIE_GUIDE.md`，说明 cookie 凭证边界、`FanqieClient` 统一请求层、已实现 HTTP/Agent 工具、安全 `[TEST]` 章节隔离和真实联调命令；删除 3 个含硬编码真实会话数据的遗留抓包脚本，新增忽略的 `.local/` 凭证目录，仅保留安全 live harness。
- [ ] 34. 把笔名「逸流AI」创作定位（有趣 / 不反智 / 拒绝无脑爽文）记入项目 memory，保证发布内容调性一致（非代码任务）。
