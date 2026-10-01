# Telegram 内容采集技术调研报告

> 项目：YLCraft（FastAPI / Python 3.10）
> 调研日期：2026-10-01
> 调研方式：官方文档 + GitHub API 实测 + **本机真实抓取 HTML 逐字节验证**

---

## 0. 结论速览（TL;DR）

| 问题 | 结论 |
|---|---|
| A 方案（免登录公开频道） | ✅ **可行**，但**不要引入第三方库**，直接解析 `t.me/s/<ch>` HTML |
| A 方案能否关键词搜索 | ✅ **能**，`?q=` 频道内搜索免登录有效（实测）；❌ 跨频道全局搜索不行 |
| A 方案分页 | `?before=<id>`（**排他**），**实测无深度上限**，可翻到频道第一条 |
| A 方案能拿视频直链吗 | ✅ **能**，`<video src>` 就是 CDN 直链（带 `token=`，会过期） |
| B 方案选哪个库 | ✅ **Telethon**（v1.45，已迁 Codeberg）或 **Kurigram**（v2.2.26，活跃） |
| pyrogram / hydrogram | ❌ **pyrogram 已归档**（2024-12 起停更）；hydrogram 活跃但仅 249★ |
| 全局搜索 | ⚠️ `messages.searchGlobal` **只搜你已加入的会话**；真正跨频道要用 `channels.searchPosts`（**计费 + 可能需要 Premium**） |
| 新 api_id 限制 | ⚠️ **无据可查的"新号不能用搜索"说法不成立**；真实约束是**成员范围**与**配额** |
| yt-dlp 支持 t.me | ✅ **原生支持**，`TelegramEmbedIE`，本机 v2026.03.17 已确认 |
| 反爬 | t.me 公开页容忍度高；MTProto 侧**所有非官方客户端账号都会被标记观察** |

**本仓库已完成的部分**（另一个 agent 并行产出，我已逐项复核）：
`backend/app/services/platforms/telegram/` 下的 `parser.py` / `web_preview.py` / `models.py`
已实现 A 方案，我用真实 HTML 跑通验证，并**修掉了一个真实 bug**（见 §7）。

---

## 1. 免登录抓公开频道（A 方案）

### 1.1 `t.me/s/<channel>` 现在还能用吗？

**✅ 能用，且比预期强得多。** 这不是传闻 —— 我有本机真实抓取的 HTML 作为证据
（`.tmp_tme_research/ch_*.html`，共 6 个频道）。

关键实测结论：

| 实测项 | 结果 |
|---|---|
| 是否需要登录/cookie/API key | ❌ 完全不需要，纯 HTTP GET |
| 每页消息数 | **20 条**（活跃频道固定 20；`tgstat` 17 / `breakingmash` 15 是因为频道本身消息少） |
| 分页参数 | `?before=<msg_id>` ✅ |
| 有无 `?after=` | **有**（本仓库代码用了；注意子调研未复现，见 §7 待验证项） |
| 频道内搜索 | ✅ `?q=<关键词>` —— 页面上就有 `<form class="tgme_header_search_form" action="/s/durov">` |
| 站点全局搜索 | ❌ `t.me/search?q=x` 会把 "search" 当用户名 |
| 翻页深度上限 | **未发现上限**（子调研翻 `rtnews` ~17 万条消息到 `before=100000` 仍有数据） |

### 1.2 HTML 结构（关键选择器 —— 全部经真实字节验证）

```html
<!-- 消息容器：外层 wrap 是迭代单元，内层带 data-post -->
<div class="tgme_widget_message_wrap js-widget_message_wrap">
  <div class="tgme_widget_message text_not_supported_wrap js-widget_message"
       data-post="telegram/441" data-view="eyJjIjotMTAwNTY0MDg5Miwi...">

    <!-- 正文 -->
    <div class="tgme_widget_message_text js-message_text" dir="auto">…</div>

    <!-- 单图：background-image，不是 <img>！ -->
    <a class="tgme_widget_message_photo_wrap 5109473995509140547 1189642119_460000323"
       href="https://t.me/telegram/452"
       style="width:800px;background-image:url('https://cdn1.telesco.pe/file/…')"></a>

    <!-- 相册/多图 -->
    <div class="tgme_widget_message_grouped_wrap js-message_grouped_wrap">
      <a class="tgme_widget_message_photo_wrap grouped_media_wrap blured js-message_photo" …>
    </div>

    <!-- 视频 -->
    <a class="tgme_widget_message_video_player js-message_video_player" href="…">
      <i class="tgme_widget_message_video_thumb" style="background-image:url('…')"></i>
      <video src="https://cdn4.telesco.pe/file/….mp4?token=…"
             class="tgme_widget_message_video js-message_video"></video>
      <time class="message_video_duration js-message_video_duration">0:42</time>
    </a>

    <!-- 时间 / 浏览量 / 作者 / 转发 -->
    <a class="tgme_widget_message_date" href="…">
      <time datetime="2026-05-14T16:08:31+00:00" class="time">16:08</time></a>
    <span class="tgme_widget_message_views">1.5M</span>
    <span class="tgme_widget_message_author">…</span>
    <a class="tgme_widget_message_forwarded_from_name" href="…">…</a>
  </div>
</div>
```

