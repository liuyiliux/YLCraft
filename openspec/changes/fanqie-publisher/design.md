# Design: 番茄作家后台 API 客户端（FanqieAuthorClient）

## 对齐的现有模式（已核实）

B站「查看我的数据」在 YLCraft 的完整链路：

```text
前端 pages/my-data → api/index.ts (getBiliUpProfile)
  → GET /api/v1/bilibili/up/profile?uid=&conn_id=
    → main.py:408 挂载 bili_router
      → services/platforms/bilibili/routes.py:get_up_profile()
        → BilibiliClient(BasePlatformClient).get_user_profile(uid)   # client.py:1127
          → GET /x/web-interface/card   (apis.py 端点常量)
            → 映射 UserProfile 数据类
```

关键事实：
- **凭证统一**：数据来自 `PlatformConnection`（cookie + `account_id`），不另建存储。
- **采集层独立**：平台专属逻辑在 `services/platforms/bilibili/{apis,client,routes,utils}.py`，`client.py` 里 `@register_platform("bili")`。
- **基类可选方法**：`BasePlatformClient`（`services/platforms/base.py`）提供 `get_user_profile` 等可选方法（默认 `raise NotImplementedError`），B站实现它。
- **不落库**：B站每次实时拉取，无历史趋势表。

番茄直接平移这套结构即可。

## Architecture

番茄发布有两条来源，但**核心是创作项目闭环**——让 YLCraft「写小说/短剧」的成稿能一键推到番茄作家后台，把现有 `novel_body` 正文变成发布物。

```text
┌─────────────────────────────────────────────────────────────────┐
│  核心场景：创作项目闭环（/story 工作台 → 番茄发布）              │
│                                                                 │
│  CreativeProject (project_type=novel / short_drama)             │
│     └─ ProjectContent(content_type="novel_body",               │
│            chapter_number=N, text_content=正文)  ← 成稿         │
│           │  (标题 / 正文 / 章节号)                              │
│           │  ① 用户在项目设置里绑定番茄书 + 卷 (book_id/volume_id) │
│           │  ② 逐章选 item_id（番茄已建的章节）或章节映射        │
│           ▼                                                      │
│  POST /api/v1/creative-projects/{pid}/publish-to-fanqie         │
│     → FanqiePublishService.publish_chapter()                    │
│        → FanqieClient.save_draft() / publish()                 │
│           → cover_article/v0   (已验证 200/code:0)             │
│        → 写 ProjectPublishRecord (章节↔番茄 item_id/version 映射) │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  辅助场景 A：通用发布页（/publish，自由撰稿，非创作项目来源）    │
│  POST /api/v1/platforms/{conn_id}/publish (article 类型)        │
│     → FanqieClient.save_draft()（自由标题+正文，book_id 由表单选）│
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  辅助场景 B：我的数据 / 热榜（对标 B站 my-data）                 │
│  /api/v1/fanqie/*  →  FanqieClient.get_my_books()/get_book_stats()│
│                      get_hot_list()                              │
└─────────────────────────────────────────────────────────────────┘

                         ▼ 共用采集层 ▼

FanqieClient(BasePlatformClient)   ← app/services/platforms/fanqie/client.py 新增
        │  @register_platform("fanqie")
        ├─ 发布：save_draft() / publish()        [cover_article/v0 已验证]
        ├─ 我的数据：get_my_books() / get_book_stats()   [已验证 book_list + book_common_v1]
        └─ 热榜：get_hot_list()                   [douyin_hot_list/v0 已验证]
        │
        ├─ parse_cookie(PlatformConnection.cookie_content) → dict
        └─ httpx 携带 cookie 调 fanqienovel.com Web API
        ▼
番茄作家后台 Web API  (fanqienovel.com)
        │
PlatformConnection (cookie_content, AuthType.COOKIE, account_id=writer_id)  ← 现有，零改造
        │
可选快照  NovelBookStat / NovelEarning / ProjectPublishRecord
```

## Creative Project 集成（核心场景）

把 Fanqie 发布定位为**创作项目（`/story`）的发布出口**，而非孤立的客户端。现有数据模型已具备全部前置条件：

