"""YLCraft — 微博搜索**纯 HTTP**（httpx 直连 `s.weibo.com`）。

## 为什么不需要浏览器（2026-10-06 实测推翻旧结论）

我先前两次断言"微博搜索必须开浏览器"，都是**测试方法错了**。

第一次（10-04）用的是移动版 `m.weibo.cn` 的 JSON 接口，它的 `page`
参数翻不动 —— 那是我选错了端点，不是平台限制。

第二次（10-06）我给 `s.weibo.com` 的**网页请求**加了接口用的头：

    'x-requested-with': 'XMLHttpRequest'      ← ⚠️ 就是这个

加上它，微博直接返回"页面不存在"：

    → https://weibo.com/sorry?pagenotfound&retcode=6102

我拿这个被踢的结果下了结论"直连不行"，还**写进了代码注释当实测结论**，
于是白开了几天浏览器（每次搜索 ~15 秒 + 250MB 内存）。

⚠️ **网页请求不能带 `x-requested-with`** —— 那是给 AJAX/JSON 接口用的。
把它加到普通页面请求上，微博会认为你在用错误的姿势访问。

### 去掉那个头之后（实测 2026-10-06）

    page=1   1.0 秒  22 张卡片
    page=2   0.4 秒  10 张
    page=3   0.5 秒   9 张
    page=10  0.4 秒  10 张
    page=50  0.4 秒  10 张
    页与页重叠 = **0**（真翻页）

⇒ **15 秒 → 0.4~1 秒**，且不需要开浏览器。

## ⚠️ 必须登录

用库里那份 cookie 直连实测：

    GET https://s.weibo.com/weibo?q=沈阳   → 200，18万字节，30 个 card-wrap

被踢到访客页的情形是 `passport.weibo.com/visitor/visitor`。

## 总页数

HTML 里写着 **「共50页」**（`共\\s*(\\d+)\\s*页`）。

⚠️ 实测它**不是写死的模板文字**，是真的上限：

    沈阳 / 美食 / 北京   都说「共50页」（都超 500 条了）
    不存在的词            没有「共X页」，卡片 0 个
    请求 page=51         仍说「共50页」，但**弹回第 1 页**（22 张卡片）

⇒ 可以直接告诉用户"共 50 页"，不用再翻到空页才发现。

## 浏览器路径还在

`search_patchright.py` 保留为**兜底**：直连被限流/改版时自动退回。
不是删掉，是多一条路。
"""
from __future__ import annotations

import html as _html_mod
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

logger = logging.getLogger("ylcraft.platforms.weibo.http")

# ⚠️⚠️ 微博桌面版的分类**不在同一个地址下**（2026-10-07 从页面自己的
# 标签 href 读出来的，**不是猜的**）：
#
#     综合  /weibo?q=沈阳&Refer=weibo_weibo
#     热门  /weibo?q=沈阳&xsort=hot&Refer=hotmore
#     实时  /realtime?q=沈阳&rd=realtime&tw=realtime     ← **另一个页面**！
#     视频  /video?q=沈阳&xsort=hot&hasvideo=1&tw=video
#     图片  /pic?q=沈阳
#     用户  /user?q=沈阳
#     话题  /topic?q=沈阳&pagetype=topic&topic=1
#
# ⚠️⚠️ **我之前把「实时」当成不存在，删掉了 —— 那个结论是错的。**
#    当时只看了 `/weibo?q=` 上有没有实时分类，看不到就说"桌面版没有实时"。
#    实际上它就在 `/realtime` 这个另一个页面上（用户截图直接指出来了）。
#
# ⇒ 所以这些**不能**只用 `xsort` 区分，必须按 `path` 分开取。
DESKTOP_SEARCH_URL = "https://s.weibo.com/weibo?q={keyword}&page={page}"

