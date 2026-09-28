# 各平台能力矩阵（实测）

> 最后更新：2026-09-28
> 测法：`backend/_check_platform_matrix.py`（经真实 HTTP 路由打，非单元测试）
> **拿不到记"不支持/失败"，不编造。**

## 矩阵

| 平台 | 内容搜索 | 分页 | UP主/用户搜索 | 我的数据 | 作品列表 |
|------|---------|------|--------------|---------|---------|
| **B站** | ✅ 5 条（total=1000） | ✅ 20 条 OK | ✅ 5 个 | ✅ **6 个 Tab**（见下） | ✅ |
| **抖音** | ✅ 5 条 | ⚠️ **只 18 条**（抖音已停支持 offset 翻页） | ✅ 4 个 | ✅ OK | ✅ OK |
| **小红书** | ❌ 0 条（**cookie 过期**） | ❌ | ❌ code=-104（cookie 过期） | ✅ OK | ✅ OK |
| **微博** | ✅ 5 条 | ⚠️ **只 9 条**（无真翻页，靠 since_id） | ❌ 未实现 | ❌ 未实现 | ❌ 未实现 |
| **X** | ✅ 5 条 | ✅ 20 条 OK | ❌ 未实现 | ❌ 未实现 | ❌ 未实现 |

> ⚠️ **勘误（2026-09-28）**：本表初版把 B站「我的数据」标成"未实现"，
> **那是错的**。原因：我的检查脚本只测了 `/api/v1/users/me`
> （那是给抖音/小红书新写的接口），**没测 B站已有的 `/api/v1/bilibili/*`**。
> 用户指出后重测 —— B站的数据能力其实是**全平台最强的**，见下节。

## 逐项说明

### 分页

| 平台 | 机制 | 状态 |
|------|------|------|
| B站 | `page` 参数（服务端真分页） | ✅ 两页返回不同数据 |
| X | cursor（**没有 page 参数**） | ✅ 已实现"page=N 先翻过 N-1 页" |
| 抖音 | offset/count | ⚠️ **offset>0 全部返回 0 条**（详见下） |
| 微博 | `page` 参数 | ⚠️ `page=2` 返回 173 字节 HTML 错误页；真翻页靠 `since_id` 游标 |
| 小红书 | — | 未测（cookie 过期） |

#### 抖音 offset 翻页已失效（2026-09-28 复测）

代码注释里"offset=0/20/40 有效"是 2026-09-27 的结论，**现在不成立**：

    offset=0   count=20  -> 18 条  cursor=20  has_more=True   ✅
    offset=20  count=20  ->  0 条  cursor=40  has_more=False  ❌
    offset=5   count=5   ->  0 条  cursor=10  has_more=False  ❌

**在真实浏览器里跑同样的请求，offset=20 也是 0 条** ——
所以这是抖音的**服务端行为变化**，不是我们的代码问题，
也不是"自动化被限制"（真实浏览器也一样）。

**结论：抖音目前只能拿首页（约 18 条）。**
代码保留 offset 递增逻辑，若抖音恢复该能力则无需改动即可生效。

### UP主 / 用户搜索

| 平台 | 接口 | 状态 |
|------|------|------|
| B站 | `/crawler/search-enhanced` + `search_type=user` | ✅ |
| 抖音 | `/api/v1/users/search?platform=douyin` | ✅ |
| 小红书 | `/api/v1/users/search?platform=xiaohongshu` | ⚠️ 需有效 cookie |
| 微博 | — | ❌ 未实现（微博确实有用户搜索接口，未做） |
| X | — | ❌ 未实现 |

### 作品详情 / 我的数据

| 平台 | 状态 |
|------|------|
| 抖音 | ✅ `/users/me` + `/users/videos` |
| 小红书 | ✅ 同上（但需有效 cookie） |
| B站 | ❌ 我的数据未实现（B站有其他入口页） |
| 微博 | ❌ 未实现 |
| X | ❌ 未实现 |

## 已知的"连接标识不一致"（踩坑点）

连接表里的 `platform` 值与本项目其它地方**不一致**（历史原因）：

| 连接表 | 搜索接口认 | users 接口认 |
|--------|-----------|-------------|
| `bilibili` | `bili` | — |
| `xhs` | `xhs` | `xiaohongshu` |
| `twitter` | `twitter` | — |

**取 conn_id 时必须按连接表的值查，传给接口时用接口认的值。**
用错会得到 `conn_id=None` → HTTP 422（实测踩过）。

---

## B站「我的数据」—— 全平台最强（2026-09-28 实测）

入口：菜单「采集与下载 → 我的数据」（`/my-data`），**不是** `/my-platform-data`。

### 6 个 Tab

    概览 / 视频 / 收藏夹 / 历史 / 关注 / 付费课程

### 实测结果（带 conn_id 打真实接口）

| 接口 | 结果 |
|------|------|
| `/bilibili/history` | ✅ 20 条 |
| `/bilibili/favorites` | ✅ 20 条 |
| `/bilibili/followings` | ✅ 20 条 |
| `/bilibili/paid-courses` | ✅ 1 条 |

> ⚠️ `/bilibili/stats` **不是账号统计**，是**单个视频的统计**
> （需要 `bvid` 或 `aid`，不给就 400）。初版矩阵把它误当成"账号统计"了。

### B站独有的能力（其它平台都没有）

    /bilibili/danmaku              弹幕
    /bilibili/subtitles            字幕（+ /subtitle/download 下载）
    /bilibili/comments             评论（+ /comment/send 发评论）
    /bilibili/paid-courses         付费课程（+ 详情/播放地址/下载任务）
    /bilibili/history/search       历史搜索
    /bilibili/up/ranking           UP主排行
    /bilibili/series/{id}          合集
    /bilibili/video/info           视频详情

**B站 25 个端点**，远超其它平台（抖音 3 个、微博/推特各 0 个专用端点）。

### 支持的平台

`/my-data` 页同时支持 **B站** 和 **番茄小说** 两个平台切换。
