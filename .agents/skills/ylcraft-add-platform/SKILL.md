---
name: ylcraft-add-platform
description: Add, extend, or audit a content platform (search / detail / user / my-data / download) in YLCraft. Use when the user asks to add a new platform (Kuaishou, Zhihu, TikTok, YouTube…), fix a platform whose feature "seems implemented but does not work", or make a platform consistent across backend, frontend, cookies, download, and asset layers.
---

# YLCraft 新增平台

## 这个 skill 解决什么问题

一个平台名在代码里平均出现 **56 处**（实测 `douyin`），横跨
**采集 / 登录态 / 下载 / 素材 / 路由 / 前端 / Agent** 七个面。

真正的难点不是"写个爬虫"，而是：

> **登记齐全 ≠ 功能接通。** 漏掉某一层时，症状往往**不是报错**，
> 而是"某个功能悄无声息地不对"。

本 skill 把七层的接触点、每层的**漏了会怎样**、以及**自动化校验**固化下来。

---

## 铁律（违反必踩坑）

1. **不要猜接口。** 路径 / 参数 / queryId / 字段名都要有实测或源码出处。
   查不到就说"未找到"，**绝不编造**。
2. **不支持的平台名/接口要显式抛错**，不要静默返回空列表 ——
   空会被上层理解成"没搜到"，属假阴性，排查最费时间。
3. **改完必须跑全量校验**，不是只查自己改的那个平台。
4. **后端起效 ≠ 前端接通。** 每次都要看前端有没有入口。
5. **实测矩阵要全平台跑**，别只测新加的那个（这条被用户提醒过两次）。

---

## 工作流

### 第 0 步：确认能力边界

先问清楚（问用户或看需求）：**支持哪几个能力？**

| 能力 | 方法名 | 没有会怎样 |
|------|--------|-----------|
| 搜索 | `search(params)` | 核心缺失 |
| 分页 | 搜索要带 `_has_more` | ⚠️ 前端**没有「下一页」** |
| 详情 | `get_detail(id)` | 详情空 |
| 搜博主 | `search_users(kw)` | 博主中心查不到 |
| 用户资料 | `get_user_profile(id)` | 同上 |
| 作品列表 | `get_user_videos(id)` | ⚠️ `/users/videos` **500** |
| 我的数据 | `get_self_profile()` | ⚠️ 误报"登录态失效" |

### 第 1 步：抓包（**不做这步后面全是返工**）

记录到 docstring（**含日期**）：URL、必需 header、必需参数、
响应路径、翻页方式、类型字段。

参考已有实现：
- 纯 HTTP + 签名 → `platforms/xiaohongshu/`（`xhshow`）
- 纯 HTTP + 动态头 → `platforms/twitter/`（`x-client-transaction-id`）
- 浏览器（Service Worker） → `platforms/weibo/`（**无头**运行）

### 第 2 步：写客户端 + 注册

```
app/services/platforms/<平台>/
    __init__.py      # 导出
    client.py        # @register_platform("名字") + @register_platform("别名")
    apis.py          # 接口常量 + 参数构造
    health.py        # 登录态检测（建议）
```

**⚠️ 还要加进自动发现列表**：
`app/services/platforms/__init__.py::_auto_discover_platforms()` 的
`platform_modules` —— **漏了客户端不会加载**。

### 第 3 步：登录态（四张表）

`app/services/cookies/base.py`：

| 表 | 漏了会怎样 |
|----|-----------|
| `PLATFORM_LOGIN_URLS` | 开不出登录页（**指创作者后台而非读者站**） |
| `PLATFORM_DOMAINS` | ⚠️ **抓不全 cookie → "有值但不生效"** |
| `PLATFORM_TEST_URLS` | "检查"按钮失效 |
| `PLATFORM_USER_AGENTS` | 用默认 UA（可能被风控） |

加 `app/services/cookies/platforms/<平台>.py`：平台特有的登录判断
（如小红书识别「扫码登录」「电脑设备登录超限」），并注册进
`cookies/platforms/__init__.py::_detector_registry`。

> ⚠️ **`PLATFORM_DOMAINS` 是最容易漏且最难查的。**
> 实测微博：只写 `.weibo.com` 会漏 `.weibo.cn`（m 站），
> 而搜索/详情全走 m 站 → "cookie 有值但 `/api/config` 返回 `login=False`"。
> **把主站 / m 站 / passport / CDN 全列上。**

### 第 4 步：内容层（**最不报错，最容易翻车**）

| 要点 | 正确做法 |
|------|---------|
| **类型判断** | 用平台**权威字段**，不要猜：抖音 `aweme_type`(0/68)、小红书 `note_card.type` |
| **`video_url` / `images`** | **宁可留空也不要兜底** —— 兜底会让下游"有没有值"判断全部失真 |
| **图集图片** | 放进 `raw_data._images`（`SearchResult` 没有 images 字段） |
| **视频直链** | 放进 `raw_data._video_url` |
| **`has_more`** | 放进 `raw_data._has_more`（**如实**，没有就 False） |

### 第 5 步：下载 / 防盗链

`app/services/download/platforms/<平台>.py` + `app/services/video/parser*.py`

> ⚠️ **防盗链每个平台方向可能相反**：
>
> | 平台 | 图片 | 视频 |
> |------|------|------|
> | X | **不能带** Referer | **不能带** |
> | 抖音 | 必须带**对的** | 必须带对的 |
> | 微博 | 必须带 weibo 的 | 无所谓 |
> | 小红书 | 无所谓 | 无所谓 |
>
> 统一走 `app/api/v1/proxy.py::_guess_referer` + `_NO_REFERER_HOSTS`
> （**按域名**）。**不要**按 `platform` 字符串写死一张表 ——
> 实测漏平台后兜底成抖音，微博图片**全 403**。

