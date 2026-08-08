# Proposal: 番茄作家后台 API 客户端（FanqieAuthorClient）

> 本变更由早期的「fanqie-publisher（仅发布）」升级而来。经真实抓包验证后，
> 明确番茄作家后台整站走 Web API（无原生签名），因此把范围扩展为
> **对标 B站 my-data 的完整客户端**：既能发布，也能查看「我的数据」、拉热榜灵感。

## 实施状态（2026-08-02 更新）

- ✅ **已完成**：Phase 0（FanqieClient 核心）、Phase 1（创作项目发布闭环）、Phase 2（平台管理接入，零模型改造）、Phase 3 中的 C/D 接口（书籍/统计真实调用 + 真实分页/统计参数）、Phase 4（热榜灵感）、Phase B（我的数据前端接入）。
- ⏳ **待做**：
  - Phase 1 真机联调（任务 7）：`tools/test_fanqie_client.py --live` + 前端「保存到番茄草稿」面板实测；
  - Phase 3 E 组抓包（任务 21/23/25）：作家资料 / 章节列表 / 收益——需用户在已登录浏览器抓 cURL 回填；
  - Phase 5：通用发布页 `/platforms/{id}/publish`（article 自由发布）；Agent 集成已完成，剩余真实发布联调；
  - Phase 6：单元测试 / 集成验证 / 文档收尾。
- 凭证快照模型 `NovelBookStat` / `NovelEarning` **未实现**：前端走实时拉取，暂不做趋势快照（后续如要趋势图再补）。

> 进度明细见 `tasks.md`（勾选状态），接口与前端落地细节见 `design.md`。

## What

为 YLCraft 新增**番茄作家后台集成**，核心价值是**打通「写小说/短剧 → 一键保存番茄草稿」的创作闭环**——把现有创作项目（`/story` 工作台）里 `novel_body` 章节正文直接推到番茄作家后台草稿，同时保留对标 B站 my-data 的数据查看与热榜灵感能力。

能力分三块：

1. **草稿保存（核心闭环）**：把创作项目里某章 `novel_body` 成稿一键保存到番茄草稿；支持逐章与批量，回执落 `ProjectPublishRecord` 做章节↔番茄 `item_id` 映射。已实测 `POST cover_article/v0/` 返回 `200 {"code":0}`。正式发布尚未实现。
2. **查看我的数据（My Data）**：对标 B站「我的数据」页，拉取「我的书 / 章节 / 阅读与收益」等创作数据，在 YLCraft 内统一查看。
3. **热榜灵感（Inspiration）**：拉取番茄作家后台「开书灵感 / 热门故事」公域数据，辅助创作选题。已实测 `GET douyin_hot_list/v0/` 返回 `code:0`、21 条。

核心交付：

- `FanqieClient(BasePlatformClient)` 数据采集层（对齐 `services/platforms/bilibili/` 四件套模式），内含发布、我的数据、热榜三类方法。
- `FanqiePublishService`：**创作项目发布编排**，读 `ProjectContent(novel_body)` → 转 HTML → 调 `FanqieClient` → 写 `ProjectPublishRecord`；新增 `POST /api/v1/creative-projects/{pid}/publish-to-fanqie`。
- 平台凭证接入 `PlatformConnection`：番茄登录态 cookie 存 `cookie_content`，`AuthType.COOKIE` 已存在，**零模型改造**。
- 前端：`story` 工作台每章加「保存到番茄草稿」动作 + `my-data` 扩展（或独立 `novel-data` 页）+ 草稿保存入口。
- 安全护栏：所有探针 / 测试一律独立测试章节 + 独立 cookie，绝不复用线上内容。

## Why

- 用户（笔名「逸流AI」）已在番茄作家后台开书写作，希望 YLCraft 统一管理番茄，如同现有 B站：既发布也看数据。
- 经真实抓包 + 真实请求验证：**番茄作家后台走 Web API，无原生签名死胡同**：
  - 无 `X-Argus`/`X-Gorgon`/`signature` 等原生签名头（社区 5 个发布仓库走浏览器的签名问题在作家后台不存在）；
  - body 为明文 HTML 表单 / 明文 JSON，无加密；
  - URL 里的 `msToken`/`a_bogus` 为 Web 端反爬参数，**实测不强制校验**（抓包值直接复用成功）。
- 结论：纯 `httpx + cookie` 即可覆盖**发布 + 热榜**；「我的数据」接口待抓包补齐，但模式与 B站完全一致，工程风险可控。

## What changes

