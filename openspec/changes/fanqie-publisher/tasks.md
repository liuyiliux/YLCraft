# Tasks

> **进度总览（2026-08-08）**：✅ Phase 0 / 1 / 2 / 4 / 5 代码完成；✅ Phase 3 的 C/D 接口 + 前端「我的数据」完成；✅ Phase 6 离线测试、发布预检 API/UI、Agent 工具和文档完成；🟡 E 组（作家资料/章节/收益，任务 21/23/25）待用户登录态抓包；⏳ 真实测试章与项目端到端联调（7/31/32）待用户环境。
> 详见 `proposal.md`（实施状态 + What changes 表）与 `design.md`（接口/前端落地细节）。
>
> **2026-09-25 更新（browser-skill 抓包轮）**：E 组三项**已全部用 browser-skill 接管用户已登录 Chrome 抓到真实契约并落地**——任务 21（作家资料 `account/info/v0/`）、23（章节列表 `chapter_list/v1`，附带发现卷列表 `volume_list/v1`）、25（收益 `income/book_list/v0/`）。收益页路由为 `/main/writer/profit`（猜测的 `income-analysis` 实测 404，靠 React fiber 调用 onClick 才拿到真实路由）。前端发布面板支持从番茄拉取章节列表并自动填入 `item_id`，取代手动粘贴；「我的数据」新增「收益」Tab。
> **仍待用户侧**：7 / 31 / 32 需要真实账号写路径（有效 Cookie + 自建 `[TEST]` 章节）。

## Phase 0: FanqieClient 核心（已验证接口落地）

- [x] 1. 新建 `app/services/platforms/fanqie/{apis,client,routes,utils}.py` 骨架，`client.py` 定义 `@register_platform("fanqie") class FanqieClient(BasePlatformClient)`。
- [x] 2. 实现 `parse_netscape_cookie(text) -> dict`（`fanqie/utils.py`），并加 `normalize_cookie` 兼容 Netscape/原始两种 `cookie_content`。
- [x] 3. 实现 `get_hot_list(type=0)`（`GET douyin_hot_list/v0/`），返回 `data` 字典 —— **已实测 200/code:0**。
- [x] 4. 实现 `save_draft` / `save_draft_from_markdown`（`POST cover_article/v0/`）—— **已实测 200/code:0**。
- [x] 5. 实现 `_call()` 统一出口：校验 HTTP、解析 JSON、按 `code` 分类 `CookieExpiredError` / `ParamError` / `RiskControlError` / `FanqieError`（登录页重定向也判为 CookieExpired）。
- [x] 6. 实现 `markdown_to_fanqie_html(md)` 简易转换（段落包 `<p>`、行内 `<br>`、HTML 转义、粗体/斜体/代码）。
- [ ] 7. 用**独立测试章节**（标题含 `[TEST]`、独立 `item_id`）真实验证 `save_draft` 返回 `latest_version` —— 待用户用自有 cookie + 自建测试章跑 `tools/test_fanqie_client.py --live`（脚本已就绪，离线单测已过）。
  - _阻塞结论（2026-09-24 复核）：**代码侧无法再推进，卡在"需要真实番茄账号 Cookie + 自建测试章 item_id"**。脚本已就绪且默认离线，`--live` 也只允许 `[TEST]` 标题、独立 item_id，不会碰线上内容；执行需用户提供本机 `.local/` 凭证（**不得入库、不得写进仓库**）。解封命令：`backend\venv_win\Scripts\python.exe tools\test_fanqie_client.py --live`。_
- [x] 8. 收敛为 `tools/test_fanqie_client.py`：默认只跑离线单测；`--live` 强制 `[TEST]` 标题 + 独立章 ID + cookie 仅从文件/环境变量读取，绝不入库、绝不复用线上内容。

## Phase 1: 创作项目发布闭环（核心场景）