### 第 6 步：路由 / 素材

| 位置 | 要点 |
|------|------|
| `app/api/v1/platforms.py::SUPPORTED_PLATFORMS` | 平台整体可用 |
| `app/api/v1/users.py::SUPPORTED` | 用户查询 + **`cookie_domain`** |
| `app/services/crawler/service.py::BROWSER_ONLY` | 哪些必须走浏览器（**慎重**，优先试无头） |
| 建素材节点 | ⚠️ **必须带 `owner_user_id`** |

> ⚠️ **`cookie_domain` 要用 `netscape_to_header` 认识的名字**：
> `"xhs"` → 0 字符，`"xiaohongshu"` → 998 字符；
> `"twitter"` → 0 字符，`"x.com"` → 1339 字符（**X 的域是 `.x.com`**）。
> 这个坑**犯过两次**。

> ⚠️ **`owner_user_id` 漏了 → 素材库列表看不到**（列表按 owner 过滤）。
> 记录其实在库里，只是 `owner=None`。**后台任务**（`DownloadTask`）也要带。

### 第 7 步：前端（**至少两处下拉**）

| 位置 | 漏了会怎样 |
|------|-----------|
| `pages/accounts/index.tsx::PLATFORM_METAS` | 账号中心看不到入口 |
| `pages/crawler/index.tsx` | 搜索页选不到 |
| `pages/my-platform-data/index.tsx` | ⚠️ 「我的数据」**选不到**（X 就这样漏过） |
| `pages/platform-users/index.tsx` | 博主中心选不到 |
| `pages/assets/index.tsx` | 素材库筛不到 |

> ⚠️ **创作者中心只有抖音/小红书**。前端要**显式守卫**，
> 不能用 `else` 兜底 —— 实测 `if (isXhs) {...} else {...抖音...}`
> 导致选微博时显示**抖音的数据**。

### 第 8 步：跑校验 + 实测矩阵

```bash
cd backend
python scripts/check_platform_registry.py --allow-known   # 必须全绿
```

再跑**全平台**实测矩阵（不是只测新的那个）：

| 检查项 | 判定 |
|--------|------|
| 搜索 | 有条数 |
| 分页 `page=1/2/3` | **首条不同** + `has_more` 合理 |
| 详情 | 正文/图片/视频有值 |
| 我的数据 `/users/me` | 拿到昵称 |
| 搜博主 `/users/search` | 有条数 |
| 作品列表 `/users/videos` | 不报 500 |
| **图集/视频类型** | 找一条图集 + 一条视频，**类型判对** |
| **视频可播** | 走 `/proxy/video` → 200/206 |
| **图集可下载** | `/api/v1/download/download-images`，成功数 == 张数 |
| **素材库可见** | `/api/v1/asset-hub/nodes` 里能看到刚下载的 |

---

## 常见症状 → 根因速查

| 症状 | 根因 |
|------|------|
| cookie 有值但"未登录" | `netscape_to_header` 域名别名不对 |
| 搜索"未登录"但 cookie 有效 | 站点有**两套登录体系**（微博 m 站 vs 主站） |
| 图集被判成视频 | `video_url` 拿"原文链接"兜底 |
| 图集一张图都没有 | 读错字段（抖音图集在 `images`，不是 `image_infos`） |
| 前端没有"下一页" | 后端没设 `has_more` |
| 详情播不了视频 | 浏览器带 Referer，CDN 拒绝 → 走 `/proxy/video` |
| 下载的素材在库里找不到 | 没写 `owner_user_id` |
| 下拉里选不到某平台 | 前端漏加（**后端起效 ≠ 前端接通**） |
| 每次搜索弹浏览器 | 在 `BROWSER_ONLY` 且**有头** → 先试**无头** |
| `'XxxClient' has no attribute` | 没实现 `get_user_videos` 等，要显式抛错 |
| 端口 `WinError 87` | 两个 uvicorn 抢 8000 |
| 启动失败 `No route to host` | 数据库**在远程**，网络抖动 → 重试，别改代码 |

---

## 必须一起改的文档

- `docs/platform/ADDING_A_PLATFORM.md` —— 登记表 + 踩坑（**主文档**）
- `docs/platform/COLLECTION_ARCHITECTURE.md` —— 采集架构与能力矩阵
- `docs/architecture/API_SURFACE.md` + `api_surface.json` —— 改了 API 面就要同步
- `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` —— 语义/模块影响

---

## 相关代码位置速查

```
backend/app/services/platforms/__init__.py      ← 自动发现列表 + 共享缓存
backend/app/services/platforms/base.py          ← @register_platform / BRWOSER 会话
backend/app/services/platforms/<平台>/           ← 客户端
backend/app/services/cookies/base.py            ← 四张表
backend/app/services/cookies/platforms/__init__.py  ← _detector_registry
backend/app/services/crawler/service.py         ← BROWSER_ONLY / cookie 解析 / 素材类型
backend/app/api/v1/users.py                     ← SUPPORTED（用户维度）
backend/app/api/v1/platforms.py                 ← SUPPORTED_PLATFORMS
backend/app/api/v1/download.py                  ← 解析/下载/素材归属/图集下载
backend/app/api/v1/proxy.py                     ← 图片/视频代理（Referer 策略）
backend/app/api/v1/asset_hub.py                 ← 素材列表（**按 owner 过滤**）
backend/scripts/check_platform_registry.py      ← 自动化校验
frontend/src/pages/{accounts,crawler,my-platform-data,platform-users,assets}/
```