#: 前端 search_type → (页面路径, 附加查询串)
#:
#: ⚠️ 「热门」不是按点赞数排的（实测 xsort=hot 返回 515, 467, 1142, 8992…）
#:    —— 是微博自己的热度榜，**不要在前端按点赞重排**，那会与官方不一致。
DESKTOP_PATHS: Dict[str, Tuple[str, str]] = {
    "note":     ("weibo",     ""),                 # 综合
    "all":      ("weibo",     ""),
    "default":  ("weibo",     ""),
    "popular":  ("weibo",     "&xsort=hot"),      # 热门
    "hot":      ("weibo",     "&xsort=hot"),
    "realtime": ("realtime",  "&rd=realtime&tw=realtime"),
    "video":    ("video",     "&xsort=hot&hasvideo=1&tw=video"),
    # ⚠️ 「图片」**故意不放进来**（2026-10-07 实测后不提供）。
    #
    # `/pic` 页面能返回 200 且有 20 个 `mid`，但它是**纯瀑布流**：
    #     div.card-wrap = 0    .txt = 0    .from = 0
    # mid 全部挂在 `<img>` 上，**没有任何文案/作者/时间/计数**。
    # ⇒ 现有解析器一条都取不出来，返回 0 条。
    #
    # 给一个只会返回 0 条的 tab = **假选项**（标签写着"图片"，
    # 点了什么都没有），比没有更糟 —— 和之前误删「实时」是同一类错误的反面。
    # ⇒ 要支持得单独写一套瀑布流解析（至少要能拿到 alt/作者），
    #    在那之前**不提供这个 tab**。
}

# 实测上限（第 50 页仍有内容，page=51 会被弹回第 1 页）
MAX_PAGE = 50

# 实测每页 10 条（第 1 页有 22 个 card-wrap，前几个是"热搜/推广"，不是结果）
PAGE_SIZE = 10

# ⚠️⚠️ **绝对不能**加 `x-requested-with: XMLHttpRequest`
#
# 那是给 JSON/AJAX 接口用的头。**加到普通网页请求上，微博会拒绝**：
#
#     GET s.weibo.com/weibo?q=沈阳   （带 XHR 头）
#     → https://weibo.com/sorry?pagenotfound&retcode=6102   卡片 0 个
#
#     GET s.weibo.com/weibo?q=沈阳   （不带）
#     → 200，18万字节，卡片 30 个      ✅
#
# 我因为加了这个头，误判"直连不行"好几天，每次搜索白开浏览器。
BASE_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "zh-CN,zh;q=0.9",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
    ),
}

# 「共50页」
RE_TOTAL_PAGES = re.compile(r"共\s*(\d+)\s*页")
# 卡片容器。⚠️ 属性顺序是 action-type → mid → class，**不能假设顺序**：
#     <div action-type="feed_list_item" mid="535..." class="card-wrap">
RE_CARD_START = re.compile(r'<div[^>]*class="card-wrap"[^>]*>')
RE_MID = re.compile(r'mid="(\d+)"')
RE_TXT = re.compile(r'class="txt"[^>]*>(.*?)</p>', re.S)
RE_NAME = re.compile(r'<a[^>]*class="name"[^>]*>(.*?)</a>', re.S)
RE_USER_HREF = re.compile(r'href="//weibo\.com/(\d{6,})')
RE_IMG = re.compile(r'(https://tvax\d\.sinaimg\.cn/[^"\']+)')
RE_CARD_ACT = re.compile(r'<div class="card-act">(.*?)</ul>', re.S)
RE_LI = re.compile(r"<li[^>]*>(.*?)</li>", re.S)
# ⚠️ 发布时间 + 发布来源，例如：
#     `10月06日 15:50  来自 iPhone客户端`
#     不抓它 ⇒ 前端「发布时间」列永远是 `-`（真 bug，2026-10-07 修）。
#
# ⚠️⚠️ 结束标签必须是 `</div>`，**不是 `</span>`**（2026-10-07 实测）：
#     <div class="from">
#       <a href="//weibo.com/6079887320/RikziB9zF?...">\n 09月16日 08:26\n</a>
#        &nbsp;来自 <a href="//weibo.com/" rel="nofollow">iPhone 15 Pro Max</a>
#     </div>
#     第一版我按 `</span>` 写 → 一条都匹配不到 → 时间继续全丢。
RE_FROM = re.compile(r'class="from"[^>]*>(.*?)</div>', re.S)
# ⚠️⚠️ `.from` 的时间**不止一种写法**（2026-10-07 浏览器实测，三种都真实存在）：
#
#     ① `10月06日 15:50`                     —— 最常见
#     ② `今天08:07`                          —— 当天的，**没有月日**！
#     ③ `2025年09月16日 08:26`               —— 跨年才带年份
#
#     ② 是第一版漏掉的：只写了 ①③ 的正则，于是"今天"的微博时间全丢
#     （实测第 2 页 9 条里丢了 5 条 —— 那 5 条恰好全是今天发的）。
#
# 另外 `.from` 里还会插话，比如：
#     `今天 03:55 转赞人数超过40`  /  `10月06日 12:50 转赞人数超过200`
# ⇒ 时间用"按位置取"而不是"匹配到就停"，插在中间也不影响。
RE_FROM_TIME = re.compile(
    r"(\d{4}年)?\s*(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2})")
