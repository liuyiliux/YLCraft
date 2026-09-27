# 小红书（Xiaohongshu）接入指南

> 本文记录 YLCraft 接入小红书的**实测事实**。所有端点、参数、结论都来自真机验证，
> 未验证的一律标注"未确认"，不做猜测。

## 一、能力现状

| 能力 | 状态 | 实现位置 | 说明 |
|------|------|----------|------|
| 登录态检测 | ✅ 可用 | `services/cookies/platforms/xiaohongshu.py` | `/login` 重定向 + 头像选择器 |
| 登录态体检 | ✅ 可用 | `platforms/xiaohongshu/routes.py` | `GET /api/v1/xiaohongshu/login-health` |
| 关键词搜索 | ✅ 可用 | `platforms/xiaohongshu/search_patchright.py` | 必须走浏览器，见第三节 |
| 搜索翻页 | ✅ 已实现 | 同上 | 无限滚动加载 + 按页切片 |
| 笔记详情 | ✅ 可用 | `platforms/xiaohongshu/note.py` | 浏览器读 DOM，见第四节 |
| 图文图集 | ✅ 可用 | 同上 | `.swiper-slide img` + 去重 |
| 排序/筛选 | ❌ 未实现 | — | 搜索页参数未经抓包确认，不猜 |
| 评论采集 | ❌ 未实现 | — | 未抓包确认，不猜端点 |
| 去水印解析页 | ✅ 已接入 | `platforms/xiaohongshu/detail_adapter.py` | 桥接老链路 |

---

## 二、为什么小红书必须用浏览器

### 签名是硬门槛

| | 抖音 | 小红书 |
|---|---|---|
| 接口 | `/aweme/v1/web/general/search/single/` | `so.xiaohongshu.com/api/sns/web/v2/search/notes` |
| 签名 | **不需要**（实测直接 httpx 可通） | **需要 `X-s`/`X-t`** |
| 做法 | Python 直接 HTTP | 只能让浏览器自己发请求 |

签名函数 `window._webmsxyw` 是**混淆 JS**，且**跨域调用实测 406**，
所以无法在 Python 侧复现。

### 已失效的端点（勿重新启用）

```
edith.xiaohongshu.com/api/sns/web/v1/feed            → code:300011
edith.xiaohongshu.com/api/sns/web/v1/search/notes    → code:300011
```

`code:300011` 文案是「当前账号存在异常…」，但**不是账号真有问题**
（同一 Cookie 在浏览器里一切正常）——本质是缺签名被风控拒。

真实搜索端点已迁到 `so.xiaohongshu.com/api/sns/web/v2/search/notes`，
但同样要签名。

---

## 三、搜索的三个实测要点

### 1. 必须用 `add_cookies` 注入，不能用请求头传 Cookie

```
fetch_page(headers={"Cookie": ...})  → 0 张卡片
ctx.add_cookies(...)                 → 27~30 张
```

小红书的登录态判断依赖浏览器 cookie jar 里的域属性（domain/httpOnly/SameSite）。

### 2. 必须先访问首页"预热"

```
先 goto /explore 再 goto 搜索页 → ✅ 27 张
直接 goto 搜索页               → ❌ 超时 / 0 张
```

**这条最隐蔽**：搜索页的请求/响应都正常，只是数据永远不回来，
很容易误判成"被平台限制"。

### 3. 不能用无头模式

实测无头会被甩到验证码/登录页（与抖音同一个坑）。

### 翻页：无限滚动

搜索页没有 page 参数，翻页靠滚动加载：

```python
await _scroll_until(page, target)   # 滚到累计卡片数够为止（有轮次上限）
raw_cards = await page.evaluate(JS_PARSE_CARDS)
window = raw_cards[start:start + page_size]   # 按页切片
```

`total` 回报"已加载条数"作为下界（小红书不返回真实总数）。

### 卡片字段（实测）

| 字段 | 来源 |
|------|------|
| id | `section.note-item` 的 `data-note-id` 属性（比从 href 抠更稳） |
| 封面 | 卡片里**第一个 img**（第二个是作者头像，class 含 `author-avatar`） |
| 标题/作者/点赞 | 对应子元素 innerText |

---

## 四、笔记详情（2026-09-27 实测打通）

### 关键：必须带 xsec_token

```
/explore/{id}                     → 「当前笔记暂时无法浏览」
/explore/{id}?xsec_token=…        → ✅ 正常渲染
/search_result/{id}?xsec_token=…  → ✅ 正常渲染
```

token 来自搜索结果，且**会轮换**（实测 URL 里是 `AB128Hnm…`，
页面内已是 `AB0eZ6W7…`），所以只能用当次链接里的，不能长期缓存。

### 图片直接从 DOM 读，不需要签名接口

笔记页的图由页面自己从 `sns-webpic-qc.xhscdn.com` 加载，
所以读 DOM 即可。

### 选择器踩过两次坑（重要）

| 尝试 | 结果 |
|------|------|
| `[class*=note] img` | ❌ 3 图的笔记返回 **40 张**（混入推荐流） |
| 限定 `#noteContainer` 内取图 | ❌ 仍 **36 张**（容器内含底部推荐流） |
| **`.swiper-slide img` + 去重** | ✅ **3 张**，与页面 `1/3` 指示器一致 |

**swiper 会生成 duplicate slide**（同一张图出现两次），所以**必须去重**
（按去掉 query 的 URL 做键）。

### 交叉校验：用页面指示器

页面上的 `1/3` 是图集指示器，可用来交叉校验提取到的图片数。
两者不一致时记 warning，便于尽早发现选择器又失效了。

### 实测提取结果

