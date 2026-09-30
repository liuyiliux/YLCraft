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

## ⚠️ 登录态「时效」：先查清**能不能延长**，别白花时间

### 实测：快手登录态约 **20 分钟**失效，且**无法从代码层延长**

    20:46  扫码成功 → /rest/v/profile/get → result=1（拿到资料）
    21:0x  → result=109（中间态）
    21:0x  → result=2（未登录）

**解包 cookie 确认**（base64 → protobuf）：

    kuaishou.server.webday7_st → 字段名 + 248 字节**密文**
    passToken                  → 字段名 + 192 字节**密文**

密文里**没有 TTL** → 失效**由服务端控制**。
名字里的 `day7` 只是"最长 7 天"，实际被提前踢。

**调研结论（全网开源零实现）**：

  · MediaCrawler（★66k）`login.py` **只有登录、没有保活**
  · `cv-cat/KuaiShou-Spider` 只透传、不重建
  · 快手网页端**没有公开的 refresh 端点**

**唯一被验证过的路**：**让浏览器替你续期** ——
只要浏览器处于登录态，快手自己会刷新 `webday7_st`
（`/rest/v/profile/*` 响应带 `Set-Cookie`），
你只需**定期重读** `browser_context.cookies()`。

> ⚠️ **排查登录态问题的第一件事**：先确认它**是不是本来就会过期**。
> 我一开始以为是"检测器坏了"，改了三版判据 —— 其实有一半是
> **登录态真的过期了**。**两件事要分开查。**

### 顺带：快手还有一组 **6 分钟** TTL 的 cookie

    kwscode / kwssectoken    6/1440 天 = **6 分钟**
    （官方 SDK 在浏览器端本地续期；来源：cv-cat 项目复刻的 JS）

那是**风控凭证**，与会话凭证是两套。过期也会拖累请求成功率。

### 「搜索能用」≠「登录态有效」

快手**搜索/搜博主不需要登录**（公开数据），只有 `profile/*` 需要。
所以"搜索正常"完全不能说明登录态还好 ——
**这个坑本仓库踩过三次**（微博、X、快手）。

## ⚠️ 登录检测：**必须两种状态各测一遍**（血泪教训）

快手这个检测器我改了**三次**才对，每次都是"换了个新判据但没验证到位"：

| 版本 | 判据 | 为什么错 | 我只测了什么 |
|------|------|---------|-------------|
| ① | `[class*=avatar]` | 首页有**别人的**头像 | 只看了"登录时长什么样" |
| ② | 只判 cookie | **访客也有 `webday7_st`** | 只测了"未登录也有头像" |
| ③ | `/rest/v/profile/get` | **在白名单里，需签名** → 返回 `50`（签名失败）被我当成未登录 | 没用真实登录态验证 |
| ④ | 页面「登录即可享受」文案 | ✅ | 两种状态都测了 |

**铁律**：改完登录判据，必须用**「已登录」和「未登录」两种状态各测一遍**。

判据选择优先级：

    1. **站点自己的"我是谁"接口**（最优）—— 但要确认它**不需要签名**！
       ⚠️ 返回 `50`（签名失败）**不等于** `2`（未登录），别搞混
    2. **页面上的"未登录"文案**（次优）—— 实测可靠，比 cookie 稳
    3. **cookie 名**（最差）—— 访客常也有会话 cookie，**容易假阳性**
    4. ❌ **不要用模糊 CSS 选择器** —— 首页一般有**别人的**头像/昵称

判不出来一律**按未登录处理**（`ADDING_A_PLATFORM.md` 的规矩）。

## 常见症状 → 根因速查

| 症状 | 根因 |
|------|------|
| cookie 有值但"未登录" | `netscape_to_header` 域名别名不对 |
| 搜索"未登录"但 cookie 有效 | 站点有**两套登录体系**（微博 m 站 vs 主站） |
| **登录态用一会儿就失效** | **平台本来就短命**（快手实测 ~20 分钟，无法延长）—— 先确认是不是"本来就会过期"，别急着改检测器 |
| 后端支持但用户**选不到** | **前端下拉漏加**（X、快手**都漏过**）—— 每次都要查**全部**下拉入口 |
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
