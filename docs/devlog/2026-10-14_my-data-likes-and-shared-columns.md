# 2026-10-14 ~ 10-18 X「我的数据」：点赞 / 正在关注 / 作品 + 前端公共化重构

## 项目目标

起点是一句很具体的话：**"我的点赞 列表没有观看数吗"**、**"详情也不是完全一样 字段？"**。

最后收敛成三件事：

1. **X 的「我的数据」补齐** —— 点赞列表、正在关注作品流
2. **抽公共组件**（详情抽屉 + 列库），消灭"三处各写一份、每次差一点"
3. **修掉迁移过程中被我抹掉的平台个性**

## 已改文件

**后端 — 新增能力**

- `services/platforms/twitter/apis.py`
  - `LIKES_OP`：queryId `mu4us66Q6RRNOywVQhGtRg`（**从 JS bundle 实测抓取**，twscrape 里没有这个操作）
  - `HOME_LATEST_OP`：`HomeLatestTimeline`（**POST**！queryId `NmDBT3APtNxDpMqIEauu7A`，**bundle 里搜不到**，靠 browser-skill 抓真实网络请求）
  - `HOME_LATEST_FEATURES`：照真实请求抄的，**与 `GQL_FEATURES` 不一样，不许混用**
- `services/platforms/twitter/search_http.py`
  - `fetch_user_likes` / `fetch_home_latest`；抽出共用的 `_parse_user_timeline`
  - `_request_post_op()`：POST 专用（`queryId` 要放 **body** 里）
  - 评论作者改读**新版嵌套** `u.core.name/screen_name`（旧的扁平字段 X 已不给）
  - `author` 改为**昵称**（取不到退回 handle）；补 `bookmark_count` / `views`（顶层）/ `quote_count`
- `services/platforms/twitter/client.py`：`get_self_likes(_page)` / `get_home_latest`
- `api/v1/users.py`：`/users/likes`、`/users/home-feed`；`_media_of()` 统一组装媒体 + 详情字段；风控 → **503**（原 500）
- `api/v1/comments.py`：归一化白名单补 `author_handle`
- `services/platforms/douyin/client.py`：403 文案改如实（**稳定封禁**，非概率；重试无效、登录态正常）

**前端 — 新增公共层**

- `components/platform-detail/`：`PlatformDetailDrawer` + `PlatformMediaView` + `CommentPanel`
- `components/content-columns/index.tsx`：列库（每列一个工厂 + `rowsHave` 数据驱动）
- `pages/my-platform-data/`：`MyLikesPanel`（likes / home-feed 双模式）、`contentColumns` 已被列库取代
- `pages/crawler/index.tsx`：250 行手写列 → 列库；1237 行手写抽屉 → 公共组件

## 当前进度

**全部完成**，浏览器逐项实测确认：

- X 点赞列表（20 条/页、可翻页、带媒体）
- X「正在关注」作品流（`HomeLatestTimeline`，20~35 条）
- 详情：媒体预览 + 评论 + 子回复展开
- 列与详情在「我的数据」和「查询」页**同源**
- 「内容搜索」页移除 X 的「用户」tab

## 验证结果

- `test_my_likes_x.py` **92 条**（新增防退化测试）
- 相关套件 **612 条全过**；`tsc` exit=0；`vite build` 成功
- 浏览器实测：翻页 / 详情 / 评论 / 子回复 / 下载跳转 / 列显示 / 封面拖动

## 四个最贵的坑（都实际犯过）

1. **翻页只变页码不变内容** —— 游标压栈了但**没有任何 effect 去请求新游标**。
   「刷新」按钮是唯一触发点。⇒ 翻页必须有 `useEffect` 依赖 `currentCursor`。

2. **下载变成跳播放页** —— 把**流地址**（`proxy/video`）当下载链接，
   而它**没有 `Content-Disposition`**，浏览器按"导航到媒体"处理。
   ⇒ 想"下载"必须先拿 blob；**大文件别走 blob**（实测那条路也慢，见坑 4）。

3. **字段"最后一步被丢掉"（本轮出现 3 次）**
   - 详情少评论/时间：`_media_of()` 只拷了 `likes`
   - 评论作者全「匿名」：X 改了 schema，只读旧层级
   - `@handle` 消失：`comments.py` 的白名单没列它

   ⚠️ 一个字段从平台到界面要穿**三段**：采集端 → 归一化白名单 →
   响应模型（`response_model`）。**每段都可能静默丢，且都不报错。**

