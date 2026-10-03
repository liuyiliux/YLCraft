"""YLCraft — Telegram 公开预览页（`t.me/s/<channel>`）解析。

## 为什么走 HTML 预览页

Telegram 没有"免登录关键词搜索"这回事，但**公开频道**有一个
网页预览页 `https://t.me/s/<username>`，不需要登录、不需要 API key，
直接返回最近若干条消息的 HTML。这是 A 方案的唯一可行路径。

## ⚠️ 关于选择器的可靠性

t.me 的 HTML 结构**不是公开契约**（Telegram 可以随时改），
所以这里的解析**必须容错**：选择器命中不了时返回空而不是抛异常，
并且把"页面结构可能变了"作为可读错误报出来
（本仓库铁律：不要静默返回空 —— 那会伪装成"这个频道没消息"）。

选择器来源：实测（见 `docs/platform/TELEGRAM_GUIDE.md`）+ 社区常见做法。
**每条选择器都在 docstring 里标注了它取什么**，改版时好定位。

## 消息结构（实测形态，2026-10-01）

    <div class="tgme_widget_message_wrap js-widget_message_wrap">
      <div class="tgme_widget_message text_not_supported_wrap js-widget_message"
           data-post="channelname/123" data-view="...">
        <div class="tgme_widget_message_user">  ← 头像/作者（频道页里通常空）
        <div class="tgme_widget_message_bubble">
          <a class="tgme_widget_message_photo_wrap" style="background-image:url('...')">
          <div class="tgme_widget_message_text js-message_text">正文…</div>
          <video src="..."> 或 <a class="tgme_widget_message_video_player">
          <span class="tgme_widget_message_views">1.2K</span>
          <time datetime="2026-01-01T00:00:00+00:00">
"""
from __future__ import annotations

import html as _html
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from .models import TelegramChannel, TelegramMessage

logger = logging.getLogger("ylcraft.platforms.telegram")

# ⚠️ **选择器常量一律不带标签前缀**（2026-10-01 踩到的 bug）
#
# 下面这些值会被 `f".{SEL_XXX}"` 拼成类选择器使用。
# 如果这里写成 `"div.tgme_widget_message_text"`，拼接后就是
# `".div.tgme_widget_message_text"` —— **不是合法 CSS**，
# `select_one` 永远返回 None，表现是"正文全空"（不报错！）。
# 所以统一只写 **class 名本身**。
SEL_CHANNEL_TITLE = "tgme_channel_info_header_title"
SEL_CHANNEL_DESC = "tgme_channel_info_description"
SEL_CHANNEL_COUNTER = "tgme_channel_info_counter"
SEL_CHANNEL_AVATAR = "tgme_page_photo_image"

# 消息容器（这个单独用，自带标签选择器，见 parse_messages）
SEL_MSG = "div.tgme_widget_message"
SEL_MSG_TEXT = "tgme_widget_message_text"
SEL_MSG_PHOTO = "a.tgme_widget_message_photo_wrap"
SEL_MSG_VIDEO = "video"
SEL_MSG_VIDEO_PLAYER = "a.tgme_widget_message_video_player"
SEL_MSG_TIME = "time"
SEL_MSG_VIEWS = "tgme_widget_message_views"
SEL_MSG_AUTHOR = "tgme_widget_message_author_name"
SEL_MSG_FORWARD = "tgme_widget_message_forwarded_from_name"


def _clone(el):
    """深拷贝一个 bs4 节点（用于"改了不影响原树"）。

    ## ⚠️ 为什么不能用 `copy.copy`（2026-10-01 踩到）

    第一版用 `copy.copy(el)`，结果**取回来的文本是空的** ——
    bs4 的 `Tag.__copy__` 只复制标签本身，**不带 children**
    （它是浅拷贝），所以 `get_text()` 拿到空串。
    表现为"每条消息的正文都是空"（而 HTML 里明明有文字），
    非常隐蔽 —— 因为不报错，只是内容没了。

    正确做法：用 `BeautifulSoup(str(el), "lxml")` 重新解析，
    得到一个**独立的树**。
    """
    from bs4 import BeautifulSoup

    try:
        return BeautifulSoup(str(el), "lxml")
    except Exception:
        return el


