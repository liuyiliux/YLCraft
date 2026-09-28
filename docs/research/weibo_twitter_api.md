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

### 1. 关键结论：**未登录也能搜索**（与"必须 auth_token"的普遍说法不同）

实测（2026-09-27，bsk 在真实浏览器）：

```
document.cookie 无 auth_token          ← 未登录
x.com/search?q=美食&src=typed_query    ← 页面正常
搜索结果正常渲染：
  wangguan @wangguan2ghr  对美食一点抵抗力没有…
  海派甜心 @paiisnobody   美食是健康的水煮菠菜…
```

网络捕获到真实请求：

```
GET https://x.com/i/api/graphql/uGB-gNd5HE4TkpO70OcFNw/SearchTimeline
    ?variables={"rawQuery":"美食","count":20,"querySource":"typed_query",
                "product":"Top","withGrokTranslatedBio":true}
    &features={...}
→ HTTP 200
```

**注意 queryId 是 `uGB-gNd5HE4TkpO70OcFNw`**，而 gallery-dl 里硬编码的是
`4fpceYZ6-YQCx_JSl_Cn_A` —— 用旧值实测 **HTTP 404**（queryId 会轮换）。

### 2. guest token 可以拿到

```
POST https://api.x.com/1.1/guest/activate.json
     Authorization: Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejR...
→ {"guest_token":"2104424973205110820"}   实测 HTTP 200
```

（Bearer 是 gallery-dl `extractor/twitter.py` 里的网页端固定值。）

### 3. 但 httpx 复现失败

| 方案 | 结果 |
|------|------|
| guest token + 新 queryId，httpx 直连 | **HTTP 404** |
| 页面内 fetch 同 URL（无额外头） | **HTTP 403** |
| 页面内 fetch + `x-csrf-token`(ct0) | **仍 403** |

页面 cookie 实测含 `ct0`（160 位）、`guest_id`、`twid`，**没有 `auth_token`**。
推特比微博严格得多，403 说明还差请求头组合（未查明是哪个）。

### 3b. queryId 会轮换，硬编码必然失效

- gallery-dl 里硬编码 `4fpceYZ6-YQCx_JSl_Cn_A` → 实测 **404**
- 当前真实值 `uGB-gNd5HE4TkpO70OcFNw`（我方 bsk network 捕获）

尝试从 JS bundle 动态提取：主 bundle 里 `queryId` 是**懒加载**的
（只匹配到 1 处且不是 Search），分布在多个 chunk 里。
**这条路太脆弱**，不作为方案。

### 3c. 可用路径：操作 UI + 读 DOM（已验证可行）

不依赖 queryId，直接**打开搜索页 URL，等渲染，读 `article` 节点**：

```
https://x.com/search?q={关键词}&src=typed_query         综合
https://x.com/search?q={关键词}&f=media&src=typed_query 图片/视频
```

实测 DOM 提取成功：

```json
{"articles": 4,
 "statusLinks": ["/TaoSeDao/status/2101202430444675082"],
 "text": "桃色岛TaoSeDao @TaoSeDao · 9月19日 胖胖de奇妙旅行…"}
```

能读到：推文 ID（从 `/status/<id>`）、作者、正文。
图片 URL 规则：`pbs.twimg.com/media/...`（**注意排除
`profile_images`，那是头像**）。

**下轮计划**：按这个路径实现（与微博同构：Patchright 打开页面 → 解析 DOM），
媒体原图按 `?format=jpg&name=orig` 升级（gallery-dl 规则，需实测确认）。

### 4. 图片/视频 URL 规则（来自 gallery-dl，未在我方环境验证）

    self._size_image = "orig"
    self._size_fallback = ("4096x4096", "large", "medium", "small")
    # 形如: {base}?format={fmt}&name={size}

即把 `&name=` 后面换成 `orig` 得原图。视频在
`extended_entities.media[].video_info.variants[]`（yt-dlp 提取器里有）。
**标注为"未验证"** —— 等下轮实测确认后再写代码。

### 5. 来源

| 结论 | 来源 |
|------|------|
| guest token 端点 + Bearer | gallery-dl `extractor/twitter.py:1856` |
| 图片尺寸规则 orig/4096x4096 | gallery-dl `extractor/twitter.py:79-80, 266` |
| 要求 auth_token Cookie | gallery-dl `extractor/twitter.py:27-28, 782-793` |
| 搜索 queryId + variables | gallery-dl `extractor/twitter.py:1598-1613` |
| **当前 queryId `uGB-gNd5HE4TkpO70OcFNw`** | **我方 bsk network 实测捕获** |
| 未登录可搜索 | **我方 bsk 实测**（cookie 无 auth_token，搜索结果正常） |

---

## 三、方法论（沿用抖音那次的教训）

**按 URL 路径过滤，不要按响应体字段猜。**

这次微博调研验证了另一条经验：
**"接口不存在"和"没带登录态"要分清**。
`ok=-100` + 跳登录页 是**登录态**问题，不是接口废弃；
如果只看"返回空"就下结论，会误判成"微博搜索做不了"。