# `今天08:07` / `昨天 21:30` —— 没有月日，需要按"今天/昨天"反推
RE_FROM_TODAY = re.compile(r"(今天|昨天|前天)\s*(\d{1,2}):(\d{2})")
# ⚠️⚠️ **实时页**的时间格式**又不一样**（2026-10-07 实测 s.weibo.com/realtime）：
#
#     9秒前 / 30秒前 / 1分钟前 / 3分钟前 / 6分钟前
#
# `RE_FROM_TODAY` 匹配不到这些（没有 HH:MM），第一版会把实时的时间全丢成空。
RE_FROM_AGO = re.compile(r"(\d+)\s*(秒|分钟|分|小时|天)前")
RE_VIDEO = re.compile(r"video\.weibo\.com|\.media-video")
RE_NUM = re.compile(r"[\d.]+\s*[万亿]?")
# ⚠️ 必须先删注释 —— `.card-act` 里有一段被注释掉的 <li>（"收藏"），
#    不删会让三个计数整体错位（见 `_parse_counts`）。
RE_COMMENT = re.compile(r"<!--.*?-->", re.S)


class WeiboLoginRequired(RuntimeError):
    """直连被踢到访客页 / 登录页 —— 调用方据此提示用户补登录态。

    与「关键词没内容」**必须分开**：前者要用户去账号中心，
    后者只是白搜一场。
    """


def _clean(html_fragment: str) -> str:
    """去标签 + 压空白。"""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html_fragment)).strip()


def _unescape(text: str) -> str:
    """还原 HTML 实体（`&amp;` `&#39;` …），并去掉微博特有的零宽字符。"""
    out = _html_mod.unescape(text or "")
    # 微博正文末尾常带 U+200B，用户看到是空方块
    return out.replace("\u200b", "").strip()


def _parse_from(seg: str) -> Dict[str, Any]:
    """从卡片片段里取发布时间 + 发布来源。

    `.from` 里的文本**有三种写法**（2026-10-07 浏览器实测，都真实出现）：

        ① `10月06日 15:50  来自 iPhone客户端`
        ② `今天08:07  来自 季肖冰超话`      ← **没有月日**
        ③ `2025年09月16日 08:26  来自 iPhone` ← 跨年才带年份

        中间还可能插话：`今天 03:55 转赞人数超过40`

    返回 `{"create_time": "<秒时间戳字符串>", "source": "<设备名>"}`，
    抓不到就返回 `{"create_time": "", "source": ""}` —— **不编**。

    ## 为什么非转成时间戳

    `.from` 基本**没有年份**，而且 ② 连月日都没有。
    直接把 `"10月06日 15:50"` 丢给前端 `new Date()`，浏览器会按
    **2001 年**兜底 → 显示"24 年前"。

    ⇒ 缺年份时取「**不晚于今天**」的最近一年（微博按时间倒序，
       不会给未来内容）；② 用「今天/昨天」直接反推。
       这是有依据的推断，不是随手猜的常量。
    """
    m = RE_FROM.search(seg or "")
    if not m:
        return {"create_time": "", "source": ""}

    raw = _unescape(_clean(m.group(1)))
    if not raw:
        return {"create_time": "", "source": ""}

    # 来源 = 「来自」后面的设备/应用名。⚠️ 有的卡片没有「来自」，
    #    那就整段都是时间，别把时间当来源。
    source = ""
    sm = re.search(r"来自\s*(.+)$", raw)
    if sm:
        source = sm.group(1).strip()

    now = datetime.now()
    target: Optional[datetime] = None

    tm = RE_FROM_TIME.search(raw)
    if tm:
        year = int(tm.group(1)[:-1]) if tm.group(1) else 0
        month, day, hour, minute = (
            int(tm.group(2)), int(tm.group(3)),
            int(tm.group(4)), int(tm.group(5)),
        )
        if 1 <= month <= 12 and 1 <= day <= 31 and hour <= 23 and minute <= 59:
            if not year:
                year = now.year
            try:
                candidate = datetime(year, month, day, hour, minute)
            except ValueError:      # 2 月 29 日这类
                candidate = None
            if candidate is not None and not tm.group(1):
                # 补出来的年份让时间跑到未来 ⇒ 说明是去年的，取上一年
                if candidate > now:
                    try:
                        candidate = datetime(
                            year - 1, month, day, hour, minute)
                    except ValueError:
                        candidate = None
            target = candidate

    if target is None:
        # ② `今天08:07` / `昨天21:30` —— 按今天/昨天反推
        rm = RE_FROM_TODAY.search(raw)
        if rm:
            days_back = {"今天": 0, "昨天": 1, "前天": 2}.get(rm.group(1), 0)
            hour, minute = int(rm.group(2)), int(rm.group(3))
            if hour <= 23 and minute <= 59:
                base = now - timedelta(days=days_back)
                try:
                    target = base.replace(
                        hour=hour, minute=minute, second=0, microsecond=0)
                except ValueError:
                    target = None

    if target is None:
        # ③ `9秒前` / `3分钟前` —— **实时页**的格式（见 RE_FROM_AGO）
        am = RE_FROM_AGO.search(raw)
        if am:
            n = int(am.group(1))
            unit = am.group(2)
            secs = {"秒": 1, "分": 60, "分钟": 60, "小时": 3600, "天": 86400}[unit]
            target = now - timedelta(seconds=n * secs)

    if target is None:
        # 只有文本、没有可解析的时间 → 如实留空，别塞个假时间进去
        return {"create_time": "", "source": source}

    return {"create_time": str(int(target.timestamp())), "source": source}


