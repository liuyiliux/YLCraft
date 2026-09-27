# 用户搜索 / 用户主页 接口调研结论（抖音 + 小红书）

> 记录日期：2026-09-27
> 调研方式：把问题分别交给两个调研 subagent，用 `curl.exe` 抓 GitHub raw 文件
> （注：`web_fetch` / `web_search` 对 github.com 与 raw.githubusercontent.com
> 会被网络沙箱拦截，但 **`curl.exe` 全程通畅**，GitHub API 也可用）

---

## 一、最重要的结论：小红书"做不了"是**我方误判**

我在实现前用 Playwright 监听响应，得到两个错误结论：

| 我的结论 | 实际 |
|---|---|
| 用户搜索**做不了**（`type=54` 无效） | ❌ **错**。有独立接口，`type=54` 只是前端路由参数 |
| 用户资料**没有独立接口** | ❌ **错**。有 `user/otherinfo` |

### 误判的根因（值得记录）

我当时按「**响应体里同时含 `nickname` + `follower_count`**」过滤响应。
但：
- `user/otherinfo` 的资料在 `data.basic_info` 里，字段是 `nickname`/`red_id`，
  **没有 `follower_count`**（粉丝数在别处或缺失）
- `search/usersearch` 在 `data.users[]` 里，字段是 `name`/`fans`（字符串"140.9万"），
  **不是 `nickname`/`follower_count`**

**过滤条件没命中 → 我错误地推断"没有这个接口"。**

✅ **正确做法：按 URL 路径白名单过滤，而不是按响应体字段猜。**
（抖音那边我恰好蒙对了，因为抖音的字段名就是 `nickname`+`follower_count`。）

---

## 二、抖音（实测验证可用，**已实现**）

| 能力 | 接口 | 关键参数 |
|---|---|---|
| 用户搜索 | `GET /aweme/v1/web/discover/search/` | `keyword`, `search_channel=aweme_user_web`, `count`, `offset` |
| 用户资料 | `GET /aweme/v1/web/user/profile/other/` | **`sec_user_id`**（不是 uid）, `personal_center_strategy=1` |
| 作品列表 | `GET /aweme/v1/web/aweme/post/` | `sec_user_id`, `max_cursor`, `count` |

### 关键坑

1. **channel 与路径一一绑定**（四个 tab 各有独立路径 + 独立 channel）：

   | tab | 路径 | channel |
   |---|---|---|
   | 综合 | `general/search/single/` | `aweme_general` |
   | 视频 | `search/item/` | `aweme_video_web` |
   | 用户 | **`discover/search/`** | **`aweme_user_web`** |
   | 直播 | `live/search/` | `aweme_live` |

   把用户 channel 传给 `general/search/single` 是**无效操作**——
   该接口只认 `aweme_general`，返回综合结果是**预期行为，不是 bug**。

2. **主页必须用 `sec_uid`**。实测：
   ```
   /user/{uid}      → title="的抖音"     videoLinks=0   ❌
   /user/{sec_uid}  → title="李子柒的抖音" videoLinks=43  ✅
   ```
   原因（Evil0ctal 项目注释）：`the numeric uid rotates, the sec id does not`
   ——数字 uid 会变，sec_id 不会。

3. `max_cursor` 语义是**毫秒级发布时间戳**，不只是"游标"。

4. **`search_channel` 取值差异**：调研称必须 `aweme_user_web`；
   **我方实测 `aweme_user` 与 `aweme_user_web` 都能返回结果**
   （李子柒 5 条，两个值都通）。代码采用社区一致的 `aweme_user_web`，
   并保留 `aweme_user` 作备用常量。

### 签名

调研称 `aweme/post` 与 `aweme/detail` 在抖音的 ArgusSecurityPlugin
**保护白名单**里（社区实测约 5/8 被 403 拦截）。

**我方实测（2026-09-27，多次调用）：全部 `status_code=0`，
`aweme/post`、`profile/other`、`discover/search`、`aweme/detail`
都不需要签名，加不加 `x-tt-argus` 头也没差别。**

