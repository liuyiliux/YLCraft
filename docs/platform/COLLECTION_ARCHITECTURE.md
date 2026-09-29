# 多平台采集：搜索 / 详情 / 下载 功能架构

> 最后更新：2026-09-29
> 覆盖平台：B站、抖音、小红书、微博、X（原 Twitter）、番茄

本文说明「采集与下载」相关功能的**实际代码结构**，以及每个平台
在各能力上**走哪条路径、为什么**。

---

## 一、总览：三层结构

```
┌─────────────────────────────────────────────────────────────┐
│  前端页面                                                     │
│  ┌──────────────┬──────────────┬──────────────┬────────────┐ │
│  │ /crawler     │ /download    │ /platform-   │ /my-data   │ │
│  │ 内容搜索      │ 去水印下载    │  users       │ /my-       │ │
│  │ +详情抽屉     │ +磁力/种子    │ 博主中心      │ platform-  │ │
│  │              │              │              │ data 我的数据│ │
│  └──────────────┴──────────────┴──────────────┴────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            ↓ HTTP
┌─────────────────────────────────────────────────────────────┐
│  API 层  app/api/v1/                                          │
│  ┌──────────────┬──────────────┬──────────────┬────────────┐ │
│  │ crawler.py   │ download.py  │ users.py     │ bilibili.py│ │
│  │ 搜索/详情/导入 │ 解析/下载/任务│ 用户维度      │ B站专有    │ │
│  └──────────────┴──────────────┴──────────────┴────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  服务层                                                       │
│  ┌────────────────────────┬────────────────────────────────┐ │
│  │ CrawlerService          │ VideoParser / DownloadManager │ │
│  │ （搜索/详情的统一入口）   │ （视频解析 / 文件下载）          │ │
│  └────────────────────────┴────────────────────────────────┘ │
│                            ↓                                  │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  platforms/  平台客户端层（统一接口）                       ││
│  │  ├── bilibili/   ├── douyin/    ├── xiaohongshu/          ││
│  │  ├── weibo/      ├── twitter/   └── fanqie/               ││
│  └──────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  传输层（三种，按平台选）                                       │
│  ┌────────────┬──────────────┬─────────────────────────────┐ │
│  │ httpx      │ Patchright   │ yt-dlp                      │ │
│  │ 纯 HTTP    │ 真实浏览器    │ 通用下载器                    │ │
│  │ + 签名      │ + 登录态      │                             │ │
│  └────────────┴──────────────┴─────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、平台客户端统一接口

所有平台都实现 `BasePlatformClient` 的这套方法
（`backend/app/services/platforms/base.py`）：

| 方法 | 用途 | 谁实现了 |
|------|------|---------|
| `search(params)` | 搜索内容 | **全部 6 个平台** |
| `get_detail(item_id)` | 取详情 | **全部 6 个平台** |
| `search_users(keyword)` | 搜博主 | B站/抖音/小红书/微博/X（**番茄无**） |
| `get_user_profile(id)` | 博主资料 | **全部 6 个平台** |
| `get_self_profile()` | 我自己的资料 | 抖音/小红书/微博/X（**B站/番茄无**） |
| `get_user_videos(id)` | 某博主的作品 | B站/抖音/小红书（**微博/X/番茄无**） |

> **B站「我的数据」是另一条路**：它走 `/bilibili/*` 专有路由
> （收藏夹/历史/关注/付费课程，6 个页签），能力比其它平台强得多。

---

## 三、搜索：各平台走哪条路

```
前端 /crawler
    ↓ POST /api/v1/crawler/search-enhanced
CrawlerService._search_via_platforms()
    ↓
    ├── BROWSER_ONLY = ("weibo", "wb")   ← 只有微博
    │       ↓ mode="patchright"
    │   微博：必须浏览器（见下「为什么微博特殊」）
    │
    └── 其余平台 mode="api"
            ↓ create_client(platform, mode, cookie=cookie)
        ┌──────────────────────────────────────────────┐
        │ B站     官方 API（无需 Cookie）                 │
        │ 抖音    HTTP + 自己的签名                       │
        │ 小红书  **纯 HTTP + xhshow 签名** ← 2026-09 打通│
        │ X      **纯 HTTP + x-client-transaction-id**   │
        │ 番茄    官方 API                                │
        └──────────────────────────────────────────────┘
```

### 关键：`cookie` 必须显式传

`_search_via_platforms` 通过 `_resolve_cookie_for(conn_id, platform)`
取 cookie。**api 模式不传 cookie 会静默失败**（报"需要登录 Cookie"）。

⚠️ 踩过的三个坑：
1. 用 `PlatformConnectionService().get_raw_cookie()` → **返回 None**
   （它自己的 session 在请求上下文查不到库）
   → 已改用 `resolve_connection` + `netscape_to_header`
2. `netscape_to_header(raw, "xhs")` → **0 字符**，必须传 **`xiaohongshu`**
   → 已做平台名归一
3. **同一个坑犯了两次**：加映射表时漏了 `twitter` 本身
   （`netscape_to_header(raw, "twitter")` → 0 字符，必须传 **`x.com`**）。
   → 已改成**逐个候选试**，而不是只查一次映射表

### ⚠️ 搜索结果缓存（2026-09-29 加）

缓存在**共享入口** `platforms.search()` 上，所有平台受益：

| 平台 | 首次 | 缓存命中 |
|------|------|---------|
| 小红书 | 1.7s | **0.4s** |
| 抖音 | 2.6s | **0.4s** |
| B站 | 1.2s | **0.4s** |

  · **只缓存非空结果** —— 空可能来自限流（抖音实测），
    缓存它会让"稍后重试"也拿不到数据
  · **key 含 `conn_id` + `sort_by`** —— 不同账号/排序不能串
  · TTL 5 分钟、容量上限 500 条

**教训**：小红书的缓存原来只加在部分路径上，**压根没生效**
（实测三次搜索耗时都是 16 秒）。缓存放共享入口才能真正惠及所有路径。

---

## 四、详情：两条完全不同的路

```
前端点「详情」
    ↓ GET /api/v1/crawler/note-detail?platform=&note_id=&conn_id=&xsec_token=
    ↓ （或 POST /api/v1/download/parse → 走 VideoParser）
```

### 路径 A：直接调平台详情接口

| 平台 | 端点 | 传输 | 必需 |
|------|------|------|------|
| **小红书** | `POST edith…/api/sns/web/v1/feed` | httpx | **`xsec_token`**（缺→461）+ xhshow 签名 |
| **X** | `UserByScreenName` GraphQL | httpx | `auth_token`+`ct0`+`x-client-transaction-id` |
| **微博** | `containerid=100505{uid}` | Patchright | 登录态 |
| **B站** | 官方 API | httpx | 无 |
| **抖音** | 搜索结果里已含全部字段 | — | 前端直接用结果渲染 |

### 路径 B：去水印解析（下载页）

```
/download 粘贴链接
    ↓ POST /api/v1/download/parse
VideoParser.parse(url)
    ├── B站      → parser_bilibili（官方 API，无需 Cookie）
    ├── 抖音     → parser_douyin（iesdouyin 分享页，绕过 msToken）
    ├── 小红书   → platforms/xiaohongshu/detail_adapter（**纯 HTTP API**）
    ├── X        → syndication API 兜底
    └── 其它     → yt-dlp 兜底
```

---

## 五、小红书：完整链路（最复杂，但已全部纯 HTTP）

```
        搜索                     详情                    创作中心
         │                       │                        │
    ┌────▼─────┐          ┌──────▼──────┐         ┌───────▼────────┐
    │search_api│          │  note.py    │         │  creator.py    │
    │ /search/ │          │  /feed      │         │/galaxy/v2/...  │
    │  notes   │          │             │         │/galaxy/...     │
    └────┬─────┘          └──────┬──────┘         └───────┬────────┘
         │                       │                        │
         └───────────┬───────────┴────────────────────────┘
                     ▼
              signing.py（xhshow）
              ├── sign_get()  → X-s / X-t / X-s-common
              └── sign_post(..., x_rap=True) → + x-rap-param
                     │
                     ▼
              edith.xiaohongshu.com / creator.xiaohongshu.com
```

### 三个必须记住的实测结论

| 结论 | 说明 |
|------|------|
| **`page_size` 只认 20** | 其它值一律返回空 `items`（但 HTTP 200 + `success:true`） |
| **必须带 `image_formats`** | 否则 `cover` 只有宽高、**没有 URL**（列表封面全空） |
| **`xsec_token` 必需** | 搜索返回里自带，直接喂给详情；缺失返回 **HTTP 461** |

### 登录态

**与主站通用**（cookie domain 是 `.xiaohongshu.com`）。
⚠️ 但**过期的 `web_session` 依然存在** —— "有 cookie" ≠ "已登录"。
实测失效时主站正文会写「**电脑设备登录超限，请重新登录**」。

---

## 六、下载：三条独立路径

```
┌───────────────────────────────────────────────────────────────┐
│ ① 视频下载    POST /api/v1/download/download                   │
│    走 yt-dlp → backend/downloads/{platform}/{title}/           │
│    ✅ 不需要浏览器                                              │
├───────────────────────────────────────────────────────────────┤
│ ② 图片下载    POST /api/v1/download/download-images            │
│    走 httpx 直连 → 同上目录                                     │
│    ✅ 不需要浏览器                                              │
├───────────────────────────────────────────────────────────────┤
│ ③ 导入素材库  POST /api/v1/crawler/import                       │
│    写数据库（**只存 URL，不落盘**）                              │
│    ⚠️ 与「下载」是两件事 —— 下载不会自动入库                      │
└───────────────────────────────────────────────────────────────┘
```

### 平台专用下载器

```
DownloadManager
    ├── platforms/bilibili.py（含**付费课程**下载）
    ├── platforms/douyin.py
    ├── platforms/twitter.py
    └── 兜底：yt-dlp
```

---

## 七、传输层选择（为什么每个平台不一样）

| 平台 | 传输 | 原因 |
|------|------|------|
| **B站** | httpx | 官方 API 开放，无需 Cookie |
| **抖音** | httpx | 自己的签名算法 |
| **小红书** | **httpx + xhshow** | 缺签名会被风控拒（300011）；**加签名即可纯 HTTP** |
| **X** | **httpx** | 需要 `x-client-transaction-id`（动态生成）；失败才回退 DOM |
| **微博** | **Patchright** | ⚠️ **必须浏览器** —— 微博注册了 **Service Worker**，由它代理请求并注入 httpx 复现不了的上下文（实测 httpx 直连一律 `ok=-100`，与签名无关） |
| **番茄** | httpx | 官方 API |

### 各平台传输层实现文件

```
xiaohongshu/  signing.py（签名）  search_api.py（搜索）  note.py（详情）
              search_patchright.py（浏览器兜底）  creator.py（创作中心）
twitter/      xclid.py（transaction-id）  search_http.py（HTTP 优先）
              search_dom.py（DOM 兜底）
weibo/        search_patchright.py（唯一路径）
```

---

## 八、创作者中心（只有号主能看的数据）

| 平台 | 端点 | 签名 | 实测 |
|------|------|------|------|
| **抖音** | `creator.douyin.com/aweme/janus/creator/data/overview/all/` | ❌ **不需要** | 播放/主页访问/净增粉丝… |
| **小红书** | `creator.xiaohongshu.com/api/galaxy/v2/creator/datacenter/account/base` | ✅ xhshow GET 签名 | 曝光759/观看157/完播率3.4%… |

**与公开数据的区别**：

```
公开接口（/users/me）  → 粉丝数、获赞数（谁都看得到）
创作者中心             → 播放量、曝光、完播率、主页访客、取关…
                        （**只有号主可见**）
```

⚠️ 抖音创作者中心**所有数值都是字符串**（`"8"` 不是 `8`），
只认 int/float 会把它们全过滤成 0。

---

## 九、踩坑清单（改代码前必读）

### 数据正确性

| 坑 | 表现 | 正确做法 |
|----|------|---------|
| 把"没登录"当成"没结果" | 所有关键词都 0 条 | 先查凭证，再查参数 |
| 把"本页条数"当"总数" | 显示"共 20 条"但翻页还有 | 用 `has_more`，不编造 total |
| 抓页面链接当"自己" | 「我的数据」返回别人的资料 | 先验证登录态 |
| 用原图当缩略图 | 图"有成功有失败"（其实在慢加载） | 加 `imageView2` 参数 |

### 前端

| 坑 | 表现 | 正确做法 |
|----|------|---------|
| 展开错响应层级 | 字段全 undefined | `resp.data` 才是数据 |
| `btoa` 处理中文 | **整页崩**（InvalidCharacterError） | 用 `encodeURIComponent` |
| 分页 total 只加一次 | 只能翻到第 2 页 | 随 `currentPage` 累计 |

### 后端

| 坑 | 表现 | 正确做法 |
|----|------|---------|
| 函数漏 `return` | 日志说读到了、上层说没有 | 检查返回值 |
| 静默返回空 | 用户只看到"没搜到" | 抛**可操作**错误 |
| cookie 取不到 | 全线报"需要登录" | `resolve_connection` + 别名归一 |

---

## 十、相关文档

- `docs/platform/capability_matrix.md` —— 各平台能力矩阵（含实测数字）
- `docs/platform/ADDING_A_PLATFORM.md` —— 新增平台指南
- `docs/research/weibo_twitter_api.md` —— 微博/X 接口调研
- `docs/architecture/API_SURFACE.md` —— 完整 API 清单