def _text_of(el) -> str:
    """把一段 HTML 转成**干净文本**。

    Telegram 的正文里有：
      · `<br>` 换行
      · `<a href>` 链接
      · `<i class="emoji" style="background-image:url(...)">` 表情（**要丢**，
        否则会混进一堆 CSS）
      · `<tg-spoiler>` 剧透（保留文字）
    """
    if el is None:
        return ""
    # 深拷贝后再改，避免污染原树（同一节点可能被多次取用）
    node = _clone(el)
    # 取回真正的根节点（BeautifulSoup 包装了一层）
    root = node.body if getattr(node, "body", None) is not None else node
    # emoji 是背景图实现，文本为空 —— 直接删掉更干净
    for emoji in root.select("i.emoji, .emoji"):
        emoji.decompose()
    # <br> 换成换行
    for br in root.find_all("br"):
        br.replace_with("\n")
    txt = root.get_text(separator="", strip=False)
    # HTML 实体已由 bs4 解好；这里只做空白规整
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()


def _html_of(el) -> str:
    """正文的 HTML（保留 <a>/<br>/emoji），供前端富文本渲染。

    ⚠️ 只取**内层** HTML（不要外层 div 本身）。
    """
    if el is None:
        return ""
    node = _clone(el)
    root = node.body if getattr(node, "body", None) is not None else node
    # 去掉脚本类残留（防御性）
    for bad in root.select("script, style"):
        bad.decompose()
    inner = root.decode_contents()
    return inner.strip()


def _photo_urls(msg_el) -> List[str]:
    """取消息里的图片直链。

    Telegram 用 `background-image: url('https://cdn...')` 实现图片，
    不是 `<img src>` —— 所以要正则从 style 里抠。
    多图 = 多个 `tgme_widget_message_photo_wrap` 元素。
    """
    urls: List[str] = []
    for a in msg_el.select(SEL_MSG_PHOTO):
        style = a.get("style") or ""
        m = re.search(r"url\(['\"]?([^'\")]+)['\"]?\)", style)
        if m:
            urls.append(m.group(1))
    # 兜底：有些形态是 <img src>
    for img in msg_el.select("img"):
        src = img.get("src") or ""
        if src.startswith("http") and src not in urls:
            urls.append(src)
    return urls


def _video_info(msg_el) -> Tuple[str, str, int]:
    """取 (视频直链, 封面, 时长秒)。

    ## ⚠️ 更正：公开页面**能**拿到视频直链（2026-10-01）

    我最初以为"Telegram 视频是分片流，预览页拿不到直链"——**这是错的**。
    读了 yt-dlp 自带的 `extractor/telegram.py`（`TelegramEmbedIE`）后确认：
    它就是从页面里正则取 `<video src="...">` 作为直链，
    且 `_TESTS` 里有可下载的测试样本（md5 校验通过）。

    所以这里如实取 `<video src>`；只有一个例外：
    `src` 是 `blob:` / `data:` 时不是真直链（那种情况留空，
    由上层用 yt-dlp 走 `t.me/ch/msgid` 下载）。

    封面：`tgme_widget_message_video_thumb` 的 `background-image`。
    """
    video = ""
    cover = ""
    duration = 0

    v = msg_el.select_one(SEL_MSG_VIDEO)
    if v is not None:
        src = v.get("src") or ""
        # blob:/data: 不是可下载的直链（页面用 JS 拼流的情况）
        if src.startswith("http"):
            video = src
        cover = v.get("poster") or ""

    player = msg_el.select_one(SEL_MSG_VIDEO_PLAYER)
    if player is not None:
        if not cover:
            style = player.get("style") or ""
            m = re.search(r"url\(['\"]?([^'\")]+)['\"]?\)", style)
            if m:
                cover = m.group(1)
        # 时长：<time class="message_video_duration">1:23</time>
        # ⚠️ yt-dlp 用的选择器是 `<time[^>]+duration[^>]*>`，
        # 说明时长元素是 `<time>` 且带 duration class（不是 span）
        dur = player.select_one("time[class*=duration], .message_video_duration")
        if dur:
            duration = _parse_duration(dur.get_text(strip=True))

    # 兜底：单独找 video_thumb 元素（yt-dlp 提到这个 class）
    if not cover:
        thumb = msg_el.select_one(".tgme_widget_message_video_thumb")
        if thumb is not None:
            style = thumb.get("style") or ""
            m = re.search(r"url\(['\"]?([^'\")]+)['\"]?\)", style)
            if m:
                cover = m.group(1)

    return video, cover, duration