- `CreativeProject`：`project_type ∈ {novel, short_drama, ...}`，`settings_json` 可存发布绑定。
- `ProjectContent(content_type="novel_body", chapter_number, title, text_content)`：每章成稿就在这里，`text_content` 是纯文本正文 → 转 `<p>` 即番茄 `content` 字段。
- 阶段推进：大纲 → 章节规划 → 单话细纲 → **正文(novel_body)** → 脚本 → 分镜 → 漫画页。`novel_body` 是发布番茄最自然的产物。

### 绑定与映射（落库方案）

番茄要求 `book_id` + `volume_id` + `item_id`（章节）三段定位。YLCraft 侧映射：

| 番茄侧 | YLCraft 侧来源 | 获取方式 |
|---|---|---|
| `book_id` / `volume_id` | `CreativeProject.settings_json.fanqie.binding` | 项目设置里用户粘贴（番茄 Web 端建书/卷后获得） |
| `item_id`（章节） | `ProjectContent` 逐章绑定 或 番茄章节列表回填 | 用户粘贴，或 `get_book_chapters()` 回填（E 组待抓） |
| `title` | `ProjectContent.title` | 直接取 |
| `content` | `ProjectContent.text_content` → `<p>段落</p>` | `markdown_to_fanqie_html()` |

新增轻量映射/记录表（**不改造 PlatformConnection**）：

```python
class ProjectPublishBinding(SQLModel, table=True):
    """创作项目 → 番茄书/卷 的发布绑定（存 project settings 的简化版，也可独立表）"""
    __tablename__ = "project_publish_bindings"
    id: str = Field(primary_key=True)
    project_id: str
    conn_id: str                      # 关联的 PlatformConnection（番茄 cookie）
    platform: str = "fanqie"
    book_id: str = ""
    volume_id: str = ""
    volume_name: str = ""
    created_at: datetime

class ProjectPublishRecord(SQLModel, table=True):
    """每次发布/存草稿的回执，章节↔番茄 item_id/version 映射，避免重复覆盖"""
    __tablename__ = "project_publish_records"
    id: str = Field(primary_key=True)
    project_id: str
    content_id: str                  # 对应的 ProjectContent.id（novel_body）
    conn_id: str
    book_id: str
    item_id: str                     # 番茄章节 id
    chapter_number: int
    title: str
    action: str                      # "draft"（当前唯一支持动作）
    remote_version: int = 0          # cover_article 返回的 latest_version
    post_url: str = ""
    status: str = "success"
    error_message: str = ""
    published_at: datetime
```

> 绑定信息（book_id/volume_id/conn_id）也可直接塞进 `CreativeProject.settings_json.fanqie`，避免多表；独立 `ProjectPublishBinding` 表的好处是支持一个项目绑定多本书。两种都可行，实现时选其一（默认：先塞 settings_json，记录用 `ProjectPublishRecord`）。

### 发布服务 `FanqiePublishService`（新增）

```python
# app/services/platforms/fanqie/publish_service.py
class FanqiePublishService:
    def preview_chapter(self, project_id, content_id, item_id=None,
                        conn_id=None, book_id=None, volume_id=None,
                        volume_name=None) -> dict:
        """Resolve project binding and validate a novel_body locally.
        Validates only connection id/platform metadata; no cookie use or remote request.
        """
    def publish_chapter(self, project_id, chapter_number, conn_id,
                        book_id, volume_id, volume_name, item_id=None,
                        action="draft") -> dict:
        """读 ProjectContent(novel_body) → 转 HTML → FanqieClient.save_draft
        → 写 ProjectPublishRecord。item_id 为空时要求用户提供（番茄章节需先建）。"""
    def publish_chapters_bulk(self, project_id, chapter_numbers, ...) -> dict:
        """批量保存多章草稿，逐章回执，绝不静默重试。"""
    def get_publish_status(self, project_id, chapter_number) -> dict:
        """查 ProjectPublishRecord，前端展示「草稿/未保存 + 远程版本」"""
```

发布前置检查由 UI、Agent 和发布服务共用，不在各入口复制规则：