```
标题：168cm/180斤古早波点穿搭和日落也太配了叭！
作者：禾子盒盒
图片：3 张（与 1/3 指示器一致）
下载：3 张，107 KB，文件头 RIFF….WEBP
```

---

## 五、缓存与会话复用

小红书搜索单次成本 15~20 秒（开浏览器 2~3s + 预热 6s + 开搜索页 5~10s），
所以有两层缓存（实现见 `platforms/session_pool.py` 与
`platforms/xiaohongshu/cache.py`）：

| 层 | 键 | 效果 |
|----|----|------|
| 结果缓存 | 平台+连接+关键词+类型+页码+每页数，TTL 10 分钟 | 同页 **16s → 0.38s** |
| 浏览器会话复用 | 平台+连接 | 省掉开浏览器 + 预热（~9 秒） |

实测：

```
1) 首次搜索    16.0 s
2) 同页再搜     0.38 s   ← 命中结果缓存
3) 第 2 页     22.2 s    ← 复用会话（仍需滚动加载）
5) 切回第 1 页   0.40 s   ← 命中结果缓存
```

**两个易错点（都已钉测试）**：

1. 缓存必须加在**共享入口** `search_via_patchright`。只加在
   `search_with_runtime`（自建浏览器分支）会完全失效——实际调用走的是
   **注入页分支**（`base._init_patchright` 先建好 page）。
2. 客户端退出时**不得**关闭已入池的会话，否则会关死复用中的会话，
   下次报 `TargetClosedError`。

---

## 六、图文笔记的资产储存结构

多图图文按**"集合 + 子图"两层**导入
（`services/crawler/service.py::_import_image_collection`）：

```
COLLECTION「标题」
  ├─ metadata: image_count, images[], platform, author, source_url
  ├─ IMAGE「标题 - 图1」→ metadata.remote_url
  └─ ...
```

判据 `is_multi_image_post()`：**多图 且 无视频**才建集合。

用 `AssetType.COLLECTION` + `AssetNode.parent_id` 表达层级（资产库已有），
**不用** `RelationType.CONTAINS` 关系表（`parent_id` 已表达层级，
再加关系表是重复信息）。采集阶段只存 URL 不落盘。

---

## 七、排查陷阱：残留浏览器进程

探测详情时曾看到页面显示「手机号登录」，误判为登录态失效。

**实际原因**：12 个残留 Chrome 进程占着同一个持久化 profile
（`backend/data/browser_profiles/xhs`），导致新会话打开的是旧窗口、状态错乱。

**排查命令**：

```powershell
Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" |
    Where-Object { $_.CommandLine -match 'browser_profiles' }
```

清理这些进程后一切正常。**注意**：只清理
`user-data-dir` 指向 YLCraft 目录的进程，不要动用户自己的 Chrome。

（这类残留来自探测脚本 `ctx.close()` 未彻底清干净，属于已知问题。）

---

## 七、用户搜索与个人主页（2026-09-27 实测，**尚未实现**）

用户问"小红书能不能做 UP主搜索和个人中心数据"。实测结论**与抖音不同**：

### 用户搜索：❌ 做不了

小红书的搜索接口只有一个：

```
so.xiaohongshu.com/api/sns/web/v2/search/notes
```

用 `type=54`（用户搜索）请求时，**返回的仍然是笔记**：

```
model_type 分布: {'note': 20, 'hot_query': 2}   ← 没有 user
```

页面上虽然渲染出了 31 个 `/user/profile/` 链接，但**没有独立的
用户列表接口**被调用——用户数据是混在笔记响应的 `note_card.user` 里
（只有昵称/头像，没有粉丝数）。

### 个人主页：✅ 可以做（资料读 DOM + 作品走接口）

实测打开 `/user/profile/{user_id}`：

```
页面正常渲染：title="逸流AI - 小红书"、30 个笔记链接
DOM 里能直接读到资料：
    {"fans":"195 粉丝","follows":"2 关注","liked":"2930 获赞",
     "nickname":"逸流AI","desc":"分享ai知识，入口，提示词"}
```

作品列表接口（实测捕获）：

```
GET https://edith.xiaohongshu.com/api/sns/web/v1/user_posted
```

> ⚠️ **没有找到"查他人资料"的接口**——遍历主页产生的 29 个 JSON 响应，
> 只有 `v2/user/me`（查自己）。所以资料只能**读 DOM**，
> 与笔记详情同一个套路。

### 与抖音的差异一览

| 能力 | 抖音 | 小红书 |
|------|------|--------|
| 用户搜索 | ✅ `discover/search`（有独立接口） | ❌ 无独立接口 |
| 用户资料 | ✅ `profile/other`（有接口） | ⚠️ 只能读 DOM |
| 作品列表 | ✅ `aweme/post` | ✅ `user_posted` |
| 主页标识 | **必须 `sec_uid`**（uid 打开是空页） | `user_id`（`/user/profile/{id}`） |

---

## 八、相关文件

| 文件 | 职责 |
|------|------|
| `platforms/xiaohongshu/search_patchright.py` | 搜索（预热/滚动/缓存） |
| `platforms/xiaohongshu/note.py` | 笔记详情（DOM 提取 + 交叉校验） |
| `platforms/xiaohongshu/detail_adapter.py` | 桥接「去水印解析」页 |
| `platforms/xiaohongshu/cache.py` | 结果缓存 |
| `platforms/xiaohongshu/search.py` | 已失效的 API 搜索（显式报错） |
| `platforms/session_pool.py` | 跨平台浏览器会话复用 |

测试：`tests/test_xhs_*.py`（搜索修复 / 缓存 / 详情 / 真实样本）