def _pretty_time(ts: str) -> str:
    """时间戳 → `10月06日 15:50`（微博 `.from` 的原格式）。

    转不出来就返回空串 —— 宁可没有来源名，也不要写一个错的。
    """
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%m月%d日 %H:%M")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def _to_int(li_html: str) -> int:
    """从一个 `<li>` 片段里取计数。

    ⚠️⚠️ **必须先去标签再找数字**（2026-10-06 实测踩到）：

    每个 `<li>` 的 `<a>` 属性里塞满了 `mid=5350578936875316`、`uid=…`，
    直接在原始 HTML 里找数字会**先撞上那个 mid**，把 535 万当成点赞数
    （实测：赞显示成 `5350578936875316`）。

    ⇒ 先 `_clean()` 剥掉所有标签只剩可见文字，再找数字。
       可见文字形如 `转发` / `1` / `1.2万`。

    ⚠️ 微博实测只用 **万/亿** 两种单位。没验证过的单位**不换算** ——
    猜错显示成 "3" 无所谓，猜错显示成 "3000" 就是编数据。
    拿不到数字（空串、"转发"）一律给 0，**绝不编**。
    """
    text = _clean(li_html)
    m = RE_NUM.search(text)
    if not m:
        return 0
    raw = m.group(0).replace(" ", "")
    mult = 1
    if raw.endswith("万"):
        mult, raw = 10_000, raw[:-1]
    elif raw.endswith("亿"):
        mult, raw = 100_000_000, raw[:-1]
    try:
        return int(float(raw) * mult)
    except ValueError:
        return 0


def _parse_counts(seg: str) -> Tuple[int, int, int]:
    """从 `.card-act` 里取 (转发, 评论, 点赞)。

    ⚠️ 顺序是**实测**的：DOM 里恒为 转发 → 评论 → 点赞，
    且 `.card-act > ul > li` 恒为 3 个。

    ⚠️⚠️ **必须先删 HTML 注释**（2026-10-06 实测踩到）：
       `.card-act` 里有一段被注释掉的"收藏"按钮：

           <!--                <li><a ...>收藏</a></li>-->

       不删掉的话它会被当成**第 1 个 li**，导致
       `['收藏', '转发', '1', '2']` —— 位置整体错一位，
       转发/评论/点赞全部读错。删掉后才是干净的 3 个。

    ⚠️⚠️ **必须按位置取，不能按"哪些像数字"过滤**（更早一版就是这么错的）：
       转发为 0 时第一个 li 的文本是**文字"转发"**而不是 "0"，
       数字过滤会把整行筛掉 → 三个计数错位、全部变成 0。

    ⚠️ 推广位卡片的 `.card-act` 实测只有 2 个数字 ——
       拿不到就给 0，**不补位、不猜**。
    """
    act = RE_CARD_ACT.search(seg)
    if not act:
        return 0, 0, 0
    inner = RE_COMMENT.sub("", act.group(1))
    lis = RE_LI.findall(inner)
    nums = [_to_int(li) for li in lis[:3]]
    while len(nums) < 3:
        nums.append(0)
    return nums[0], nums[1], nums[2]