- [x] 9. 新增 `ProjectPublishRecord` 模型（`project_id / content_id / conn_id / book_id / item_id / chapter_number / action / remote_version / post_url / status`），见 `design.md` 映射章节↔番茄 item_id。**已在 `db/models/creative_project.py` 落地，纳入 `init_db()` 自动建表。**
- [x] 10. 项目绑定存储：在 `CreativeProject.settings_json.fanqie` 存 `{ conn_id, book_id, volume_id, volume_name }`，由 `FanqiePublishService.get_binding/set_binding` 读写。
  - _更正（2026-09-25）：原文声称「`PlatformType.FANQIE` 已加（`platform_connection.py` + `database.py` 的 `_PG_ENUM_VALUES`）」——**`database.py` 里从来没有 `_PG_ENUM_VALUES`，全仓无此代码**，PostgreSQL 的 `platformtype` 原生枚举因此一直缺值。实测创建番茄连接报 `psycopg2 invalid input value for enum platformtype: "FANQIE"`。已新增迁移 `047_add_fanqie_platform_type` 补上大写 `'FANQIE'`（SQLAlchemy 对 `enum.Enum` 字段默认存 name/大写；库里另有一批历史遗留小写值但未被使用），已 `upgrade head` 并验证查询路径可用。_
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
- [x] 21. 实现 `get_my_profile(writer_id)` → `UserProfile`（昵称 / 头像 / 总阅读 / 总粉丝）
  - _2026-09-25 **已完成（browser-skill 抓包落地）**：真实端点为 `GET /api/author/account/info/v0/`。抓包方式为 browser-skill 接管用户已登录 Chrome → 打开作家后台 → 读真实请求与响应；证据导出 `.local/fanqie-e-group-capture.json`（不入库），未提取或保存任何 Cookie / 签名值。_
  - _**与原描述的偏差（已如实修正）**：该接口返回的是「作家名 / 简介 / 头像 / 积分 / 等级」，**不返回总阅读与总粉丝**——那两个属作品级或数据中心指标，应走 `get_book_stats(book_id, stats_type=...)`。实现按真实字段落地，未为凑原描述而伪造字段。_
  - _**隐私边界**：响应含 `phone_number` / `identity_name_mask` / `identity_code_mask`，仅透传展示，**不落库、不写日志、不进模型上下文**。_
  - _落地物：`apis.py` 的 `ACCOUNT_INFO`、`client.get_my_profile()`、`routes.py` 的 `GET /my/profile`、前端 `getFanqieMyProfile`；新增 7 例契约测试。_
- [x] 22. 实现 `get_my_books(...)` → 书籍列表（已验证 `book_list/v0`，已对齐真实分页参数 page_count/page_index，返回 `data.item_list`）。
- [x] 23. 实现 `get_book_chapters(book_id)` → 章节列表（回填后自动映射 `item_id`，替代手动粘贴）
  - _2026-09-25 **已完成（browser-skill 抓包落地）**：真实端点为 `GET /api/author/chapter/chapter_list/v1`，参数 `book_id` / `volume_id` / `page_index`（**0 起**）/ `page_count` / `status`；响应 `data.item_list[]` 提供 `item_id`（**发布目标 ID**）、`index`、`title`、`word_number`、`article_status` 等。_
  - _配套发现并落地卷列表 `GET /api/author/volume/volume_list/v1`（发布到已有章节需要 `volume_id`），因此路由比原计划多一条 `GET /book/{book_id}/volumes`。_
  - _易错点已处理：番茄分页是 0 起的 `page_index`，对外 `page` 是 1 起，内部转换并有专门测试固定（`page=1 → index=0`、`page=2 → index=1`）。_
  - _前端已接：`FanqiePublishPanel` 新增「拉取章节列表」按钮 + 选章下拉，选中后自动填入 `item_id` 与 `volume_id`，不再需要手抄 ID。_
  - _安全：纯只读 GET；`index` 可对齐项目 `chapter_number`，但**发布前仍应人工确认**——映射错章节会写到错误位置。_
- [x] 24. 实现 `get_book_stats(book_id, stats_type=1)` → 阅读量 / 追读 / 投票 / 推荐票（已验证 `book_common_v1/v0`，已加 `stats_type` 支持数据中心各 Tab）。
- [x] 25. 实现 `get_earnings(writer_id, period)` → 收益 / 分成 / 打赏
  - _2026-09-25 **已完成（browser-skill 抓包落地）**：真实端点为 `GET /api/author/income/book_list/v0/`，参数 `page_count` / `page_index`（0 起）。响应 `data` 含 `total_count` / `is_cp` / `income_book_list[]`；**实测该书暂无收益，返回 `{"total_count":0,"is_cp":0,"income_book_list":[]}`——空列表是真实结果，不得当成接口异常**。_
  - _抓包过程值得记录：收益页藏在**悬停展开的二级菜单**里，DOM 无 a 标签、无可用 snapshot ref，合成 MouseEvent 也不触发 React。最终通过**读取节点上的 React fiber，直接调用其 `onClick` 处理器**才跳转成功，得到真实路由 `/main/writer/profit`。此前猜测的 `/main/writer/income-analysis` **实测 404**——再次印证「不猜路径」。_
  - _落地物：`apis.py` 的 `INCOME_BOOK_LIST`、`client.get_earnings()`、`routes.py` 的 `GET /earnings`（替换 `not_captured` 占位）、前端 `getFanqieEarnings` + 「我的数据」新增「收益」Tab。_
  - _隐私：收益数字属敏感信息，仅展示用，不落库、不写日志、不进模型上下文。_