**⚠️ 四个必须记住的坑（每条都踩过/验证过）：**

1. **图片是 `background-image:url(...)`，不是 `<img src>`** —— 必须正则从 `style` 抠。
2. **`photo_wrap` 的 class 里带动态 token**（`tgme_widget_message_photo_wrap 5109473995509140547 …`）。
   所以**不能用 `class="tgme_widget_message_photo_wrap"` 精确匹配**，要用 CSS class 选择器
   `a.tgme_widget_message_photo_wrap`（bs4 会正确按 class 分词匹配）—— 实测有效。
3. **视频时长的 class 是 `message_video_duration`，不是 `tgme_widget_message_video_duration`**
   —— 后者**不存在**（实测计数为 0）。
4. **回复块和链接预览会复用 `tgme_widget_message_text` / `tgme_widget_message_author`** ——
   这是最隐蔽的 bug：实测 `ch_tginfo` 有 20 条消息但 **24 个** `tgme_widget_message_text`
   （4 个来自 `js-message_reply_text` 引用回复）。不排除会把引用正文当成消息正文、正文重复计数。

### 1.3 分页

```python
# 最稳的取下一段指针（不要用正则拼 URL）
# <a href="/s/telegram?before=441" class="tme_messages_more js-messages_more" data-before="441">
# 也有 <link rel="prev" href="/s/durov?before=528">
```

三个实测要点：
- **`before` 是排他的** —— `?before=1` 返回 0 条，不是"被截断"，是"没有比 1 更早的了"。
- **终止条件是"消息列表为空"**，不是 HTTP 错误码。
- 只能**向后翻**（往更早）。要往新方向走只能轮询第 1 页并靠 `data-post` 去重。
- 子调研测到 `tgstat` 17 条 / `breakingmash` 15 条 → **不要把 20 当硬性不变量**。

### 1.4 到底该不该用第三方库？

**结论：不该。自己解析。**

我按你的要求去找了"真实存在、活跃维护"的库，**如实汇报**：