def parse_cards(html: str) -> List[Dict[str, Any]]:
    """把一页 HTML 拆成结果卡片。

    ⚠️ 只取**带 mid 的**卡片 —— 那是内容微博；
       "热搜榜""精选专题""推广位"没有 mid（实测第 1 页 22 个 card-wrap
       里只有 20 个带 mid）。
    """
    starts = [m.start() for m in RE_CARD_START.finditer(html)]
    out: List[Dict[str, Any]] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(html)
        seg = html[start:end]

        mid_m = RE_MID.search(seg)
        if not mid_m:
            continue
        mid = mid_m.group(1)

        txt_m = RE_TXT.search(seg)
        text = _unescape(_clean(txt_m.group(1))) if txt_m else ""
        if not text:
            continue

        name_m = RE_NAME.search(seg)
        href_m = RE_USER_HREF.search(seg)
        img_m = RE_IMG.search(seg)
        repost, comment, like = _parse_counts(seg)
        info = _parse_from(seg)

        out.append({
            "mid": mid,
            "text": text,
            "user": _clean(name_m.group(1)) if name_m else "",
            "user_id": href_m.group(1) if href_m else "",
            "img": img_m.group(1) if img_m else "",
            "is_video": bool(RE_VIDEO.search(seg)),
            "repost": repost,
            "comment": comment,
            "like": like,
            "create_time": info["create_time"],
            "source": info["source"],
        })
    return out


def parse_total_pages(html: str) -> Optional[int]:
    """读「共50页」。

    ⚠️ 没有这个文字时返回 `None`（**不猜**）——
       调用方据此说"不知道有几页"，而不是编一个数字出来。
    """
    m = RE_TOTAL_PAGES.search(html or "")
    if not m:
        return None
    try:
        return max(1, min(int(m.group(1)), MAX_PAGE))
    except (TypeError, ValueError):
        return None


def to_search_result(card: Dict[str, Any]) -> Any:
    """卡片 → 统一的 `SearchResult`。

    ⚠️ 复用 `search_desktop.parse_desktop_card`（不是 `client`）——
       我第一版写成 `from .client import parse_desktop_card`，
       那个函数在 `search_desktop` 里 → ImportError → 直连**静默失败**
       → 回退到浏览器，表现为"改了没效果、还是 15 秒"。

       ⚠️ 而且它是被 `except Exception` 吞掉的，只在日志里一行
       `[weibo] 直连失败（ImportError: ...）` —— 不主动查根本发现不了。
    """
    from .search_desktop import parse_desktop_card

    create_time = str(card.get("create_time") or "")
    source = str(card.get("source") or "")

    return parse_desktop_card({
        "mid": card.get("mid"),
        "text": card.get("text"),
        "user": card.get("user"),
        "userHref": "//weibo.com/%s" % card.get("user_id", ""),
        # ⚠️ 这里以前硬编码 `from: ""`，于是 `_parse_from()` 解析出来的
        #    发布时间被**原样丢掉** → 前端「发布时间」列永远显示 `-`
        #    （2026-10-07 修）。`from` 形如 `10月06日 15:50  来自 iPhone客户端`。
        "from": ("%s 来自 %s" % (_pretty_time(create_time), source)
                 if create_time and source else _pretty_time(create_time)),
        "create_time": create_time,
        "nums": [str(card.get("repost") or ""), str(card.get("comment") or ""),
                 str(card.get("like") or "")],
        "img": card.get("img") or "",
        "is_video": card.get("is_video"),
    })


def _host_of(url: str) -> str:
    """取 URL 的 host（取不到就返回空串）。"""
    try:
        from urllib.parse import urlparse

        return (urlparse(url or "").hostname or "").lower()
    except Exception:
        return ""


def _is_search_page(url: str) -> bool:
    """最终落点**还在不在** `s.weibo.com`。

    ⚠️ 这是"有没有被踢到登录页"的**唯一可靠判据**。
       别去枚举登录域 —— 我第一版只认 `passport.weibo.com`，
       而实测 302 的目标是 `login.sina.com.cn`，直接漏过。

    ⚠️ 也**不能**只看状态码：`follow_redirects=True` 之后拿到的是
       最终页的 200，中间的 302 是看不见的。
    """
    host = _host_of(url)
    return host == "s.weibo.com"