| 层 | 新增 | 修改 | 状态 |
|---|---|---|---|
| Backend | `app/services/platforms/fanqie/{apis,client,routes,utils}.py`（`FanqieClient(BasePlatformClient)`） | 注册进 `services/platforms/__init__.py` 自动发现列表 | ✅ Phase 0 |
| Backend | `app/services/platforms/fanqie/publish_service.py`（`FanqiePublishService`，创作项目发布编排） | — | ✅ Phase 1 |
| Backend | `POST /api/v1/creative-projects/{pid}/publish-to-fanqie`（逐章/批量发布，4 个端点） | **新建 `app/api/v1/creative_fanqie.py`**（独立模块，避开 `creative_projects.py` 的 8s2b 隐患；同前缀 `/api/v1/creative-projects`） | ✅ Phase 1 |
| Backend | `ProjectPublishRecord` 模型（章节↔番茄 item_id/version 映射回执） | `app/db/models/creative_project.py`（直接新增表，纳入 `init_db()` 自动建表） | ✅ Phase 1 |
| Backend | 发布逻辑 `save_draft`/`publish` 作为 `FanqieClient` 方法 | — | ✅（save_draft 已验证；publish 待 E 组后验证） |
| Backend | `PlatformType.FANQIE` 枚举 + `SUPPORTED_PLATFORMS` 条目 | `app/db/models/platform_connection.py`（PlatformType 枚举）+ `app/db/database.py`（PG 枚举同步 `_PG_ENUM_VALUES`）+ `app/api/v1/platforms.py`（SUPPORTED_PLATFORMS） | ✅ Phase 2 |
| Backend | `extract_writer_info()`（仿 bilibili `extract_account_info_from_cookie`） | `app/services/platform_connection/` 新增 `fanqie.py`；`service.py` 的 `_test_cookie` 两分支接入 | ✅ Phase 2 |
| Backend | `main.py` 挂载 `fanqie_router`（`/api/v1/fanqie`） | — | ✅ Phase 2 |
| Backend | 可选快照模型 `NovelBookStat` / `NovelEarning`（支持阅读 / 收益趋势图） | `app/db/models/` | ⏸️ 未实现（前端走实时拉取，暂不做快照） |
| Backend | `/platforms/{id}/publish`（article 自由发布）补全 | — | ⏳ Phase 5 待做 |
| Frontend | `story` 工作台「保存到番茄草稿」按钮 + `FanqiePublishPanel`（绑定/草稿保存/记录面板） | 新建 `pages/story/FanqiePublishPanel.tsx`；`pages/story/index.tsx` 正文区加按钮 + 挂载 | ✅ Phase 1 |
| Frontend | `api/index.ts` 加 `publishChapterToFanqie` / `getFanqieBinding` / `setFanqieBinding` / `getFanqiePublishStatus` / `getFanqieMyBooks` / `getFanqieBookStats` / `getFanqieHotList` | `frontend/src/api/index.ts` | ✅ Phase 1 + B + 4 |
| Frontend | `pages/my-data` 支持 fanqie：`FanqieDataPanel`（书籍网格 + 统计卡片 + 热榜 Tab） | 新建 `pages/my-data/FanqieDataPanel.tsx`；`pages/my-data/index.tsx` 加平台 `Segmented`（B站/番茄）+ 修复 early-return | ✅ Phase B |
| Frontend | 「灵感广场」页 `pages/inspiration`：热榜 → 转创作选题 | 新建 `pages/inspiration/index.tsx`；`App.tsx` 路由 `/inspiration` + `AppLayout` 侧边栏「灵感广场」 | ✅ Phase 4 |
| Agent | `fanqie_tools.py`：书架/统计/热榜、项目发布预检、发布记录、确认后草稿写入 | 注册到 `services/agent/tools/__init__.py`；创作导演内置白名单已接入 | ✅ Phase 5（真实写入联调待 Phase 6） |

> 与现有能力的对应：**发布闭环**复用 `CreativeProject` + `ProjectContent(novel_body)` 既有数据，零改造正文存储；**我的数据/热榜**平移 B站 my-data 模式（`PlatformConnection` + `services/platforms/` 子类 + `/api/v1/fanqie/*` + 前端页）。两者共用 `FanqieClient` 采集层。

## Non-goals

- **不**做「抓取番茄公共书源」：归入 `app/services/novel/` 的 `BOOK_SOURCES` 书源体系，是独立变更。
- **不**逆向 App 原生签名（`X-Argus`/`libmetasec_ml.so`）：作家后台无需。
- **不**整包 vendor 任何外部发布仓库，仅借鉴流程自研，兼顾可维护与合规。
- **不**做账号注册 / 笔名简介 / 作品创建表单（用户在番茄 Web 端完成，本变更只推正文 + 查数据）。
- **不**自动绕过登录二次校验 / 图形验证码：cookie 过期即报错并提示重抓。

## User flow

### 核心：创作项目 → 番茄发布
1. 用户在 YLCraft「创作项目」(`/story`) 写小说/短剧，生成 `novel_body` 章节正文。
2. 项目设置里绑定番茄：选 `PlatformConnection`（番茄 cookie）+ 粘贴 `book_id`/`volume_id`（番茄 Web 端建书/卷获得）。
3. 在工作台某章 `novel_body` 点「保存到番茄草稿」：选该章对应的番茄 `item_id`（番茄已建章节，或粘贴）→ `save_draft`。
4. 回执写 `ProjectPublishRecord`，前端展示草稿状态与远程版本，可重复保存更新。
5. 支持选中多章批量保存草稿。

### 辅助：我的数据 / 热榜
- **我的数据**：用户在平台管理绑定番茄 → YLCraft「我的数据」选番茄 → 拉取书籍 / 章节 / 收益卡片。
- **热榜**：YLCraft「灵感」入口 → 拉取热门故事列表辅助选题，可一键转成创作项目选题。

> 关键约束：番茄章节（`item_id`）需在番茄 Web 端先建好（或用 `get_book_chapters` 回填，E 组待抓）；本变更**不**在 YLCraft 内建书/建卷/建章节，只推正文 + 查数据。

## 安全与隐私（硬性约束）

- cookie 含完整登录会话，等同账号凭证。仅存 `PlatformConnection`，走既有加密字段；探针脚本不入库真实 cookie。
- 任何自动化测试**必须新建独立测试章节**（`title` 含 `[TEST]` 前缀 + 独立 `item_id`），绝不触碰线上章节（此前误覆盖过一次，已恢复）。
- cookie 过期检测：返回 `code!=0` 指向登录态失效或 HTTP 跳转登录页时，明确提示「请重新抓取登录态」，不静默重试。