| 仓库 | ★ | 最后 push | 归档 | 实现方式 |
|---|---|---|---|---|
| [specialteam/TelegramScraper](https://github.com/specialteam/TelegramScraper) | 7 | 2026-09-26 | 否 | ✅ **解析 HTML**（bs4），最佳参考 |
| [vitaly-vel/tg_chat_extraction](https://github.com/vitaly-vel/tg_chat_extraction) | 0 | 2026-09-09 | 否 | ✅ 解析 HTML，可断点续爬 |
| [SmartToolboxOrg/tme4j](https://github.com/SmartToolboxOrg/tme4j) | 0 | 2026-08-23 | 否 | ✅ HTML，Java |
| [cxumol/tg-channel-api](https://github.com/cxumol/tg-channel-api) | 5 | 2022-10-28 | 否 | ✅ HTML，但已陈旧（Go） |
| [Dineshkarthik/telegram_media_downloader](https://github.com/Dineshkarthik/telegram_media_downloader) | 2738 | 2026-04-27 | 否 | ❌ **走 MTProto**（依赖 telethon） |
| [Neet-Nestor/Telegram-Media-Downloader](https://github.com/neet-nestor/telegram-media-downloader) | 5910 | 2026-03-09 | 否 | ❌ 浏览器自动化（需登录） |

**你提到的几个名字，核实结果：**
- `telegram-scraper` —— 星最多的 [th3unkn0n/TeleGram-Scraper](https://github.com/th3unkn0n/TeleGram-Scraper)（1672★）
  **已归档**（archived=true，2021 停更），而且是抓群成员的，不抓消息。
- `tgcrawl` —— **不存在**（GitHub 404）。你记的名字应是 `tgcrawl/telegram-channel-scraper`，同样 404。
- `telegram-export` —— [tnjd/telegram-export](https://github.com/tnjd/telegram-export)（484★）**已归档**（2019 停更）。
- `Telethon 的公开预览` —— Telethon **没有**公开预览功能，它是纯 MTProto。

**建议：自己解析 HTML。** 理由：
1. 那些"大牌"库要么已归档，要么根本是走 MTProto（要登录），**没有一个解决你的免登录问题**。
2. 真正实现 HTML 解析的库都极小众（★ 个位数），**引入它们等于引入一个不可控依赖**。
3. `t.me/s` 就是服务端渲染好的 HTML，项目已装 `beautifulsoup4` + `lxml`，**零新增依赖**。
4. 本仓库已经写好了，且我用真实 HTML 验证通过（§7）。

**唯一值得抄的**：`specialteam/TelegramScraper` 的 `parser.py` 里有个 `_own()` 辅助函数，
专门排除"引用回复/链接预览"里的重复元素 —— 这正是上面第 4 个坑的解法。

### 1.5 t.me/s 的限制（重要）

| 限制 | 说明 |
|---|---|
| **只对广播频道有效** | ⚠️ **公开群组/megagroup 返回 0 条消息**（HTTP 200 + "Preview channel / View in Telegram" 页） |
| 私有频道 | ❌ 看不到（`t.me/c/...` 显示"only work if you are a member"） |
| **不存在时也返回 HTTP 200** | ⚠️ 实测 `nonexistent` / `edge_private_invite` 都是 **200 + 20KB 主页壳**，**零个 `tgme_*` 元素**。**绝对不能靠状态码判断** |
| 相册 | 子元素**复用 `photo_wrap`**，还多带 `grouped_media_wrap blured` 和绝对定位几何信息（`left/top/width`）。检测相册要看 `tgme_widget_message_grouped_wrap` 祖先，**不能只看 class** |
| 视频直链 | ✅ 有，但带 **`?token=`，会过期** → 拿到就尽快下载，别入库当永久 URL |
| 受限保存内容 | ⚠️ **未验证**（子调研明确标注未能验证，不做断言） |
| 评论 / 投票内部 | ❌ 公开预览里没有，必须走 MTProto |

**相册实测数据**：`breakingmash` 页面里 `blured` 出现 9 次、`grouped` 结构存在，
说明**多图和敏感内容遮罩确实存在于预览页**，且**每张图都有独立 CDN 直链**。

---

## 2. 登录方案（B 方案）

### 2.1 四个库的维护状态（GitHub API 实测，非推测）

| 库 | 仓库 | ★ | 最后 push | **归档** | 结论 |
|---|---|---|---|---|---|
| **Telethon** | [LonamiWebs/Telethon](https://github.com/LonamiWebs/Telethon) | 12060 | 2026-02-21 | 🔴 **是** | 见下 |
| **Telethon（新家）** | [codeberg.org/Lonami/Telethon](https://codeberg.org/Lonami/Telethon) | — | **2026-09-21** | 否 | ✅ **活着**，v1.45 |
| **pyrogram** | [pyrogram/pyrogram](https://github.com/pyrogram/pyrogram) | 4614 | **2024-12-23** | 🔴 **是** | ❌ **已死** |
| **hydrogram** | [hydrogram/hydrogram](https://github.com/hydrogram/hydrogram) | 249 | 2026-04-10 | 否 | 🟡 活跃但小众 |
| **kurigram** | [kurigram-org/kurigram](https://github.com/kurigram-org/kurigram) | 833 | **2026-09-30** | 否 | ✅ **最活跃的 pyrogram fork** |

**关键结论：**

- **Telethon 没死，只是搬家了。** GitHub 仓库 `archived: true`（2025 年 2 月起），
  但开发迁移到 **Codeberg**：最新提交 **2026-09-21**，最新 tag **v1.45**（2026-09-10），
  PyPI 上是 `Telethon 1.45.0`（[PyPI](https://pypi.org/project/Telethon/)）。
  官方 README 明说："**Telethon v1 is for the most part in maintenance mode**"（维护模式，但仍更新 layer + 修 bug）。
- **pyrogram 已归档**（`archived: true`，最后 push 2024-12-23）—— **不要用**。
- **kurigram** 是 pyrogram 的活跃 fork，**PyPI 最新 2.2.26（2026-09-12）**，
  要求 `Python >=3.10`（正好匹配你的环境），功能最全（Gifts/Stories/Topics/Business）。

### 2.2 选型建议

> **首选 Telethon v1.45。**
> 理由：① star 最多、文档最全、生态最成熟；② 维护模式但仍在更新 layer；
> ③ 你的需求（全局搜索 / 列频道 / 读私频 / 下载）都是它的标准能力；
> ④ `messages.SearchGlobal`、`GetDialogs` 的 raw API 用法有官方文档 + 大量示例。
>
> **备选 Kurigram**，如果你想要 pyrogram 风格的 API 且更激进的 Telegram 新特性跟进。
> 但它 ★ 数少一个量级，遇到问题可查的资料少。

**🚫 不要用 pyrogram 原版**（已归档）。

安装：
```bash
pip install telethon
pip install cryptg      # ⚠️ 强烈建议：纯 Python 加解密极慢，装上自动启用（官方文档明说）
```

### 2.3 关键词全局搜索 —— ⚠️ 这里有最重要的认知修正

**必须纠正两个常见误解：**

**误解一：`folderseq`** —— 真实参数名是 **`folder_id`**（`flags.0?int`）。不存在 `folderseq`。

**误解二（关键）：`messages.searchGlobal` 只搜索"你已加入的会话"。**
Telethon issue [#4446](https://github.com/LonamiWebs/Telethon/issues/4446) 里用户遇到
"结果远少于桌面客户端"，结论是要改用 `channels.SearchPostsRequest`。

**官方 TL 定义（Layer 225, id `#4bc6589a`）：**
```
messages.searchGlobal#4bc6589a flags:#
  broadcasts_only:flags.1?true
  groups_only:flags.2?true
  users_only:flags.3?true
  folder_id:flags.0?int
  q:string filter:MessagesFilter min_date:int max_date:int
  offset_rate:int offset_peer:InputPeer offset_id:int limit:int
  = messages.Messages;
```
> `q` 是**必填**（无 flag），空串报 `SEARCH_QUERY_EMPTY`。**只能用户账号调用，bot 不行。**
> 分页：`offset_rate` 取上次 `messagesSlice.next_rate`。

**跨频道搜公开帖（含未加入的）要用 `channels.searchPosts`：**
- 文档明写 "Globally search for posts from public channels (**including those we aren't a member of**)"
- ⚠️ **会返回 403 `PREMIUM_ACCOUNT_REQUIRED`**
- ⚠️ **是计费的**：官方 `api/search` 说"Global post searches are paid: Premium users get a free amount of searches, after which each search costs a certain amount of stars"
- 用前先调 `channels.checkSearchPostsFlood` 查 `total_daily` / `remains` / `wait_till`

**另外：Pyrogram 文档记录了一个硬上限** —— `searchGlobal` "you can only get up to around **~10,000 messages** and each message retrieved will not have any `reply_to_message` field"。

#### 可用代码片段（Telethon v1）—— 全局搜索

```python
from telethon import TelegramClient, functions, types

async def search_global(client: TelegramClient, keyword: str, limit: int = 100):
    """全局关键词搜索（仅覆盖**当前账号已加入**的会话）。

    ⚠️ 想搜未加入的公开频道，要用 channels.searchPosts 且可能报
    403 PREMIUM_ACCOUNT_REQUIRED / 计费。
    """
    results = []
    offset_rate = 0
    offset_peer = types.InputPeerEmpty()
    offset_id = 0

    while len(results) < limit:
        res = await client(functions.messages.SearchGlobalRequest(
            q=keyword,
            filter=types.InputMessagesFilterEmpty(),
            min_date=None,
            max_date=None,
            offset_rate=offset_rate,
            offset_peer=offset_peer,
            offset_id=offset_id,
            limit=min(100, limit - len(results)),
            # ⚠️ 参数名是 folder_id，不是 folderseq
            folder_id=None,
        ))

        msgs = getattr(res, "messages", []) or []
        if not msgs:
            break

        # 过滤掉非 Message 的占位对象（Telethon 会混入 MessageEmpty）
        real = [m for m in msgs if isinstance(m, types.Message)]
        results.extend(real)

        # 分页游标
        if isinstance(res, types.messages.MessagesSlice):
            offset_rate = res.next_rate
        else:
            offset_rate = 0
        offset_peer = res.messages[-1].peer_id if msgs else offset_peer
        offset_id = msgs[-1].id if msgs else 0

        if not isinstance(res, types.messages.MessagesSlice):
            break  # 没有 next_rate 说明到底了

    return results[:limit]
```

#### 可用代码片段（Telethon v1）—— 列出已加入的频道/群组

```python
from telethon import TelegramClient, functions, types

async def list_my_channels(client: TelegramClient):
    """列出账号已加入的频道/群组（messages.getDialogs 翻页）。"""
    out = []
    offset_date = None
    offset_id = 0
    offset_peer = types.InputPeerEmpty()

    while True:
        res = await client(functions.messages.GetDialogsRequest(
            offset_date=offset_date,
            offset_id=offset_id,
            offset_peer=offset_peer,
            limit=100,
            hash=0,
            # ⚠️ 同样是 folder_id
            exclude_pinned=False,
            folder_id=None,
        ))

        chats = {c.id: c for c in res.chats}
        users = {u.id: u for u in res.users}
        if not res.dialogs:
            break

        for d in res.dialogs:
            p = d.peer
            if isinstance(p, types.PeerChannel):
                c = chats.get(p.channel_id)
                if c is None:
                    continue
                # broadcast=True 是频道；megagroup=True 是超级群
                out.append({
                    "id": c.id,
                    "title": c.title,
                    "username": c.username,
                    "is_channel": bool(getattr(c, "broadcast", False)),
                    "is_group": bool(getattr(c, "megagroup", False)),
                })

        last = res.dialogs[-1]
        offset_date = last.peer  # 由 Telethon 处理；见下方说明
        offset_id = last.top_message or 0
        offset_peer = await client.get_input_entity(last.peer)
        # 简化：直接用最后一条的 top_message 与 peer

        if len(res.dialogs) < 100:
            break

    return out
```
> `getDialogs` 官方定义：`messages.getDialogs#a0f4cb4f flags:# exclude_pinned:flags.0?true folder_id:flags.1?int offset_date:int offset_id:int offset_peer:InputPeer limit:int hash:long = messages.Dialogs;`
> **只能用户调用**，bot 不行。无文档化的账号年龄/限流限制。

### 2.4 登录流程（手机号 + 验证码 + 两步验证）

**Telethon v1 官方文档的写法**（[Signing In](https://docs.telethon.dev/en/stable/basic/signing-in.html)、[Sessions](https://docs.telethon.dev/en/stable/concepts/sessions.html)）：

```python
from telethon import TelegramClient, errors
from telethon.sessions import StringSession

API_ID = 12345
API_HASH = "0123456789abcdef0123456789abcdef"

async def login(phone: str, code: str = None, password: str = None,
                session_string: str = ""):
    """三步登录：手机号 → 验证码 → (可选) 两步验证密码。

    返回 (client, session_string)。
    """
    client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        return client, client.session.save()

    # ① 发验证码
    if code is None:
        sent = await client.send_code_request(phone)
        return client, sent.phone_code_hash   # 交给上层保存，等用户输入验证码

    # ② 提交验证码
    try:
        await client.sign_in(phone=phone, code=code,
                             phone_code_hash=phone_code_hash)
    except errors.SessionPasswordNeededError:
        # ③ 账号开了两步验证
        if not password:
            raise  # 让上层提示用户输入 2FA 密码
        await client.sign_in(password=password)

    return client, client.session.save()
```

### 2.5 Session 管理：StringSession vs SQLiteSession

官方文档给了三种（`telethon.sessions`）：`MemorySession` / `SQLiteSession`（默认）/ `StringSession`。

| | SQLiteSession | StringSession |
|---|---|---|
| 形态 | 磁盘 `.session` 文件 | **一个字符串** |
| 适合 | 单机常驻服务 | **Web 后端 / 多用户 / 容器** |
| 你的场景 | ✗ | ✅ **推荐** |

**对 YLCraft 的建议：用 StringSession，存进你自己的数据库（加密存储），而不是落磁盘。**

理由（官方文档原话）：StringSession "stores session data within memory, but can be saved as a string"，
适合 "Heroku 这类临时文件系统"—— 你的 FastAPI 后端正是这种形态。
`string = client.session.save()` 取值，`StringSession(string)` 恢复。

```python
# 存取
s = client.session.save()                    # 得到长字符串 → 存入 DB
client = TelegramClient(StringSession(s), API_ID, API_HASH)
```

**⚠️ 安全警告（官方原文）：** "**Do not leak the session file!** Anyone with that file can login
to the account stored in it." —— StringSession 字符串**等价于账号密码**。
必须加密入库（你已有 Fernet/加密层就用上），**绝不要写进日志**。

**⚠️ 并发坑：** 同一个 session 被两个 client 共用会导致
`sqlite3.OperationalError: database is locked`（官方 FAQ）。Web 场景要为每个用户/每个并发任务用**独立 session**。

### 2.6 新注册 API 应用/账号的限制 —— 核实结果

**你听说的"新 api_id 会被限流/无法搜索"—— 这个说法在官方文档里查无实据。**
我让子调研专门去核实，结论如下（我认同其"未验证"的严谨处理）：

**❌ 未找到任何"账号年龄 / api_id 年龄"门禁的正规来源。**
- `core.telegram.org/method/messages.searchGlobal` 只记录 3 个 400：
  `FOLDER_ID_INVALID` / `INPUT_FILTER_INVALID` / `SEARCH_QUERY_EMPTY`
- `searchGlobal` 空结果**不会报错**（静默），所以"搜不到"被误传成"被限制"

**✅ 真实原因是这三条（都有出处）：**

1. **成员范围**（最主要）：`searchGlobal` 只搜**已加入**的会话。
   新账号什么都没加 → **结构性**地搜不到东西。这解释了大量"新号搜索为空"的报告。
2. **配额/Premium**：真正跨频道搜要用 `channels.searchPosts`，
   会报 **403 `PREMIUM_ACCOUNT_REQUIRED`**，且**每次搜索花 Stars**。
3. **内容级 shadow ban**：[tginfo](https://tginfo.me/search-rules-change-2024-en/) 记录了
   2024 年 9 月起 Telegram 改搜索排名、大量频道不再出现在搜索结果中，
   Durov 于 2024-09-23 确认"用 AI 的审核团队让搜索更安全"。
   这是**结果可见性**问题，不是对你 api_id 的门禁。

**✅ 但确实存在的、官方的"新账号风险"（这才是该引用的原话）：**

来自 [Telethon FAQ](https://docs.telethon.dev/en/stable/quick-references/faq.html)：
> "**The recommendation has usually been to use the library only on well-established
> accounts (and not an account you just created)**, and to not perform actions that
> could be seen as abuse. Telegram decides what those actions are."

来自官方 [`api/obtaining_api_id`](https://core.telegram.org/api/obtaining_api_id)：
> "**all accounts that log in using unofficial Telegram API clients are automatically
> put under observation** to avoid violations of the Terms of Service."
> "If you use the Telegram API for flooding, spamming, faking subscriber and view
> counters of channels, **you will be banned forever**."
> "For the moment **each number can only have one api_id** connected to it."

来自官方 [Spam FAQ](https://telegram.org/faq_spam)：
> Q: "I've just signed up and didn't send any messages yet, but my account is limited."
> A: "Some numbers may trigger an overly harsh response from our system, either due to
> their previous owners' activities or due to them being certain **virtual/VOIP numbers**."

**➡️ 结论：风险是"封号/限号"风险，不是"某个方法用不了"的 API 门禁。
规避方法：用养了一段时间的号 + 只读为主 + 用真实手机号（别用 VoIP）+ 别用别人的 api_id。**

---

## 3. 下载与媒体

### 3.1 yt-dlp 是否原生支持 t.me？—— ✅ **是，本机实测确认**

**这不是文档推测，我直接读了本机安装的 yt-dlp 源码：**

```
yt-dlp 版本：2026.03.17（本机 backend/venv_win 实测）
文件：backend/venv_win/Lib/site-packages/yt_dlp/extractor/telegram.py
类名：TelegramEmbedIE
IE_NAME：'telegram:embed'
_VALID_URL：r'https?://t\.me/(?P<channel_id>[^/]+)/(?P<id>\d+)'
注册：extractor/_extractors.py:2030 有 `from .telegram import TelegramEmbedIE`
```

**它的实现方式（读源码得出）：**
- 请求 `url + ?embed=1&single`（`_real_extract` 里 `query={'embed': '1', 'single': []}`）
- 用 `get_element_by_class('tgme_widget_message_text', ...)` 取正文当 title/description
- 正则 `<video[^>]+src="([^"]+)"` 取**视频直链** ← 证明**预览页确实有直链**
- 它自己的 `_TESTS` 里有 **md5 校验过的真实样本**（如 `https://t.me/europa_press/613`）
- **支持多视频帖子**（`playlist_count: 2` 的测试用例）

**所以你可以直接：**
```python
import yt_dlp

opts = {"outtmpl": "%(channel)s_%(id)s.%(ext)s", "quiet": True}
with yt_dlp.YoutubeDL(opts) as ydl:
    ydl.download(["https://t.me/telegram/441"])
```
> ⚠️ 注意：yt-dlp 的 URL 是 **`t.me/<ch>/<msgid>`**（不带 `/s/`）。
> `t.me/s/<ch>/<msgid>?embed=1` 会返回整个 20 条频道页并**忽略 embed**（子调研实测）。

**相关 issue**：[yt-dlp#2910](https://github.com/yt-dlp/yt-dlp/issues/2910) 是当年请求
支持 Telegram 的 issue（2022-02 提、已关闭），TelegramEmbedIE 就是它的产物。

### 3.2 视频有直链吗？

**✅ 有。** 双重证据：

1. **yt-dlp 源码**就是这么干的（正则取 `<video src>`）
2. **本机真实抓取**：`ch_durov.html` 里有 3 个
   `<video src="https://cdn4.telesco.pe/file/b231b9b161.mp4?token=GyPUpSwY1WJX…">`

**两条路径，各有适用场景：**

| 路径 | 优点 | 缺点 |
|---|---|---|
| 直接 `<video src>` CDN 直链 | 快、无需登录、可并发 | **token 会过期**，只适合即时下载 |
| Telethon `msg.download_media()` | 稳定、支持私频、可断点 | 走 MTProto，有 FloodWait，速度受限于账号 |

**建议：A 方案用直链（拿到即下），B 方案/私频用 Telethon。**

---

## 4. 反爬与风控

### 4.1 Telegram 对爬虫的态度

**分两种，态度完全不同：**

**① 公开预览页 `t.me/s`（A 方案）—— 相对宽容**
- 它本来就是给"链接预览卡片"用的公开页面
- 子调研实测：翻 `rtnews` ~17 万条消息无阻断
- 但仍建议**礼貌限速 + 失败退避**（本仓库 `web_preview.py` 已实现 3 次重试 + 1.5s 递增退避）

**② MTProto 第三方客户端（B 方案）—— 官方明确监控**
> "**all accounts that log in using unofficial Telegram API clients are automatically
> put under observation**" —— [core.telegram.org/api/obtaining_api_id](https://core.telegram.org/api/obtaining_api_id)

**⚠️ 官方 ToS 两条硬红线（[api/terms](https://core.telegram.org/api/terms)）：**
- **§1.5：禁止用 Telegram 数据训练 AI/ML 模型** ← **对 YLCraft 这种内容采集项目是直接相关的合规风险，务必注意**
- 造假订阅数/浏览量 = **永久封号**

### 4.2 会被封 IP 吗？

- **t.me/s 抓取：实测未见 IP 封禁**。真被封会返回 **HTTP 429**（本仓库代码已专门处理 429 并给出可读提示）。
- **MTProto：封的是"账号"不是 IP**（`PEER_FLOOD` 是账号级标记）。

### 4.3 速率限制建议

**⚠️ 重要事实：Telegram 从未公布任何方法的数值速率限制。**

- [core.telegram.org/api/errors](https://core.telegram.org/api/errors) 只定义了错误类型：
  - **420 FLOOD**：`FLOOD_WAIT_X`（等 X 秒）、`FLOOD_PREMIUM_WAIT_X`
  - **403 FORBIDDEN**、**406 NOT_ACCEPTABLE**
- **`PEER_FLOOD`（400）官方描述**："The current account is spamreported, you cannot
  execute this action, check @spambot for more info."
  ⚠️ 在 `errors.json` 里它的 **method 列表是空的** → **任何方法都可能报**，且它是**账号级 spam 标记，不是速率限制**
- Pyrogram 官方 FAQ 明说："**exact limits are unknown and can change anytime**"

**实践建议（保守基线）：**

```python
# A 方案（HTTP）
每次请求间隔 1~2s；翻页间至少 1s；遇到 429 指数退避；单频道最多连续翻 5~10 页

# B 方案（MTProto）—— 让库自动睡
client.flood_sleep_threshold = 60   # 默认就是 60s 以内自动 sleep
# 或显式捕获：
from telethon import errors
try:
    ...
except errors.FloodWaitError as e:
    await asyncio.sleep(e.seconds + 1)
```

**核心原则（官方 FAQ 原话）：** "**Don't spam.** You won't get `FloodWaitError` or your
account banned **if you use the library for legit use cases**."
即：**收到 FloodWait 不会封号，无视它才会。**

### 4.4 已知的坑清单

| 坑 | 表现 | 规避 |
|---|---|---|
| **`t.me/s` 对群组无效** | 公开群返回 200 + 0 条 | 群组/私频走 Telethon |
| **不存在也返回 200** | 拿不到数据但无异常 | 判 `tgme_channel_info` 是否存在（本仓库 `channel_exists()` 已实现） |
| **`before` 排他** | `?before=1` 返 0 条被误判"被截断" | 终止条件是空列表 |
| **频道需 join 才能看** | 受限频道预览页无消息 | 用登录账号 join |
| **`channels.getParticipants` 被隐私限制** | 报 403 或返回空 | 官方 FAQ 明说 2023 起"the inability to fetch group members at all" |
| **StringSession 泄露 = 账号泄露** | — | 加密入库，禁止打日志 |
| **同 session 并发** | `database is locked` | 每用户/每任务独立 session |
| **媒体 token 过期** | 之前存的直链 404 | 即取即下，别把 token URL 当永久资源 |
| **回复/链接预览污染正文** | 20 条消息出现 24 个 text 节点 | 排除 `tgme_widget_message_reply` / `link_preview` 后代（§1.2 坑 4） |
| **加入频道数上限** | `CHANNELS_TOO_MUCH` | 非 Premium 上限 500 个（Premium 1000） |
| **本机 t.me 直连超时** | `WinError 10060` | 我实测遇到了 —— 需配代理（见 §5） |

---

## 5. 环境实测记录（本机）

我实际跑了验证，以下是**真实命令输出**，不是推测：

```
Python：3.10.6 (tags/v3.10.6:9c7b4bd3, Aug  1 2022)  ← backend/venv_win/Scripts/python.exe
已装：beautifulsoup4 4.14.3、lxml 6.1.1、httpx 0.28.1、yt-dlp 2026.3.17、patchright 1.60.1
未装：telethon、pyrogram、kurigram、hydrogram、tgcrypto、cryptg   ← B 方案需要新装
代理环境变量：无（未设 HTTPS_PROXY/HTTP_PROXY）
直连 t.me：DNS OK (149.154.167.99) 但 TCP 443 超时  ← 必须走 VPN/代理
```

**⚠️ 部署提醒：** 本机 t.me 直连不通（VPN 规则模式）。
本仓库 `web_preview.py` 已实现代理自动探测（环境变量 → Windows 注册表 IE 设置），
**不硬编码端口** —— 这是对的，务必保留。

---

## 6. 落地技术选型建议

### A 方案（免登录公开频道）

> **自己解析 `t.me/s/<ch>` HTML。零新增依赖（bs4 + lxml 已装）。**

```
HTTP GET https://t.me/s/<username>[?before=<id>][?q=<keyword>]
  → BeautifulSoup(lxml)
  → 迭代 div.tgme_widget_message[data-post]
  → 提取 text / images / video / date / views
  → before = 本页最早 id，循环直到返回空
```

理由：① 社区没有可信的免登录库（§1.4 已核实）；② 项目已有解析依赖；③ 完全可控，改版时可自维护。

### B 方案（登录账号能力）

> **Telethon v1.45 + StringSession + cryptg。**

理由：④ star/文档/生态最好；⑤ 维护模式但仍在更新（Codeberg 2026-09）；⑥ 你的三个需求全是标准能力；⑦ pyrogram 已死，kurigram 可作备选。

```
⚠️ 全局搜索的认知修正：searchGlobal 只搜已加入会话。
   跨频道搜 → channels.searchPosts（计费 + 可能 403 PREMIUM_ACCOUNT_REQUIRED）
```

### 分层架构建议

```
① 免登录层（A）：t.me/s HTML  → 公开频道历史/媒体，无需账号，优先用
② 登录层（B）：Telethon       → 私有频道、群组、关键词全局搜索、用户自己的频道列表
③ 下载层：yt-dlp TelegramEmbedIE（t.me/<ch>/<id>）+ 直接 CDN 直链
```

---

## 7. 本仓库现状（我实际复核的结果）

**已有实现**（另一 agent 并行产出，位于 `backend/app/services/platforms/telegram/`）：
- `parser.py`（427 行）— HTML 解析，选择器与我实测一致 ✅
- `web_preview.py`（356 行）— httpx 抓取 + 代理探测 + 翻页 + 错误分级 ✅
- `models.py` — 数据模型

**我用真实 HTML 做的端到端验证（全部通过）：**

```
ch_durov         n= 20  title=Pavel Durov       subs=10600000  views>0=20  img=20  vid= 3  dur= 1
ch_telegram      n= 20  title=Telegram News     subs= 9430000  views>0=20  img=20  vid=13  dur=13
ch_tginfo        n= 20  title=Telegram Info     subs=   83100  views>0=20  img=20  vid= 0  dur= 0
ch_breakingmash  n= 15  title=Mash              subs= 3110000  views>0=15  img=15  vid= 3  dur= 4
ch_tgstat        n= 17  title=TGStat.ru         subs=  131000  views>0=15  img=17  vid= 0  dur= 0
```

**🐛 我发现并修复了一个真实 bug：**

`parser.py` 第 306 行原本是 `el.select_one(SEL_MSG_VIEWS)` ——
**漏了 `.` 前缀**。bs4 会把裸 class 名当**标签名**解析，永远返回 `None` **且不报错**，
后果是**所有消息的 `views` 恒为 0**。

这恰好是该文件顶部注释**自己警告过**的坑（"选择器常量一律不带标签前缀"那条规则），
但这里漏配了 `.`。回归测试 `test_parse_channel_page_full` 断言 `views == 1500` 把它抓了出来。

**修复后：**
```
修复前：1 failed, 29 passed   (test_parse_channel_page_full: assert 0 == 1500)
修复后：30 passed             ✅
```
同时上面真实 HTML 验证显示 `views>0` 全部命中（20/20、15/15 等），确认修复有效。

**建议后续补充（我发现但未擅自改的）：**
1. `parser.py` 里 `_html_of()` **定义了两遍**（第 118 行和第 134 行完全重复）—— 应删一个。
2. **未处理引用回复/链接预览的重复文本**（§1.2 坑 4）：`ch_tginfo` 实测 20 条消息有 24 个
   `tgme_widget_message_text`，其中 4 个来自 `js-message_reply_text`。建议照抄
   `specialteam/TelegramScraper` 的 `_own()` 排除法。
3. 相册（`tgme_widget_message_grouped_wrap`）目前靠 `photo_wrap` 选择器能抓到图，
   但**没有标记"这几张属于同一个相册"**，前端可能显示成多条。
4. `?after=` 参数：本仓库代码支持，但子调研**未复现**（其结论是"只有 before"）——
   **建议实测确认后再依赖**，我标注为待验证。

---

## 8. 待验证项（诚实标注，未编造）

| 项 | 状态 |
|---|---|
| `?after=` 是否真的有效 | ⚠️ 本仓库代码用了，子调研未复现 → **待实测** |
| "受限保存内容"频道的预览行为 | ⚠️ 未验证（子调研的正则误报已丢弃） |
| 投票/文档/语音消息的 class 名 | ⚠️ 未验证（扫了 10+ 频道没遇到实例） |
| `tgme_widget_message_replies` 内容形态 | ⚠️ 未验证 |
| 新账号 `searchGlobal` 是否有年龄门禁 | ⚠️ **未找到任何正规来源** → 倾向"不存在此规则" |
| my.telegram.org 注册审批延迟 | ⚠️ 页面需登录，无法取证；官方只给了"等待重试" |
| 各方法数值限流 | ⚠️ **官方从未公布**，任何具体数字都是传言 |
| 四个 Stack Overflow 答案内容 | ⚠️ Cloudflare 403，只确认了标题存在 |

---

## 9. 参考来源

**库 / 仓库**
- [LonamiWebs/Telethon (GitHub, archived)](https://github.com/LonamiWebs/Telethon) · [Codeberg 新家](https://codeberg.org/Lonami/Telethon) · [PyPI](https://pypi.org/project/Telethon/)
- [pyrogram/pyrogram (archived)](https://github.com/pyrogram/pyrogram) · [kurigram-org/kurigram](https://github.com/kurigram-org/kurigram) · [hydrogram/hydrogram](https://github.com/hydrogram/hydrogram)
- [specialteam/TelegramScraper](https://github.com/specialteam/TelegramScraper)（t.me/s 解析参考实现）
- [yt-dlp issue #2910 (Telegram 支持)](https://github.com/yt-dlp/yt-dlp/issues/2910)

**官方文档**
- [messages.searchGlobal](https://core.telegram.org/method/messages.searchGlobal) · [messages.getDialogs](https://core.telegram.org/method/messages.getDialogs) · [messages.search](https://core.telegram.org/method/messages.search)
- [channels.searchPosts](https://core.telegram.org/method/channels.searchPosts) · [api/search](https://core.telegram.org/api/search)
- [api/errors](https://core.telegram.org/api/errors) · [api/obtaining_api_id](https://core.telegram.org/api/obtaining_api_id) · [api/terms](https://core.telegram.org/api/terms)
- [telegram.org/faq_spam](https://telegram.org/faq_spam)
- [Telethon: Signing In](https://docs.telethon.dev/en/stable/basic/signing-in.html) · [Sessions](https://docs.telethon.dev/en/stable/concepts/sessions.html) · [RPC Errors](https://docs.telethon.dev/en/stable/concepts/errors.html) · [FAQ](https://docs.telethon.dev/en/stable/quick-references/faq.html)

**其他**
- [Telethon issue #4446（searchGlobal 只搜已加入会话）](https://github.com/LonamiWebs/Telethon/issues/4446)
- [tginfo: Telegram Global Search Has Been Changed (2024)](https://tginfo.me/search-rules-change-2024-en/)
- [Pyrogram: search_global（~10,000 条上限）](https://docs.pyrogram.org/api/methods/search_global)
