# 微博 / 推特 接口调研结论

> 记录日期：2026-09-27
> 调研方式：`curl.exe` 抓 GitHub raw + **Playwright/bsk 在真实浏览器内实测**

---

## 一、微博

### 1. 关键结论：**必须登录，纯 HTTP 会被拒**

实测（不登录直接请求）：

```
GET https://m.weibo.cn/api/container/getIndex?...   → HTTP 432（len=0）
访问 m.weibo.cn / weibo.com / s.weibo.com
    → 全部重定向到 Sina Visitor System
GET 搜索 API（带访客 Cookie）→ {"ok":-100,
    "url":"https://passport.weibo.com/sso/signin?entry=wapsso..."}
```

访客系统只发 `WEIBOCN_FROM`，`visitor/genvisitor` 拿到的 tid 也换不到可用身份。

**在用户已登录的浏览器里，同一 URL 返回 `ok=1`，total=739~854 条。**
→ 所以微博必须带**真实登录 Cookie**，与小红书同一类（但小红书是签名，微博是登录态）。

### 2. 搜索接口（实测可用）

```
GET https://m.weibo.cn/api/container/getIndex
    ?containerid=100103type={type}&q={关键词}
    &page_type=searchall
    &page={页码}
→ {"ok":1, "data":{"cards":[...], "cardlistInfo":{"total":739,...}}}
```

搜索类型（来源 MediaCrawler `media_platform/weibo/field.py`）：

| type | 含义 |
|------|------|
| `1`  | 综合（默认） |
| `61` | 实时 |
| `60` | 热门 |
| `64` | 视频 |

### 3. 卡片结构（实测）

`data.cards[]` 里混着两类：

```
card_type = 9   微博正文卡片（有 mblog 字段）← 要的
card_type = 11  广告/运营卡片（跳过）
```

`mblog` 关键字段（实测 70+ 个字段）：

| 字段 | 含义 |
|------|------|
| `text` | 正文（HTML） |
| `created_at` | 时间 |
| `user.screen_name` / `user.id` / `user.profile_image_url` | 作者 |
| `pics[]` | 多图数组 |
| `pic_ids` / `pic_num` | 图片 id / 数量 |
| **`original_pic`** | **原图 URL** ← 不用猜后缀 |
| `bmiddle_pic` / `thumbnail_pic` | 中图 / 缩略图 |
| `attitudes_count` / `comments_count` / `reposts_count` | 赞 / 评 / 转 |
| `mid` / `bid` | 微博 ID |
| `page_info` | 视频/文章卡片信息 |

**图片 URL 字段是现成的**（`original_pic`），不需要像某些项目那样拼
`/orj360/` `/mw690/` 后缀 —— 实测 mblog 直接给 `original_pic`。

### 4. 视频字段（实测）

当 `page_info.type == "video"`：

```
page_info.media_info.stream_url / stream_url_hd   ← 直链
page_info.urls.mp4_720p_mp4 / mp4_hd_mp4 / mp4_ld_mp4   ← 多清晰度
page_info.page_pic.url                             ← 封面
page_info.duration                                 ← 时长（秒，浮点）
page_info.page_url                                 ← 视频页
```

### 5. 详情接口

MediaCrawler 用的是**解析 HTML**（不是 JSON API）：

    GET https://m.weibo.cn/detail/{note_id}
    → 从 HTML 里正则提取 `var $render_data = ([...])[0]`
    → render_data[0].status 即 mblog

我们**优先复用搜索卡片的 raw 数据**（同抖音的做法），
拿不到再走 detail 页。

### 6. 来源

| 结论 | 来源 |
|------|------|
| 搜索 URL + containerid + page_type | MediaCrawler `media_platform/weibo/client.py::get_note_by_keyword` |
| 搜索类型枚举 1/61/60/64 | MediaCrawler `media_platform/weibo/field.py::SearchType` |
| 详情走 HTML `$render_data` | MediaCrawler `client.py::get_note_info_by_id` |
| 卡片/mblog/视频字段 | **我方 Playwright 实测**（2026-09-27） |

---

## 二、推特 / X

### 1. 结论：**搜索强制要求登录**（与微博相反）

**先纠正一个容易误判的点。** 初步实测时看到：

```
document.cookie 无 auth_token          ← 以为"未登录"
x.com/search?q=美食 搜索结果正常渲染    ← 以为"免登录可搜"
```

**但这是误判**：`auth_token` 是 **httpOnly**，`document.cookie` 本来就看不到。
后续验证确认该浏览器**已登录** —— 页面上有只有登录后才出现的元素：

```
[发帖] [账号菜单] [通知] [私信] [Grok] [历史] [个人资料]
```

**决定性证据**：用 Patchright 全新 profile（真正未登录）打开
`https://x.com/search?q=美食&src=typed_query`：

