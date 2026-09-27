# 抖音（Douyin）接入指南

> 本文记录 YLCraft 接入抖音的**实测事实**。所有端点、参数、结论都来自真机验证，
> 未验证的一律标注"未确认"，不做猜测。

## 一、能力现状

| 能力 | 状态 | 实现位置 | 说明 |
|------|------|----------|------|
| 登录态检测 | ✅ 可用 | `services/cookies/platforms/douyin.py` | DOM 判据（头像 / 登录提示），`profile/self` 仅作兜底 |
| 登录态体检 | ✅ 可用 | `platforms/douyin/health.py` | `GET /api/v1/douyin/login-health` |
| 关键词搜索 | ⚠️ 约 90% | `platforms/douyin/client.py::search` | 抖音对自动化环境**间歇性**限制，见第三节 |
| 搜索翻页 | ✅ 已实现 | 同上 | 单页 20，按 `max_results` 自动翻页 |
| 作品详情 | ✅ 可用 | `platforms/douyin/client.py::get_detail` | 端点见第二节 |
| 图文图集 | ✅ 可用 | 同上 | 每张图取 `download_url_list`（原图） |
| 评论采集 | ❌ 未实现 | — | 未抓包确认，不猜端点 |
| 去水印解析页 | ✅ 已接入 | `platforms/douyin/detail_adapter.py` | 桥接老链路 `services/video/parser.py` |

---

## 二、作品详情接口（2026-09-27 实测发现）

### 端点

```
GET https://www-hj.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={id}
```

> ⚠️ **关键：域名是 `www-hj.douyin.com`，不是 `www.douyin.com`。**
> 自己拼 `www.douyin.com/aweme/v1/web/aweme/detail/` 拿不到数据——
> 这是这条路径长期没被找到的原因。

### 发现方式（可复用）

之前尝试过、**都失败**的方式：

| 方式 | 结果 |
|------|------|
| 直接请求 iesdouyin 分享页读 `_ROUTER_DATA` | SSR 里已无数据（见下） |
| 导航前注入 `fetch`/`XHR` hook | 0 个请求（数据不走主框架） |
| 读 DOM 的 `<video>.src` | 空（延迟加载 / blob） |

**成功的方式**：Playwright 的 `page.on('request')` 监听**全部**请求
（含 worker 发起的）：

```python
page.on("request", lambda r: print(r.url))
page.on("response", lambda r: print(r.status, r.url))
await page.goto(f"https://www.douyin.com/video/{aweme_id}")
```

这一步直接打印出了 `www-hj.douyin.com` 这个域名。

### 返回结构（实测）

```json
{
  "status_code": 0,
  "aweme_detail": {
    "aweme_id": "...",
    "desc": "回到千禧年💿。#古早穿搭 ...",
    "create_time": 1782658001,
    "author": { "nickname": "Rinchyan", "uid": "..." },
    "statistics": {
      "digg_count": 17261, "comment_count": 47,
      "share_count": 5046, "collect_count": 2418
    },
    "images": [
      {
        "url_list":          ["...tplv-dy-aweme-images:q75.webp"],   // 压缩图
        "download_url_list": ["...tplv-dy-water-v2:...:2160:2880.webp"], // 原图
        "width": 2160, "height": 2880
      }
    ],
    "video": {
      "play_addr": { "url_list": ["..."] },
      "cover": { "url_list": ["..."] },
      "duration": 43000,   // 毫秒
      "width": 1920, "height": 1080
    }
  }
}
```

### 图文笔记的地址选择（**别混用**）

| 字段 | 内容 | 用途 |
|------|------|------|
| `image.url_list` | 压缩图（`q75.webp`） | 列表展示 |
| `image.download_url_list` | **原图**（实测 2160×2880） | **无水印下载** |

代码优先取 `download_url_list`。

### 一个实测的坑

图文笔记的 `video.play_addr` 指向的是**配乐**，不是视频：

```
https://lf9-music-east.douyinstatic.com/obj/ies-music-hj/7656013404485864251.mp3
```

当成视频地址会让前端误判成视频作品。代码里 `_looks_like_audio()` 负责过滤，
且**有 `images` 时直接不取 `video_url`**。

---

## 三、搜索接口（`/aweme/v1/web/general/search/single/`）

### 分页（2026-09-27 实测）

```
offset=0  → cursor=0
offset=20 → cursor=40
offset=40 → cursor=60
```

`cursor` 会推进，说明分页参数生效。**单页上限 20**（请求 `count>20` 也不会多给）。

`search()` 据此自动翻页：按 `max_results` 算页数、用响应 `cursor` 推进、
跨页去重、取够即停。

> 此前实现只请求一次、`count` 固定 10、`offset` 恒为 0，
> 所以用户无论选 10 还是 100 条都只拿到 9~10 条。

### 搜索类型（URL 抓包确认）

| 前端选项 | `search_channel` |
|----------|------------------|
| 综合 | `aweme_general` |
| 视频 | `aweme_video` |
| 用户 | `aweme_user` |
| 直播 | `aweme_live` |

### 间歇性受限（重要）

抖音对**自动化环境**的搜索接口有间歇性限制（约 90% 成功率）：

```
6/6 成功 → 3 分钟后 0/6 失败 → 6/20 成功 → 15/15 成功 → 8/8 ×2 成功
总计 48 次里 43 次成功
```