```text
FanqiePublishPanel / preview_fanqie_project_publish
    -> GET /creative-projects/{project_id}/fanqie/publish-preflight
    -> FanqiePublishService.preview_chapter()  # local-only
    -> publish only when ready=true and the user confirms the target
```

`set_binding()` and `publish_chapter()` repeat the connection and required-target validation. Preflight improves the UI, but is not the only enforcement boundary for API or Agent callers.

路由挂载（对齐 bili）：
```python
# backend/app/main.py
from app.services.platforms.fanqie.routes import router as fanqie_router
app.include_router(fanqie_router, prefix="/api/v1/fanqie", tags=["Crawler — Fanqie"])
```

## Verified endpoints (2026-08-01 实测 200 / code:0)

### A. 存草稿（发布）
```http
POST /api/author/article/cover_article/v0/?aid=2503&app_name=muye_novel&msToken=<reused>&a_bogus=<reused>
Content-Type: application/x-www-form-urlencoded;charset=UTF-8
x-secsdk-csrf-token: <会话级静态值>
origin/referer: https://fanqienovel.com/...
Cookie: <完整登录态 cookie>

body(form): aid, app_name, book_id, item_id, title, content=<p>正文</p>, volume_name, volume_id
→ 200 {"code":0,"message":"success","data":{"latest_version":N}}
```

### B. 热榜灵感（公域查看）
```http
GET /api/author/short_article/douyin_hot_list/v0/?aid=2503&app_name=muye_novel&type=0&msToken=<reused>&a_bogus=<reused>
Cookie: <完整登录态 cookie>
→ 200 {"code":0,"data":{"item_list":[21 条],"total_count":21}}
每条: book_name, author, category[], content(摘要), word_number, thumb_url, video_url, book_id
```

**已确认事实（4 个端点全部实测通过）**：均无 `X-Argus`/`X-Gorgon` 原生签名头；body/响应明文；`msToken`/`a_bogus` 不强制校验（复用抓包值成功）。纯 `httpx` + cookie 即可。

## 「我的数据」接口（2026-08-01 实测 200 / code:0）

> 来源：番茄作家后台 → 数据中心 → 小节数据页（`/main/writer/data`），referer 已确认。

### C. 我的书籍列表
```http
GET /api/author/stats/book_list/v0/?aid=2503&app_name=muye_novel&page_count=-1&page_index=0&image_fmt_list=160x214&msToken=<reused>&a_bogus=<reused>
Cookie: <完整登录态 cookie>
Referer: https://fanqienovel.com/main/writer/data
→ 200 {"code":0,"data":{"item_list":[...]}}
```
返回字段（每本书）：`book_id, book_name, book_status, book_status_desc, word_count, chapter_count, category, thumb_url/cover_url` + 更多。
⚠️ 未签约/未推荐的书可能不出现在列表里（实测返回 `item_list:[]`，需用 D 的按书查统计接口）。

### D. 单本书数据统计
```http
GET /api/author/stats/book_common_v1/v0/?aid=2503&app_name=muye_novel&book_id={book_id}&stats_type=1&msToken=<reused>&a_bogus=<reused>
Cookie: <完整登录态 cookie>
Referer: https://fanqienovel.com/main/writer/data
→ 200 {"code":0,"data":{
  "book_name": "逸流AI的新书",
  "is_publish": 0,
  "read_completion_rate": "0",
  "pursue_read_rate": "0",
  "reader_uv_daily": "0",
  "thumb_url_list": [{main_url, backup_url}],
  "main_intro": "作品还未开始推荐分发，数据不建议参考",
  "authorize_type": 0,
  ...
}}
```
对应截图里的 6 大指标：**阅读人数 / 在读人数 / 作品评分 / 加书人数 / 喜爱人数 / 追更人数**（未推荐时均为 0/"---"）。

### E. 待抓包（Phase 3 剩余，需登录态）

> **进度（2026-08-01）**：C/D 已在 `client.py` + `routes.py` 落地——书籍列表 `book_list/v0`、
> 单本统计 `book_common_v1/v0`，并已对齐**真实分页参数**（`page_count`/`page_index`，
> 非 `page`/`size`）与**统计 Tab**（`stats_type`，基础/质量/流量等数据中心子页）。
> 下列 E 组接口**必须登录态**才能抓；`agent-browser` 的独立 Chromium 无用户 cookie，
> 故走「用户在已登录浏览器抓 cURL → 贴回 → 回填」路径（用户此前已成功用过此方式）。