def build_search_url(
    keyword: str,
    page: int = 1,
    xsort: str = "",
    search_type: str = "",
) -> str:
    """拼搜索 URL。

    ⚠️ 关键词必须 `quote` —— 中文不编码会让微博返回"页面不存在"
       （实测：`?q=沈阳` 直接访问 → pagenotfound）。

    ⚠️ `search_type` 决定**页面路径**（实时/视频/图片各有各的地址，
       见 `DESKTOP_PATHS`）；`xsort` 只是 `weibo` 页上的附加参数。
    """
    path, extra = DESKTOP_PATHS.get(
        (search_type or "").strip().lower(), DESKTOP_PATHS["note"])
    # 未指定 search_type 时保留旧的 xsort 行为（兼容既有调用方）
    if not search_type and xsort:
        path, extra = "weibo", "&xsort=" + xsort

    page_no = max(1, int(page))
    url = (f"https://s.weibo.com/{path}?q={quote(keyword or '')}"
           f"&page={page_no}{extra}")
    return url


async def fetch_page(
    keyword: str,
    page: int = 1,
    *,
    cookie_header: str = "",
    xsort: str = "",
    search_type: str = "",
    timeout: float = 20.0,
) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    """直连取**一页**。返回 `(卡片列表, 总页数)`。

    总页数是 `None` 表示"页面没说" —— 调用方要如实说不知道，
    **不要**用它反推"没有更多了"。
    """
    url = build_search_url(keyword, page, xsort, search_type)

    cookies: Dict[str, str] = {}
    for part in (cookie_header or "").split(";"):
        if "=" in part:
            k, _, v = part.partition("=")
            k, v = k.strip(), v.strip()
            if k:
                cookies[k] = v

    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=True,
        headers=BASE_HEADERS, cookies=cookies,
        proxy=None,   # 别让系统代理把请求带偏
    ) as c:
        r = await c.get(url)

    body = r.text or ""
    final = str(r.url)

    # ⚠️⚠️ **被踢到登录页必须在这里拦住**，否则会退化成"0 条结果"，
    #     用户看到的是"这个词没内容"—— 那是**假阴性**，最难查的一类错。
    #
    # 我第一版只认 `passport.weibo.com`，而实测微博把未登录请求 302 到的是
    # **`login.sina.com.cn`**：
    #
    #     GET s.weibo.com/weibo?q=营口  → 302
    #     GET login.sina.com.cn/sso/login.php?...  → 200
    #
    # ⇒ 检查穿过去了 → 解析出 0 张卡片 → 上层把它当"平台没内容" →
    #   **返回空列表且不回退浏览器**。用户搜"营口"得到 0 条就是这个原因。
    #
    # 所以判据改成**"最终落点还在不在 s.weibo.com"** —— 不写死任何一个
    # 登录域，微博换登录域也不会再骗过我们。
    if not _is_search_page(final):
        raise WeiboLoginRequired(
            "[weibo] 微博搜索需要登录（被重定向到 "
            f"{_host_of(final) or '未知页面'}）。"
            "请在「账号中心」重新保存微博登录态后重试。"
        )

    if "pagenotfound" in final or "retcode=6102" in final:
        # ⚠️ 通常是关键词没编码 —— 明确说出来，别让人以为是平台挂了
        raise RuntimeError(
            f"[weibo] 微博返回「页面不存在」（pagenotfound）。"
            f"常见原因是关键词没有正确编码。URL={url[:120]}"
        )

    # 正文里若出现登录表单标记，同样按"要登录"处理（兜底，防落点没变但内容变了）
    if "请先登录" in body[:4000] or "passport.weibo.com/sso/signin" in body[:8000]:
        raise WeiboLoginRequired(
            "[weibo] 微博搜索需要登录。请在「账号中心」重新保存微博登录态后重试。"
        )

    return parse_cards(body), parse_total_pages(body)


def _resolve_cookie(conn_key: str) -> str:
    """取该平台的 cookie 头。取不到就返回空串（游客态，多数会被踢）。"""
    try:
        from ..login_health import netscape_to_header, resolve_connection

        _cid, raw = resolve_connection(conn_key or "", "WEIBO")
        if not raw:
            return ""
        return netscape_to_header(raw, "weibo")
    except Exception as exc:
        logger.warning("[weibo] 取 cookie 失败（走游客态）: %s", exc)
        return ""