4. **为补字段逐条调详情** —— 差点又走一遍 YouTube 的坑。
   用户直接否决："这个不要 容易触发限流吧"。
   ⚠️ 而且"flat 下至少有 `release_timestamp`"是**我猜的，实测是错的**。

5. **抽象公共组件 ≠ 把个性抹平**（设计错误，用户纠正）

   我把个性**写死**进列库了，于是：封面固定 64×84（**拖列宽不变大**）、
   标题默认「内容」（原来是「标题」）。

   ⇒ 正确形态：**列库给默认值 + 调用方覆盖**
   （`coverColumn(ctx, { fluid: true })`、`titleLabel`）。

## 关键决策

- **列显示「看数据」不按类型猜** —— 实测 B站 `live`/`user` 的解析器
  **根本没有** `create_time`、公众号「账号」没有而「文章」有，
  **同平台内部就不一样** ⇒ `rowsHave(results, 'create_time')`。
- **queryId 抓不到时改抓真实网络请求** —— `Likes` 能从 bundle 搜到，
  `HomeLatestTimeline` **搜不到**（运行时才用），用 browser-skill
  `bsk debug requests` 抓一次就同时拿到 **queryId + POST 方式 + 完整 features**。
- **X 的「用户」tab 移除而非修复** —— 实测返回 0 条（`search()` 不消费
  `search_type`，只改 product）。但 B站/YouTube 的**能用**，**不能一刀切**。
  规则：**搜人只走「博主中心」**（内容页那个 tab 是重复入口）。
- **YouTube 不动**（见下）

## 已知限制：YouTube 没有发布时间（2026-10-17 记录）

用户问"我们不是抓包调用接口吗，是用别人的 yt-dlp 吗" —— **问到了根子上**：

| 平台 | 实现方式 |
|---|---|
| X / B站 / 微博 / 抖音 / 快手 / 小红书 / Telegram | **我们自己直调官方接口** |
| **YouTube** | **第三方库 `yt-dlp`**（直调要 PO Token，两次被挡：`2de0baa9`、`2e623366`） |

**后果**：yt-dlp 的 **flat 搜索不返回任何日期字段**
（实测 `upload_date` / `timestamp` / `release_timestamp` **全为 None**），
所以 YouTube 搜索结果**没有发布时间**。

已否决的修法（逐条拉详情）：**慢 12 倍**（5.3s→65.9s）**且 100% 报错**。

**当前表现正确**：列是数据驱动的 ⇒ YouTube **自动省略时间列**，
不是空列，界面不误导。**用户决定：先放着。**

⚠️ 记录下来是为了**别再有人试一遍**（尤其那个"flat 有 release_timestamp"的猜测）。

## 方法论（建议下一位 AI 先读）

> **"接口能返回数据" ≠ "我们拿得到"** —— 要逐段确认：
> 采集端产出 → 归一化白名单 → 响应模型 → 前端渲染。
> 每一段都可能**静默丢字段**，且**都不报错**。
>
> **"我测了几条没有" ≠ "平台没有"** —— 小样本会得出反向结论
> （我曾据此给三个列表加逐条请求；实测 54/54 全有，是白打）。
>
> **抽象公共组件 ≠ 把个性抹平** —— 公共层给**默认值**，
> 个性由调用方**覆盖**（`fluid` / `titleLabel` / `showDownload`）。
>
> **"显示为空"有两种** —— 平台不给（该隐藏）／拿到了没显示（bug）。
> 区分办法：**用 browser-skill 直接 fetch 接口看返回的键**。
> 页面没变化时先这么查，能立刻分清是前端缓存还是后端没重载。
>
> **用户连续三次的纠正指向同一件事**：列与详情应该**同源**。
> 重复实现必然漂移，而漂移是**静默**的。

## 待办 / 下一步

- **YouTube 改成直调官方接口**（B 方案）—— 唯一能拿到发布时间的路，
  独立量级重构，风险是当初被风控挡过。用户决定先放着。
- **查询页的详情抽屉**已换公共组件，但 B站 的弹幕/字幕/数据仍是它自己的
  专属分支（用户明确"B站是单独一套"），**不要合并**。