特征：
- 返回 `status_code=0` 但 `data=[]`（**不是**报错）
- 而**账号接口可能是正常的**（所以"账号正常"推不出"搜索正常"）
- 失败常成片（连续 14 次全失败），但隔一会儿能恢复

应对：空结果时**重试 3 次**、间隔 2/4/6 秒（只在第一页重试——
翻页中途为空通常是真的到底了）。仍失败则抛 `PlatformUnavailableError`
给出可读原因，**不降级到 yt-dlp**（那只会返回空，把"被风控"误报成"没结果"）。

### 已排除的可能（都实测过，无改善）

- Cookie 问题 —— 真实 Chrome 用同一 Cookie 能搜到
- 登录态问题 —— `profile/self` 有时返回 `user=True`
- UA 版本不匹配 —— 改为真实 Chrome/154 无效
- 启动参数暴露 —— 换干净参数无效
- `navigator.webdriver` —— Patchright 已内置反检测，实测 `false`
- `languages` / `chrome.app` —— 补齐指纹后仍无效
- 参数个数 —— 14 个与 32 个都试过
- **`a_bogus` 签名** —— 见下

### 关于 `a_bogus`（避免重复劳动）

开源项目（cv-cat/DouYin_Spider、MediaCrawler、TikTokDownloader）**都实现了
a_bogus 签名**，看起来像缺失的关键。

实测做了完整验证：从 DouYin_Spider 取来 528KB 的 `static/dy_ab.js`，
用 Node + jsrsasign 跑通，生成 164 字符的合法签名，对照调用：

```
完整参数 + 不带签名  → count=5  ✅
完整参数 + 带 a_bogus → count=0  ❌（签名反而画蛇添足）
```

**结论：a_bogus 不是缺失项，加了没用。** 该第三方代码**未采纳**。

上游 TikTokDownloader issue #600 有同样症状，作者回复：
**"经测试似乎需要新算法，新算法尚未开源。"**

---

## 四、已失效的方案（勿重新启用）

### iesdouyin 分享页（`services/video/parser_douyin.py`）

**原理**（曾经可用）：`www.iesdouyin.com/share/video/{id}/` 的 HTML 里
嵌有 `window._ROUTER_DATA`，含完整视频元数据，且无需登录。

**2026-09-27 实测失效**：

```
HTTP 200，页面能打开，_ROUTER_DATA 也在
但 loaderData['video_(id)/page'] 只剩：
    ['ua','isSpider','webId','query','renderInSSR','lastPath']
整页 HTML 关键词出现次数：
    videoInfoRes   0
    aweme_detail   0
    play_addr      0
    item_list      0
```

抖音把数据改成前端异步加载了，SSR 里什么都没有。
该模块的 docstring 已标注失效，**请勿重新启用**——改用第二节的详情接口。

---

## 五、图文笔记的资产储存结构

多图图文按**"集合 + 子图"两层**导入资产库
（`services/crawler/service.py::_import_image_collection`）：

```
COLLECTION「回到千禧年」
  ├─ metadata: image_count=9, images=[9个URL], platform, author, source_url
  ├─ IMAGE「回到千禧年 - 图1」→ metadata.remote_url
  ├─ IMAGE「回到千禧年 - 图2」→ metadata.remote_url
  └─ ...
```

判据 `is_multi_image_post()`：**多图 且 无视频**才建集合
（有视频的多图是"视频+封面图"，不是图集）。

设计取舍：

- 用 `AssetType.COLLECTION` + `AssetNode.parent_id` 表达层级
  （资产库已有，无需改表）
- **不用** `RelationType.CONTAINS` 关系表——`parent_id` 已表达层级，
  再加关系表是重复信息（`AssetNodeService` 也没有 `add_relation` 方法）
- 远端 URL 存 `metadata.remote_url`，**不立即下载**——采集阶段不该产生
  大量本地文件（用户还没决定要哪张），点"下载"时再落盘

对齐开源项目常见做法（XHS-Downloader、douyin-downloader 等
都是"作品 → 图片列表"两级）。

---

## 六、连接 ID 的注意事项

**用户重新登录抖音后，连接 ID 会变**（新建连接，旧记录失效）。

- 找"要复用的连接"时按 `updated_at` 倒序，**不能**按 `last_used`
  （新建连接的 `last_used` 是 `NULL`，`nulls_last` 会把它排到最后，
  于是新 cookie 写进旧记录，库里堆出多条同平台连接）
- 失效的 `conn_id` 会自动回退到该平台最近更新的连接
  （`login_health.resolve_connection`），避免误报"没有 Cookie"

---

## 七、相关文件

| 文件 | 职责 |
|------|------|
| `platforms/douyin/apis.py` | 端点常量、搜索参数构造、实测结论记录 |
| `platforms/douyin/client.py` | 搜索（含翻页/重试）、详情、解析 |
| `platforms/douyin/health.py` | 登录态体检 |
| `platforms/douyin/detail_adapter.py` | 桥接「去水印解析」页 |
| `platforms/douyin/routes.py` | HTTP 路由 |
| `services/cookies/platforms/douyin.py` | 登录态检测器 |

测试：`tests/test_douyin_*.py`（搜索类型 / 重试 / 翻页 / 详情 / 详情接口 / 体检）