```
→ 被重定向到 https://x.com/i/jf/onboarding/web?redirect_after_login=%2Fsearch...
→ article 数 = 0（没有任何推文）
```

即使先访问首页"入境"拿到 `gt`（guest token）cookie，搜索页**仍被重定向到登录引导页**。

### 2. 所以推特需要真实登录态

与微博（**实测确认免登录可搜**，`ok=1, total=870`）不同，
推特搜索**必须有 `auth_token`**（浏览器登录后由 Patchright 持久化 profile 复用）。

这与 gallery-dl 的做法一致：

    cookies_domain = ".x.com"
    cookies_names = ("auth_token",)
    # 且注明 "Login with username & password is no longer supported.
    #          Use browser cookies instead."

**这意味着**：推特要能用，前提是**用户在 YLCraft 的浏览器里登录过一次推特**。

### 3. 其他已确认的事实

| 项 | 结果 |
|---|---|
| guest token 端点 | `POST https://api.x.com/1.1/guest/activate.json` → 200 |
| queryId（gallery-dl 硬编码） | `4fpceYZ6-YQCx_JSl_Cn_A` → **404（已失效）** |
| queryId（当前真实值） | `uGB-gNd5HE4TkpO70OcFNw`（bsk network 捕获） |
| httpx + guest token + 新 queryId | **404** |
| 页面内 fetch（无额外头） | **403** |
| 页面内 fetch + `x-csrf-token`(ct0) | **仍 403** |
| 从 JS bundle 动态提取 queryId | **不可行**（懒加载分散，主 bundle 里只 1 处且非 Search） |

### 4. 图片/视频 URL 规则（gallery-dl，未在我方环境验证）

    self._size_image = "orig"
    self._size_fallback = ("4096x4096", "large", "medium", "small")
    # 形如: {base}?format={fmt}&name={size}

图片 URL 在 DOM 里是 `pbs.twimg.com/media/...`
（**注意排除 `profile_images`，那是头像**）。
视频在 `extended_entities.media[].video_info.variants[]`（yt-dlp 提取器）。

### 5. 来源

| 结论 | 来源 |
|------|------|
| guest token 端点 + Bearer | gallery-dl `extractor/twitter.py:1856` |
| 要求 auth_token、密码登录已停用 | gallery-dl `extractor/twitter.py:27-28, 782-793` |
| 图片尺寸规则 | gallery-dl `extractor/twitter.py:79-80, 266` |
| 搜索 queryId + variables | gallery-dl `extractor/twitter.py:1598-1613` |
| **搜索强制登录（未登录被重定向）** | **我方 Patchright 全新 profile 实测** |
| 当前 queryId | **我方 bsk network 实测捕获** |
| 页面已登录（有发帖/私信等元素） | **我方 bsk 实测** |

---

## 三、方法论：两次"差点误判"

这两次都是**把"没登录"误读成"免登录可用"或"接口坏了"**：

1. **微博**：httpx 返回 `ok=-100` →
   差点以为"微博搜索做不了"。实际是**缺 Service Worker 上下文**，
   换浏览器就通了。
2. **推特**：`document.cookie` 无 `auth_token` →
   差点以为"免登录可搜"。实际是 **httpOnly**，该浏览器是登录态的。

**教训**：判断登录态不能只看 `document.cookie`，要看
**只有登录后才出现的页面元素**（发帖/私信/账号菜单），
或者**用全新 profile 复现**（这才是真·未登录）。

**推论**：`ok=-100` / 重定向到登录页 / 空 article 列表，
都应报成**"需要登录"**而不是**"关键词无结果"** ——
前者用户能自己解决，后者会让人以为功能坏了。


---

## 三、方法论（沿用抖音那次的教训）

**按 URL 路径过滤，不要按响应体字段猜。**

这次微博调研验证了另一条经验：
**"接口不存在"和"没带登录态"要分清**。
`ok=-100` + 跳登录页 是**登录态**问题，不是接口废弃；
如果只看"返回空"就下结论，会误判成"微博搜索做不了"。


---

## 四、X（原 Twitter）纯 HTTP 方案 —— **已实测跑通**（2026-09-28）

### 4.1 结论修正：404 的真正原因不是 queryId，而是缺 `x-client-transaction-id`

之前记录的"四种直连方案全失败"里，**404 的主因判断错了**。
调研 twscrape / Scweet 后发现，两个项目都在代码里明确记录：

    twscrape/queue_client.py:
        # if code 404 on first try then generate new x-client-transaction-id
        # and retry     https://github.com/vladkens/twscrape/issues/248

    Scweet/transaction.py:
        "A request without the x-client-transaction-id header answers 404."

