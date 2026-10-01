# Telegram 采集指南

> 2026-10-01 实现并实测。**两条能力线**：免登录的公开频道（A）+ 需登录的账号能力（B）。

## 一、先记住这张表（能力边界）

| 想做什么 | 走哪条 | 需要登录 | 输入 |
|---------|-------|---------|------|
| 看**公开频道**的消息 | A（`t.me/s`） | ❌ 不需要 | 频道名，如 `durov` |
| **在某个公开频道内搜关键词** | A（`?q=`） | ❌ 不需要 | `durov AI` |
| 在**你已加入的**频道/群组里搜关键词 | B（MTProto） | ✅ 需要 | 关键词 |
| 列出你加入的频道 | B（MTProto） | ✅ 需要 | 无需输入 |
| 读**私有频道** | B（MTProto） | ✅ 需要 | 频道名 |
| 搜**所有公开频道** | ❌ **做不到** | — | — |

最后一行很重要，见下面「能力边界（别夸大）」。

## 二、A 方案：公开频道（免登录）

### 实测数据（2026-10-01）

```
https://t.me/s/telegram                    → 200，20 条/页
https://t.me/s/durov?q=Telegram            → 20 条，正文全部命中
https://t.me/s/durov?q=Apple               → 20 条（跨历史，ID 不连续）
https://t.me/s/durov?q=zzzqqqxx            → 0 条
https://t.me/s/durov?before=528            → 20 条（严格早于 528）
翻到 17 万条消息的频道                      → 无深度上限
```

**关键发现**：`?q=` 让**频道内关键词搜索免登录可用**。
页面上那个搜索框就是 `<form action="/s/durov"><input name="q">`。

### ⚠️ 踩过的坑（都是实测，别再犯）

| 坑 | 真相 |
|----|------|
| ~~频道不存在返回 404~~ | **返回 HTTP 200** + telegram.org 主页壳（~19KB）。**必须靠 `tgme_channel_info` 是否存在判断** |
| ~~视频拿不到直链~~ | `<video src>` **有 CDN 直链**（带 `token=`，会过期，只适合即时下载） |
| 图片不是 `<img>` | 是 `background-image: url('...')`，要正则从 style 抠。**唯独频道头像是真 `<img>`** |
| ~~`t.me/s` 不支持搜索~~ | `?q=` **支持**，免登录 |
| 不存在的频道 vs 用户账号 | 两者返回的页面**几乎一样**（`Telegram: Contact @xxx`），**无法区分** —— 文案要把两种可能都列出 |
| 引用回复的正文 | 用 `js-message_reply_text`，与 `js-message_text` **同时存在**，选择器写错会把引用内容当正文 |
| 时间 | 要读 `<time datetime="...">` 属性；`<time>` 的**文本只有 `16:08`** |
| emoji | `<i class="emoji" style="background-image:url(...)">` —— 别把 CSS 混进正文（`<b>` 里已有真实字符） |

### ⚠️ `t.me/s` 只对**广播频道**有效

公开**群组**返回 200 但 **0 条消息**。这很可能是"只能看最近消息"传言的真正来源。
群组要走 B 方案。

## 三、B 方案：MTProto 登录

### 申请凭证（免费，2 分钟）

1. 打开 https://my.telegram.org ，用 Telegram 手机号登录
2. 进「API development tools」→ 随便填个 App 名 → 创建
3. 拿到 `App api_id` 和 `App api_hash`

### 登录流程

在 `/telegram-login` 页面（账号中心点 Telegram 也会跳过去）：

```
api_id/api_hash + 手机号 → 发验证码
    → 提交验证码 → 完成
            ↘ 账号开了两步验证 → 再提交密码
```

验证码发到**你已登录的 Telegram 客户端**里（官方账号发的消息），**不是短信**。

### 文件位置（⚠️ 都是敏感凭证）

```
backend/data/telegram/account.session       ← telethon 登录会话
backend/data/telegram/credentials.json      ← api_id / api_hash
```

**已在 `.gitignore` 中排除**（与 `browser_profiles/` 同一性质：
进了 git 就等于把账号交出去）。

## 四、⚠️ 能力边界（别夸大 —— 这条最重要）

我第一版把 B 方案叫「**全网搜索**」，**这是错的、属于过度承诺**：

- `messages.SearchGlobal` 只搜 **你已加入的会话**（Telethon issue #4446）
- 真正搜所有公开频道要用 `channels.SearchPosts`，但它：
  - 需要 **Premium 账号**
  - 报 `403 PREMIUM_ACCOUNT_REQUIRED`
  - **按 Stars 计费**
- 本项目**不做**这条路

所以：

| 说法 | 对不对 |
|------|--------|
| ✅「搜你已加入的频道」 | 对 |
| ❌「全网搜索」/「搜所有公开频道」 | **错** |
| ✅「搜指定公开频道」（A 方案的 `?q=`） | 对，且免登录免费 |

回归测试 `test_telegram_client.py::test_joined_search_is_not_called_global_search`
和 `test_frontend_telegram_tabs` 会把这条固化下来（文案不得出现"全网搜索"）。

## 五、技术选型依据（调研过，不是拍脑袋）

| 方案 | 结论 |
|------|------|
| **A：自己解析 `t.me/s`** | ✅ 采用。bs4 + lxml 项目已装，**零新增依赖** |
| 第三方库（telegram-scraper / telegram-export） | ❌ **都已归档**；星多的 `telegram_media_downloader` 走 MTProto 不是 HTML 解析；真正解析 t.me/s 的库星数都是个位数 |
| **B：Telethon** | ✅ 采用。v1.45.0。注意 GitHub 仓库标 `archived` 但**已迁 Codeberg**，仍在更新（最新 2026-09-21） |
| Pyrogram | ❌ **已归档**（2024-12 停更） |
| kurigram | 活跃（v2.2.26），可作备选 |

## 六、下载

- **视频**：消息里的 `<video src>` CDN 直链（带 token，会过期）；
  或走 yt-dlp 的 `telegram:embed` 提取器（支持 `t.me/<ch>/<msgid>`）
  - ⚠️ yt-dlp 对**纯文本帖会 `returned nothing`**（实测 460 / durov 528），必须容错
  - ⚠️ yt-dlp 只认 `t.me/ch/msgid`，**不认** `t.me/s/ch`（列表页）
- **图片**：`background-image` 里的 CDN 直链，直接下

## 七、合规提醒（官方条款）

- **API ToS §1.5 禁止用 Telegram 数据训练 AI/ML 模型** —— 对内容采集项目是直接红线
- 造假订阅数/浏览量 = **永久封号**
- 官方称所有非官方客户端账号会 "automatically put under observation"，
  请**不要高频批量操作**（代码里对 FloodWait 做了可读提示，不会静默重试）

## 八、常见问题

**Q：验证码收不到？**
发到 Telegram App 里（官方账号的消息），不是短信。

**Q：报「未配置 API 凭证」？**
公开频道不需要凭证 —— 只有「已加入搜索 / 我的频道 / 私有频道」需要登录。

**Q：报 FloodWait？**
Telegram 服务端限流，提示里会写还要等多少秒。等待即可，不是程序错误。

**Q：频道拿不到内容？**
按提示排查：用户名拼错 / 是用户账号而非频道 / 私有频道 / 是公开群组
（`t.me/s` 只对广播频道有效）。