| 能力 | 预期位置 | 端点推测 | 状态 |
|---|---|---|---|
| 作家资料 | 作家后台头像/设置 | `user/info` 类 | ⏳ 待抓 → `get_my_profile` |
| 章节列表 | 作品管理→某本书 | `chapter_list` 类 | ⏳ 待抓（回填后可**自动映射 item_id**，替代手动粘贴） |
| 收益/分成 | 左侧「收益分析」 | `earning` 类 | ⏳ 待抓 → `get_earnings` |
| 质量分析 | 数据中心 Tab | 可能 `book_common_v1` 换 `stats_type` | ⏳ 待验证 |
| 流量构成 | 数据中心 Tab | 同上 | ⏳ 待验证 |

**抓包方法（用户在已登录浏览器执行）**：
1. 打开番茄作家后台对应页面（作品管理 / 收益分析 / 数据中心各 Tab）。
2. F12 → Network → 过滤关键词：`book_list` / `chapter` / `earning` / `user` / `stats`。
3. 找到返回 JSON（含 `code:0`）的请求，右键 → Copy → **Copy as cURL**（含 Cookie）。
4. 贴回对话；我据此回填 `apis.py` 端点常量 + `client.py` 方法 + `routes.py` 真实实现，
   并清理 cURL 中的明文 cookie（仅用于本地回填，绝不入库/外传）。

> 安全：章节列表回填后，`get_book_chapters` 可在发布面板里**自动列出番茄已建章节**，
> 你只需勾选对应 item_id，不必再手动抄。但建书/建卷/建章节仍须在 Web 端完成。

## FanqieClient 设计（对齐 BilibiliClient）

```python
# app/services/platforms/fanqie/client.py
@register_platform("fanqie")
class FanqieClient(BasePlatformClient):
    BASE = "https://fanqienovel.com"

    # —— 发布（已验证 cover_article）——
    def save_draft(self, book_id, item_id, title, content_html,
                   volume_name, volume_id) -> dict: ...
    def publish(self, ...) -> dict:            # 待验证 publish_article/v0

    # —— 我的数据（已验证 book_list + book_common_v1）——
    def get_my_books(self, page=0, page_size=-1) -> Dict:
        """GET /api/author/stats/book_list/v0/  → 书籍列表"""
        ...
    def get_book_stats(self, book_id: str, stats_type: int = 1) -> Dict:
        """GET /api/author/stats/book_common_v1/v0/  → 单本书统计"""
        ...

    # —— 待抓包 ——
    def get_book_chapters(self, book_id: str) -> Dict: ...   # 章节列表
    def get_earnings(self, period: str = "month") -> Dict: ... # 收益

    # —— 热榜（已验证）——
    def get_hot_list(self, type=0) -> Dict: ...               # douyin_hot_list/v0

    def _post(self, path, payload) -> dict:   # 统一 POST + 错误分类 + cookie 过期检测
        ...
    def _get(self, path, params) -> dict:     # 统一 GET
        ...
```

要点：
- `_post` / `_get` 统一处理：非 200、JSON 解析失败、`code != 0` 抛出带语义异常（`CookieExpiredError` / `ParamError` / `RiskControlError`）。
- cookie 过期判定：返回 `code` 非 0 且消息含「登录」/「登录态」，或 HTTP 302 跳转登录页 → `CookieExpiredError`。
- `content_html` 须为 `<p>...</p>` 片段；提供 `markdown_to_fanqie_html()` 简易转换（段落包 `<p>`）。

## Cookie 解析与凭证复用（零模型改造）

- `PlatformConnection.cookie_content` 是 **Netscape 格式**，解析为 dict 喂 `httpx`：
  新增 `parse_netscape_cookie(text) -> dict`（放 `app/services/novel/cookie_manager.py` 模块级，或 `services/platforms/fanqie/utils.py`）。