结论：**当前环境下抖音全链路无需签名**；但网关策略会变，
所以代码里**单独识别 403**，把它报成"风控拦截"而不是"没有数据"——
否则风控失败会被静默吞成"该用户没有作品"（最费时间的那类假阴性）。

---

## 三、小红书（**必须签名**，接口已实测打通）

| 能力 | 接口 | 参数 |
|---|---|---|
| 用户搜索 | **`POST /api/sns/web/v1/search/usersearch`** | body: `{"search_user_request": {keyword, search_id, page, page_size, biz_type:"web_search_user", request_id}}` |
| 用户资料 | **`GET /api/sns/web/v1/user/otherinfo`** | `target_user_id` |
| 作品列表 | `GET /api/sns/web/v1/user_posted` | `num`, `cursor`, `user_id`, `image_scenes=FD_WM_WEBP` |
| 备选用户搜索 | `POST /web_api/sns/v1/search/user_info` | **前缀是 `web_api` 不是 `api`** |

### 实测打通结果（2026-09-27，用 xhshow 签名）

```
用户搜索 usersearch  → code=1000 成功，20 个用户
   吕小厨爱美食 140.9万粉 / 开动吧小胖 / 美食 …
用户资料 otherinfo   → code=0 成功
   昵称=逸流AI  red_id=95645311698  简介='分享ai知识，入口，提示词'
作品列表 user_posted → code=0 成功，20 条
   has_more=True  cursor=69b187880000000015033a97
```

### 签名方案：`xhshow`（纯 Python）

**这是本次调研最有价值的发现。**

- `Cloxl/xhshow` —— 纯 Python 复现 `X-s` / `X-s-common` / `xsc`，**MIT**，
  **零 JS 文件**。`pip install xhshow`（实测可装，v0.2.0，仅依赖 pycryptodome）。
- MediaCrawler 与 XHS-Downloader 都已迁移到它；
  `ReaJason/xhs` 仍是旧方案（Playwright 注 JS + 独立 Flask 签名服务）。
- **依赖 cookie 里的 `a1`，且必须与 cookie 一致**，否则签名一直错。

### 浏览器内签名不可行（我方实测）

在已登录页面里探测 `window._webmsxyw` / `webmsxyw` / `sign` 等
**全部是 `undefined`**，webpack 容器也没暴露 —— 签名函数被打包进闭包了。
所以**只能走 `xhshow`**，不能在浏览器上下文里现签现发。

---

## 四、其他可用发现（尚未实现）

- `/aweme/v1/web/query/user/` —— 拿当前 session 的 uid，**游客态也能用**，
  可作 cookie 有效性探针（抖音）
- `/aweme/v1/web/user/following/list/` 与 `/user/follower/list/` ——
  关注/粉丝列表（★ 这两个**同时接受 `user_id` 和 `sec_user_id`**，与资料接口不同）
- `/aweme/v1/web/home/search/item/` —— **主页内搜索作品**（f2 独有发现）
- 小红书 `/api/sns/web/v1/user/selfinfo`、`/api/sns/web/v2/user/me` —— 查自己

---

## 五、调研局限（如实记录）

1. `f2` 的常量表里**没有**用户搜索接口 → 标注"未定义"，未断言其不支持
2. `MediaCrawler` 定义了 `USER` channel 但爬虫入口**未接入**用户搜索
3. `erma0/douyin` 仓库**已清空**，仅剩 README，未能调研
4. `singmoonshell/xhs-downloader`、`BradLeon/xhs_note_analyzer` 未逐文件全扫
5. 抖音签名保护白名单的社区实测日期为 **2026-09-08**，可能已过期
   （我方 2026-09-27 实测：**当前不受保护**）
6. 小红书除 `ReaJason/xhs` 外**没有任何项目实现用户搜索**——已逐一核实

---

## 六、方法论教训

**"监听所有 JSON 响应 + 按响应体字段过滤"这个方法有陷阱**：
字段名随平台/接口而异，猜错就会得出"接口不存在"的错误结论。

✅ 更稳的做法：**先按 URL 路径白名单过滤，再看响应结构**。
或者：直接把**所有** JSON 响应按 URL 归类打印出来，人工扫一遍 —
成本很低，但不会漏。