- [x] 26. 各方法映射为 `routes.py`：C/D 已真实映射（`/my/books`、`/book/{id}/stats` 透传结构化 data）；E 组三个端点保留 `not_captured` 占位，待抓包后替换。
  - _2026-09-25 已替换完毕：E 组三条（`/my/profile`、`/book/{book_id}/chapters`、`/earnings`）全部改为真实实现，并新增 `/book/{book_id}/volumes`；`routes.py` 中已无 `not_captured` 残留（有测试固定这一点）。_
- [x] 26b. **前端「我的数据」页接入番茄**（本次 B 任务）：`api/index.ts` 加 `getFanqieMyBooks` / `getFanqieBookStats`；新建 `pages/my-data/FanqieDataPanel.tsx`（自包含：选番茄连接 → 书籍网格 → 点选看统计卡片 + stats_type 切换「基础/质量/流量」→ 热榜 Tab 卡片 + 引导去灵感广场）；`pages/my-data/index.tsx` 加平台 `Segmented`（B站/番茄），修复 early-return（两类都无才提示），番茄分支渲染 `FanqieDataPanel`。esbuild 语法校验 PASS。

## Phase 4: 热榜灵感

- [x] 27. 接入 `get_hot_list`（已验证），前端「灵感」入口展示热门故事；提供「转成创作项目选题」按钮（调 `creative-projects` 建项目/大纲草稿）。**实现：`api/index.ts` 加 `getFanqieHotList`；新建 `pages/inspiration/index.tsx`（选连接→加载热榜→卡片展示→「转为创作选题」Modal 调 `createCreativeProject(source_type=fanqie_hot, source_ref={book_id...})`→navigate('/story')）；`App.tsx` 路由 `/inspiration` + `AppLayout.tsx` 侧边栏「灵感广场」（BulbOutlined）。esbuild 语法校验 PASS。**

## Phase 5: 通用发布页 / Agent 集成（可选）

- [x] 28. 补全 `POST /api/v1/platforms/{conn_id}/publish`（article 类型）→ `FanqieClient.save_draft`：番茄要求显式 `target.book_id / volume_id / item_id`，支持 `dry_run` 校验，避免自由撰稿遗漏远端章节目标。
- [x] 29. 暴露 Agent tools（发布 / 查数据），受平台管理凭证约束，含预检与确认：`fanqie_tools.py` 提供书架/统计/热榜、项目发布预检、发布记录和远端草稿写入；Cookie 不进入模型上下文，`publish_fanqie_project_chapter` 标记为 `write` 并由运行时确认拦截。真实写入仍只允许独立 `[TEST]` 章节。UI 和 Agent 预检均复用 `FanqiePublishService.preview_chapter()`。

## Phase 6: 验证与文档