- `PlatformType` 枚举（/ `SUPPORTED_PLATFORMS`）增加 `FANQIE = "fanqie"`，标注 `VIEW=是 / PUBLISH=是 / 凭证=COOKIE`。
- `PlatformConnection` 模型**不改**；仿 bilibili 的 `extract_account_info_from_cookie`（`services/platform_connection/bilibili.py`）新增 `extract_writer_info`，在「测试连接」时调作家主页接口提取 `writer_id` 写回 `account_id` / `account_name`。

## 落库建议（番茄建议落库，B站没落）

B站每次实时拉、无趋势。番茄「收益 / 阅读」通常要做趋势图，建议在 `app/db/models/` 新增轻量快照：

```python
class NovelBookStat(SQLModel, table=True):
    __tablename__ = "novel_book_stats"
    id: str = Field(primary_key=True)
    connection_id: str          # 关联 PlatformConnection
    book_id: str
    title: str
    total_words: int = 0
    total_reads: int = 0
    total_votes: int = 0
    followers: int = 0
    snapshot_at: datetime

class NovelEarning(SQLModel, table=True):
    __tablename__ = "novel_earnings"
    id: str = Field(primary_key=True)
    connection_id: str
    book_id: str
    period: str                 # "2026-08"
    amount: float = 0.0
    currency: str = "CNY"
    settled: bool = False
    created_at: datetime
```

由后端定时任务（或前端「刷新」时）调 `FanqieClient.get_book_stats / get_earnings` 写入，前端卡片 + 趋势图读取。

## 前端（已落地，2026-08-02 更新）

> 原始设想是「`my-data` 扩展或独立 `novel-data` 页 + 一组 `getFanqie*` API」。实际落地有偏差，记录如下。

### API 层（`frontend/src/api/index.ts`）
已新增（均在 `writer-room` 段附近，复用 `listPlatformConnections`）：
- 发布闭环：`setFanqieBinding` / `getFanqieBinding` / `publishChapterToFanqie` / `getFanqiePublishStatus`（Phase 1）
- 我的数据：`getFanqieMyBooks(connId, page, size)` / `getFanqieBookStats(connId, bookId, statsType)`（Phase B）
- 热榜：`getFanqieHotList(connId, hotType=0)`（Phase 4）
- **未加**：`getFanqieMyProfile` / `getFanqieEarnings`（依赖 E 组抓包，任务 21/25 待做）。

### 「我的数据」接入（Phase B）—— 选方案：扩展现有 `my-data`
- **未**新建独立 `novel-data` 页，而是在 `pages/my-data/index.tsx` 加平台 `Segmented`（B站 / 番茄）：
  - 修复原 early-return（`biliConnections.length===0` 直接返回），改为「两类都无才提示去账号中心」；
  - 番茄分支渲染新建的 `pages/my-data/FanqieDataPanel.tsx`（自包含组件，自行加载番茄连接）。
- `FanqieDataPanel`：
  - **「我的书籍」Tab**：拉 `my/books` → 书籍网格（封面/书名/状态 Tag/字数/章节/分类），点选某书即加载该书统计；
  - **统计区 `Segmented` 切 `stats_type`**（基础数据 / 质量分析 / 流量构成）：后两者后端会真实发请求，若返回 `not_captured` 则提示，不假数据；统计字段对 `data` **扁平化展示**（已知字段走中文标签，未知回退原始 key，`main_intro` 以 Alert 提示，未推荐书数据多为 0）；
  - **「热榜灵感」Tab**：复用 `hot-list` 渲染热门故事卡片，引导去「灵感广场」转选题。
- 书籍列表若返回空（未签约/未推荐书不出现），前端提示可用「单本统计」按 book_id 查（番茄接口特性，`design.md` C 段已记）。

### 灵感广场（Phase 4）—— 新建 `pages/inspiration/index.tsx`
- 选番茄连接（过滤 `platform==='fanqie'`）→「加载热榜」→ 卡片网格（封面/标题/作者/分类/字数/摘要，字段防御性兼容）→ 每张卡「转为创作选题」→ Modal（可改标题 + 选 小说/短剧，idea 预览摘要只读）→ `createCreativeProject(source_type:'fanqie_hot', source_ref={book_id,书名,作者,分类,封面})` → `navigate('/story')`。
- 无番茄连接时友好引导去「账号中心」。
- 后端零改动：`POST /creative-projects` 原生支持 `source_type`/`source_ref`/`idea`，`service` 已落库。