def _parse_duration(s: str) -> int:
    """'1:23' / '1:02:03' → 秒。解析不出返回 0（不猜）。"""
    if not s:
        return 0
    parts = s.strip().split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return 0
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    return 0


def _parse_views(s: str) -> int:
    """'1.2K' / '3.4M' / '123' → 整数。解析不出返回 0。"""
    if not s:
        return 0
    s = s.strip().replace(",", "").replace(" ", "")
    m = re.match(r"^([\d.]+)\s*([KkMmBb]?)$", s)
    if not m:
        # 有的带单位后缀（"1.2K views"）
        m = re.match(r"^([\d.]+)\s*([KkMmBb])", s)
        if not m:
            return 0
    num = float(m.group(1))
    unit = (m.group(2) or "").upper()
    mult = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[unit]
    return int(num * mult)


def parse_channel_info(soup) -> TelegramChannel:
    """解析频道页头（`tgme_channel_info` 区域）。"""
    ch = TelegramChannel(source="web_preview")

    el = soup.select_one(f".{SEL_CHANNEL_TITLE}")
    if el:
        ch.title = el.get_text(strip=True)

    el = soup.select_one(f".{SEL_CHANNEL_DESC}")
    if el:
        ch.description = _text_of(el)

    # 订阅数：counters 区域里 "subscribers" 那一项
    for counter in soup.select(f".{SEL_CHANNEL_COUNTER}"):
        label = (counter.select_one(".counter_type") or counter)
        label_txt = label.get_text(strip=True).lower()
        if "subscriber" in label_txt or "member" in label_txt:
            val = counter.select_one(".counter_value")
            if val:
                ch.subscribers = _parse_views(val.get_text(strip=True))
            break

    img = soup.select_one(f".{SEL_CHANNEL_AVATAR}")
    if img and (img.get("src") or "").startswith("http"):
        ch.avatar = img["src"]

    return ch


def parse_messages(soup) -> List[TelegramMessage]:
    """解析页面里的全部消息。"""
    out: List[TelegramMessage] = []
    for el in soup.select(SEL_MSG):
        post = el.get("data-post") or ""
        # data-post 形如 "channelname/123"
        if "/" in post:
            channel, mid = post.rsplit("/", 1)
        else:
            channel, mid = "", post
        if not mid:
            continue

        text_el = el.select_one(f".{SEL_MSG_TEXT}")
        video, cover, duration = _video_info(el)

        t = el.select_one(SEL_MSG_TIME)
        date = (t.get("datetime") or "") if t else ""

        # ⚠️ **必须带 `.` 前缀**（2026-10-01 实测又踩到这个坑）
        #
        # `SEL_MSG_VIEWS` 是**裸 class 名**（"tgme_widget_message_views"）。
        # `select_one("tgme_widget_message_views")` 会被 bs4 当成**标签名**，
        # 永远匹配不到、返回 None、**且不报错** —— 后果是
        # **所有消息的 views 恒为 0**。
        #
        # 这正是本文件顶部警告的"裸 class 名必须配 `.`"规则；
        # 此处之前漏了点号，是回归测试 `test_parse_channel_page_full`
        # （断言 `views == 1500`）把它抓出来的。
        v = el.select_one(f".{SEL_MSG_VIEWS}")
        views = _parse_views(v.get_text(strip=True)) if v else 0

        author = ""
        a = el.select_one(f".{SEL_MSG_AUTHOR}")
        if a:
            author = a.get_text(strip=True)

        fwd = ""
        f = el.select_one(f".{SEL_MSG_FORWARD}")
        if f:
            fwd = f.get_text(strip=True)

        links = [
            h for h in (
                a.get("href") for a in (text_el.select("a") if text_el else [])
            ) if h and h.startswith("http")
        ]

        out.append(TelegramMessage(
            id=mid,
            channel=channel,
            channel_title=author,
            text=_text_of(text_el),
            html=_html_of(text_el),
            date=date,
            views=views,
            images=_photo_urls(el),
            video=video,
            video_cover=cover,
            duration=duration,
            forward_from=fwd,
            links=links,
        ))
    return out