- [x] 30. 单元测试：`parse_netscape_cookie`、错误分类（mock `code!=0` / 302 登录页）、`markdown_to_fanqie_html`（离线 pytest 覆盖；真实登录页重定向仍在 live 验证中）。
- [ ] 31. 集成验证：独立测试章节 `save_draft` + `publish` 真实走通；`get_hot_list` / `get_my_books` / `get_book_stats` 真实返回；cookie 过期场景提示正确。
  - _阻塞结论（2026-09-24 复核）：**代码侧已无可做的验证**。只读三项（热榜/书架/统计）此前已实测返回；剩下缺的是**真实账号下的写路径**（草稿 + 发布）与**真实 Cookie 过期**这类只有账号侧才会发生的场景。与任务 7 同一把钥匙：用户提供有效 Cookie + 自建 `[TEST]` 章节。失败必须回显可读原因（CookieExpired / RiskControl / ParamError 已分类），不做静默重试。_
  - _**2026-09-25 实测推进（Cookie 已就绪）**：用户通过「浏览器」方式成功登录并保存番茄连接（`platform=fanqie / status=active / acq=patchright / hasCookie=True`）。用该 Cookie 实测：_
    - _`GET /my/profile` → 真实返回作家资料（逸流AI / 积分 200 / 等级 100），**只读链路完全打通**_
    - _`GET /my/books` → `total_count=2`，含《测试啊》`book_id=7689461729293503512`（**注意字段名是 `stats_book_list`，不是 `book_list`**）_
    - _`GET /book/{id}/volumes` → 第一卷：`volume_id=7689461731638119448`，`item_count=0`_
    - _`GET /book/{id}/chapters` → `total_count=0`（**该书确实 0 章，空列表是真实结果**）_
    - _**写路径实测结论（关键）**：以空 `item_id` 调 `save_draft` → 服务端拒绝 `code=-2004`（新建章节相关）。**证实番茄要求 `item_id` 必须已存在，即章节须先在番茄 Web 端创建过**；`save_draft` 只推送正文、不建章（与现有注释一致）。_
  - _**「自动建章」可行性（已实测界定，不臆断）**：此前抓包观察到点「新建章节」时前端会预分配 `item_id`（URL 变 `/main/writer/{book_id}/publish/{item_id}?enter_from=newchapter`），但服务端章节列表仍为空——**章节在保存时才真正创建**。因此「自动建章」等价于「拿到预分配 item_id 后直接 save_draft」，需进一步抓包确认该预分配 ID 是否可由接口获得；**在确认前不得宣称支持自动建章**。_
- [ ] 32. 创作项目发布联调：建项目 → 生成 `novel_body` → 绑定番茄 → 发布到测试章 → 校验 `ProjectPublishRecord`。
  - _阻塞结论（2026-09-24 复核）：**必须等 31 的真实写路径解封后才能做**，否则会在"发布必失败"的环境里空跑一遍还要人工核对失败记录。解封后按既有 UI/Agent 路径：绑定（`settings_json.fanqie`）→ 发布前预检 → 写 `[TEST]` 草稿 → 逐条核对 `ProjectPublishRecord.status/remote_version/post_url`。_
  - _**2026-09-26 写路径已解封（实测）**：用户手动在草稿箱建了一个草稿，其 URL 提供了 `item_id`。用它真实调用 `save_draft` → 返回 `{'latest_version': 3}`，**随后回读 `edit_article` 确认标题与正文均已写入**——这是番茄写路径首次真正跑通（此前所有尝试都被 `code=-2004` 拒绝）。_
  - _**新增能力：草稿箱列表**。实测发现番茄的**草稿**与**章节**是同一份数据的两个阶段：草稿只在草稿箱、不会出现在 `chapter_list`；点「下一步 → 发布」后才进入章节列表。故新增 `GET /api/v1/fanqie/book/{book_id}/drafts`（真实端点 `GET /api/author/chapter/draft_list/v1`，靠 Patchright 复用已保存 Cookie 抓包确认；猜测的 `draft/list/v1`、`article/draft_list/v0/` 实测均 404）。响应字段是 `draft_list[]` 而**非** `item_list[]`（按 `item_list` 取值会静默得到空数组）。已实测返回用户 3 个草稿（含 YLCraft 自动写入的那条）。_
  - _**前端已接**：发布面板「拉取草稿与章节」同时拉两个列表并标【草稿】；新增「打开番茄建章」「在番茄打开本章」跳转按钮（`fanqieWebUrls`），把"去番茄点发布"这一步做到一键可达。建章仍由用户在番茄完成（番茄无建章接口，见上）。_
- [x] 33. 更新平台管理文档：新增 `docs/platform/FANQIE_GUIDE.md`，说明 cookie 凭证边界、`FanqieClient` 统一请求层、已实现 HTTP/Agent 工具、安全 `[TEST]` 章节隔离和真实联调命令；删除 3 个含硬编码真实会话数据的遗留抓包脚本，新增忽略的 `.local/` 凭证目录，仅保留安全 live harness。
- [x] 34. 把笔名「逸流AI」创作定位（有趣 / 不反智 / 拒绝无脑爽文）记入项目 memory（**已落地**）：已写入长期记忆（标题「笔名『逸流AI』创作定位与内容调性」），并写明三条各自的含义——有趣靠设定与情境的巧思而非堆爽点、不反智即角色行为与情节推进讲得通不靠降智、拒绝无脑爽文即不用无冲突升级/无逻辑碾压充数且冲突要有来由与代价；生成或润色任何发布内容（尤其 `novel_body`、章节标题、简介）时按此把关，与定位冲突的方案改到符合为止。