### 创作工作台发布（Phase 1）—— `pages/story/FanqiePublishPanel.tsx`
- 正文区 `WorkbenchSection` 的 `extra` 改为 `<Space>` 包「生成正文」+「保存到番茄草稿」按钮（`disabled={!novelBody}`）；
- 面板 Modal：选 fanqie 连接 / 读存绑定 / 填 item_id / 先调用 `previewFanqiePublish` 本地检查 / 仅预检通过才保存草稿（调 `publishChapterToFanqie`）/ 展示 `ProjectPublishRecord` 列表（status/remote_version/error_message）+ 安全 Alert（建书建卷建章节在 Web 端完成）。表单改动会清除旧预检结论。

### 校验
上述所有前端文件均通过 `esbuild` 语法校验（`EXIT=0`）；路由 `/inspiration` 与侧边栏「灵感广场」已确认注册。

## Rollout plan

> 核心主线：**先打通「创作项目 → 番茄发布」闭环**（写小说/短剧成稿一键推番茄）；
> 辅助并行：**我的数据 + 热榜**（对标 B站 my-data）；自由发布页最后补。

1. **Phase 0（已验证接口落地）** ✅ 已完成（2026-08-01）：`FanqieClient` + cookie 解析 + 错误分类 + `save_draft`（离线单测过，`--live` 待用户真机）+ `get_hot_list`（已验证）。
2. **Phase 1（创作项目草稿闭环 — 核心）** ✅ 已完成（2026-08-01）：`FanqiePublishService` + 独立 `creative_fanqie.py` 路由 + `ProjectPublishRecord` 落库 + 绑定存 `settings_json.fanqie`；前端 `FanqiePublishPanel` + 「保存到番茄草稿」按钮。⏳ 真机联调待任务 7。
3. **Phase 2（平台管理接入，零模型改造）** ✅ 已完成（2026-08-01）：`PlatformType.FANQIE` + `extract_writer_info` + 凭证 helper + `main.py` 挂载 `/api/v1/fanqie`。
4. **Phase 3（我的数据）** 🟡 部分完成：C/D 接口（`book_list/v0` + `book_common_v1/v0`，已对齐真实分页/统计参数）真实落地；E 组（章节列表/收益/作家资料）⏳ 待用户登录态抓包（任务 21/23/25）；前端 `my-data` 接入已通过 Phase B 完成。
5. **Phase 4（热榜灵感）** ✅ 已完成（2026-08-01）：`get_hot_list` + 前端「灵感广场」页（`/inspiration`），可一键转创作选题。
6. **Phase 5（通用发布页 / Agent 集成）** ✅ 已完成（2026-08-08）：通用 article 草稿发布、共享项目发布预检、发布状态和 Fanqie Agent tools 已落地；真实写入仍受确认与 `[TEST]` 约束。
7. **Phase 6（验证与文档）** 🟡 代码与离线验证完成：预检单测、Agent 工具测试、前端构建和 API 清单已同步；仍待真实测试章集成联调（31/32）、E 组抓包（21/23/25）和定位记忆（34）。
8. 安全护栏全程有效：独立测试章 + 不静默重试 + cookie 过期即报错提示。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| cookie 过期（登录态 TTL） | `_post`/`_get` 检测并抛 `CookieExpiredError`，提示重抓；不静默重试 |
| 番茄改接口 / 加签名校验 | 接口集中于 `apis.py` + `_post`/`_get`，改动面小；监控返回 `code` 变化 |
| 误覆盖线上章节 | 测试章标题强制 `[TEST]` 前缀；发布默认草稿 / dry-run |
| 凭证泄露 | cookie 仅存 `PlatformConnection`，走既有加密；探针不入库 |
| 「我的数据」部分端点未知 | C/D 已验证（book_list + book_common_v1）；E（章节列表/收益）待抓，但核心「查看我的数据」能力已可落地 |