**实测验证**：用库里真实登录 cookie + 手工生成的 transaction-id：

    transaction-id 生成成功: TEDRYfzVqJDpSwK6D6kLPIq6UqrFPg7F3HvyOhAlxK89AVQb0wBAFnMv
    SearchTimeline → HTTP 200  len=145151  tweet 条目=20

**所以：X 可以不用浏览器运行时**（但仍需一次性登录 cookie）。

### 4.2 完整可用请求（实测）

    GET https://x.com/i/api/graphql/hyPfJYJ_XAtDYoslQc-Rgg/SearchTimeline
        ?variables={"rawQuery":"美食","count":20,"querySource":"typed_query",
                    "product":"Top","withGrokTranslatedBio":false}

    必须的请求头：
        authorization: Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D...
        x-csrf-token: <ct0 cookie>
        x-client-transaction-id: <动态生成>          ← 缺这个就 404
        x-twitter-active-user: yes
        x-twitter-auth-type: OAuth2Session
        user-agent: <真实浏览器 UA>
    必须的 cookie：auth_token + ct0（domain=.x.com）

Bearer 与 queryId 来源：twscrape `account.py` / `api.py`。

### 4.3 `x-client-transaction-id` 怎么生成

来自 twscrape `xclid.py`：抓 `https://x.com/tesla` 页面 →
用 BeautifulSoup 解析出 JS bundle →
`await load_keys(soup, clt)` 得到 `(vk_bytes, anim_key)` →
`XClIdGen(vk_bytes, anim_key).calc(method, path)`。

⚠️ **twscrape 自带的 `XClIdGen.create()` 在本机报 `ConnectError`**
（它内部用动态 UA `"@chrome"`）。但**直接用固定 UA 抓页面是通的**
（HTTP 200, 304KB），所以手工走上面三步即可 —— 实测成功。

### 4.4 cursor 翻页（实测）

取响应里 `cursorType == "Bottom"` 的 `value`，塞进下一轮
`variables.cursor`：

    第 1 页: 新增 20  累计 20   cursor=有
    第 2 页: 新增 22  累计 42   cursor=有
    第 3 页: 新增 21  累计 63   cursor=有
    第 4 页: 新增 22  累计 85   cursor=有

**想拿多少拿多少** —— 比 DOM 方案（受虚拟列表限制）强得多。

### 4.5 字段质量（实测）

    ★ @viviliao711
      正文: '肉末豆腐抱蛋，嫩到duang duang的！...'
      时间: Tue Sep 22 01:25:44 +0000 2026
      互动: 赞24 转2 评2
      媒体: 1 个 type=video url=pbs.twimg.com/amplify_video_thumb/...
      语言: zh

关键字段：`legacy.full_text` / `created_at` / `favorite_count` /
`retweet_count` / `reply_count` / `extended_entities.media` / `lang` / `id_str`。

⚠️ 两个注意点：
  · `views`（浏览量）GraphQL **没给**（实测 None）—— 不要编造
  · `media_url_https` 给的是 `_thumb` 缩略图，原图要按
    `?format=jpg&name=orig` 推导（gallery-dl 规则）

### 4.6 与"必须登录"的关系

**不矛盾**：X 搜索仍**必须登录**（未登录会被重定向到登录引导页），
但"必须登录"≠"必须开浏览器运行时"。只要有 `auth_token` + `ct0`
（一次性从浏览器导出），之后就能纯 HTTP 长期使用。

### 4.7 开源对比（本次调研核实）

| 项目 | 是否纯 HTTP | 凭证 | 状态 |
|------|-----------|------|------|
| **vladkens/twscrape** | ✅ | auth_token + ct0 | 活跃（默认分支 `main`） |
| **Altimis/Scweet** | ✅ | auth_token + ct0 | 活跃 |
| snscrape | ⚠️ 免凭证（guest token） | 无 | **停更于 2023-11**，queryId 全失效 |
| nitter | ❌ | — | **已 archived** |
| tweepy / python-twitter-v2 | ❌ | 官方付费 API | 不适用 |
| MediaCrawler | ❌ **无 twitter 模块**（只有 bilibili/douyin/kuaishou/tieba/weibo/xhs/zhihu） | — | — |

**官方 API 现状**（调研源：Postproxy / OpenTweet 2026 定价页）：
免费额度已取消（2026-02-06 关闭新项目，2026-06-01 强制迁移），
现为 pay-per-use **$0.005/条读取**，**且只有 7 天搜索窗口、无归档搜索**。

### 4.8 待办

把上述 HTTP 路径实现进 `services/platforms/twitter/`，
作为 **DOM 路径的替代/回退**：
  · 优先 HTTP（快、可翻页、字段全）
  · HTTP 失败（如 transaction-id 生成失败）→ 回退现有 DOM 路径