def parse_channel_page(html: str) -> Tuple[TelegramChannel, List[TelegramMessage]]:
    """解析 `t.me/s/<channel>` 整页。

    返回 `(频道信息, 消息列表)`。

    ⚠️ **解析不出消息时不要当成"频道没消息"** ——
    调用方要结合"页面里有没有 tgme_widget_message 容器"判断：
    完全没有容器通常意味着**页面结构变了**（Telegram 改版），
    而不是频道为空。见 `detect_structure_change()`。
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "lxml")
    return parse_channel_info(soup), parse_messages(soup)


def detect_structure_change(html: str) -> Optional[str]:
    """判断页面为什么没有消息。

    返回 None 表示结构正常；返回字符串表示**可读原因**。

    ## 为什么要这个（本仓库铁律）

    "静默返回空"会把"解析器失效"伪装成"这个频道没有内容" ——
    用户会以为频道是空的，而真相是我们的选择器过期了。
    这两种情况**必须区分**。

    ## ⚠️ 实测（2026-10-01）：频道不存在返回的是 **HTTP 200**

    不是 404！而是 telegram.org 的**主页壳**（~19KB，零个 tgme_* 元素），
    `<title>` 是 "Telegram – a new era of messaging"。
    所以**必须靠页面内容判断**，不能看状态码。

    四种"拿不到内容"的形态（实测已覆盖，特征**互斥**）：

    | 形态 | 特征标志 | 实测样本 |
    |---|---|---|
    | 正常频道页（有网页消息） | `tgme_channel_info` + `tgme_widget_message` | `durov`（145601B，20 条消息）|
    | 不存在 / 私有邀请 | telegram.org 主页壳（无 tgme_*） | `美女`（中文，19854B）|
    | 普通用户账号 | `tgme_username` / `Contact @xxx` | `zzz_nonexist_9x8k2`（9744B）|
    | **频道存在但无网页消息** | `tgme_page_title` + `Preview channel` | **`kshelfs`（12313B，真实频道）** |
    | 真·改版 | 有 `tgme_channel_history` 但无消息容器 | — |

    ⚠️ 第三种是 2026-10-03 补的：`kshelfs`（涩涩深夜研讨会，5032 订阅者）
    真实存在，但 `t.me/s` 只给「Download / Preview channel」页，
    **零个 `tgme_channel_info`/`tgme_widget_message`**。
    原来落进"主页壳"分支，被误报成"Telegram 改了页面结构"——
    把"平台没开放"说成"我们的解析器坏了"，方向完全反了。
    """
    if not html:
        return "页面内容为空（网络或代理问题？）"

    low = html.lower()
    has_history = "tgme_channel_history" in low or "tgme_channel_info" in low
    has_msg = "tgme_widget_message" in low

    if has_msg:
        return None

    # 有频道外壳但没消息 —— 可能是新频道/被清空
    if has_history:
        return (
            "该频道页面存在，但没有任何消息容器（tgme_widget_message）。"
            "可能：① 频道刚创建还没有消息；② 频道消息未被网页预览收录；"
            "③ Telegram 改了页面结构（解析器需更新）。"
        )

    # ⚠️ **第四种形态：频道真实存在，但 Telegram 只给了"查看"预览页**
    # （2026-10-03 实测 @kshelfs 发现）
    #
    #     kshelfs（涩涩深夜研讨会，5032 订阅者，**真实存在**）
    #       → <title>Telegram: View @kshelfs</title>   12313 字节
    #       → 页面写着 "Preview channel … If you have Telegram,
    #          you can view and join … right away."
    #       → **没有** tgme_channel_info / tgme_widget_message
    #
    # 我原来把它归到"主页壳"分支，报错说"Telegram 改了页面结构
    # （解析器需要更新）" —— **误导**：频道好好的，是 Telegram 对这类
    # 频道不开放网页端消息列表。
    #
    # 判据（实测四类页面特征互斥，见下表）：
    #
    #   正常频道页   tgme_channel_info + tgme_widget_message
    #   仅预览页     tgme_page_title + "preview channel"
    #   用户名不存在  tgme_username
    #   telegram.org 主页壳  以上都没有
    #
    # 所以这里能**确定**地说"频道存在但内容没开放"，而不是猜。
    if "tgme_page_title" in low and ("preview channel" in low or "tgme_page_extra" in low):
        return (
            "这个频道**存在**，但 Telegram **没有开放网页端的消息列表**。\n"
            "（实测 @kshelfs 就是这种：频道是「涩涩深夜研讨会」，"
            "5032 名订阅者，但 t.me/s 只给一个「Download / Preview channel」页）\n"
            "能做的：\n"
            "  1. **去客户端看**（Telegram App / Desktop 都能看）\n"
            "  2. 在**应用里登录 Telegram**后用「我的频道」读取 —— "
            "登录走 MTProto，不受这个网页端限制\n"
            "  3. 如果该频道只是**禁止匿名预览**，等 Telegram 放开"
        )

    # 主页壳 / 联系人页 —— 频道不存在或不是频道
    #
    # ⚠️ **实测：这两种情况 Telegram 返回的页面几乎一样**
    # （都是 `<title>Telegram: Contact @xxx</title>`，~9.6KB，零 tgme_*）：
    #     thischanneldoesnotexist999xyz → Contact @thischanneldoesnotexist999xyz
    #     sedlyachok（真实用户）        → Contact @sedlyachok
    # **无法从 HTML 区分**，所以文案要把两种可能都列出来，
    # 不能假装能判断是哪一种（那会误导用户去改一个没拼错的名字）。
    if "contact @" in low or "tgme_username" in low:
        return (
            "拿不到该地址的频道内容。Telegram 对以下情况返回的页面**一样**，"
            "无法进一步区分，请逐一排查：\n"
            "  1. **用户名拼错了**（检查大小写和拼写）\n"
            "  2. 该地址是**用户账号**，不是频道"
            "（t.me/s 的公开预览只对频道有效）\n"
            "  3. 这是**私有频道**，公开预览看不了（需登录后读取）\n"
            "  4. **输入的是频道标题而非 username**（如「美女」）——\n"
            "     频道 username 只允许英文字母/数字/下划线，**不能是中文**。\n"
            "     在 Telegram 客户端里能用中文搜到频道，那搜的是**标题**，\n"
            "     走的是另一条路径、不经过 t.me 链接 —— 本工具只吃 username。\n"
            "     正确做法：在客户端打开该频道 → 复制链接 → 形如 https://t.me/xxx"
        )
    return (
        "拿不到这个地址的内容。**如果你输入的是频道标题**"
        "（中文、emoji、带空格的），那必然是这个结果：\n"
        "  · 频道 username **只允许英文字母/数字/下划线，不能是中文**\n"
        "  · 客户端里能用中文搜到频道，那搜的是**标题**，不经过 t.me 链接\n"
        "  · 本工具只吃 username —— 请复制频道链接（形如 https://t.me/xxx）\n"
        "若确认是英文 username，则可能是："
        "① 该地址不是频道（是用户账号）；② 私有频道；"
        "③ Telegram 改了页面结构（解析器需更新）。"
    )


def parse_single_message(html: str) -> Optional[TelegramMessage]:
    """解析**单条消息**页面。

    用途：`https://t.me/<channel>/<msg_id>?embed=1` ——
    ⚠️ **这条路径是 yt-dlp 用的**（见 `extractor/telegram.py::
    TelegramEmbedIE._real_extract`，它请求 `?embed=1&single`）。

    为什么需要它：频道页（`/s/`）只给最近约 20 条，
    而**单条 embed 页能拿到任意历史消息**（只要知道 id）。
    而且 embed 页里的 `<video src>` 直链更完整。

    没有消息时返回 None（调用方据此报"消息不存在/已删除"）。
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "lxml")
    msgs = parse_messages(soup)
    if msgs:
        return msgs[0]

    # embed 页的结构略有不同：没有 data-post 时用 time/正文兜底
    text_el = soup.select_one(f".{SEL_MSG_TEXT}")
    video, cover, duration = _video_info(soup)
    if text_el is None and not video and not cover:
        return None

    t = soup.select_one(SEL_MSG_TIME)
    author = soup.select_one(".tgme_widget_message_author, .tgme_widget_message_author_name")
    return TelegramMessage(
        text=_text_of(text_el),
        html=_html_of(text_el),
        date=(t.get("datetime") or "") if t else "",
        images=_photo_urls(soup),
        video=video,
        video_cover=cover,
        duration=duration,
        channel_title=author.get_text(strip=True) if author else "",
    )
