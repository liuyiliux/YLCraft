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
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

logger = logging.getLogger("ylcraft.platforms.weibo.http")

DESKTOP_SEARCH_URL = "https://s.weibo.com/weibo?q={keyword}&page={page}"

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

    return parse_desktop_card({
        "mid": card.get("mid"),
        "text": card.get("text"),
        "user": card.get("user"),
        "userHref": "//weibo.com/%s" % card.get("user_id", ""),
        "from": "",
        "nums": [str(card.get("repost") or ""), str(card.get("comment") or ""),
                 str(card.get("like") or "")],
        "img": card.get("img") or "",
        "is_video": card.get("is_video"),
    })


def build_search_url(keyword: str, page: int = 1, xsort: str = "") -> str:
    """拼搜索 URL。

    ⚠️ 关键词必须 `quote` —— 中文不编码会让微博返回"页面不存在"
       （实测：`?q=沈阳` 直接访问 → pagenotfound）。
    """
    url = DESKTOP_SEARCH_URL.format(keyword=quote(keyword or ""),
                                    page=max(1, int(page)))
    if xsort:
        url = f"{url}&xsort={xsort}"
    return url


async def fetch_page(
    keyword: str,
    page: int = 1,
    *,
    cookie_header: str = "",
    xsort: str = "",
    timeout: float = 20.0,
) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    """直连取**一页**。返回 `(卡片列表, 总页数)`。

    总页数是 `None` 表示"页面没说" —— 调用方要如实说不知道，
    **不要**用它反推"没有更多了"。
    """
    url = build_search_url(keyword, page, xsort)

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

    # 被踢到登录/访客页 —— 要**区分**于「没搜到」
    if "passport.weibo.com" in final or "passport.weibo.com" in body[:20000]:
        raise WeiboLoginRequired(
            "[weibo] 微博搜索需要登录。请在「账号中心」重新保存微博登录态后重试。"
        )
    if "pagenotfound" in final or "retcode=6102" in final:
        # ⚠️ 通常是关键词没编码 —— 明确说出来，别让人以为是平台挂了
        raise RuntimeError(
            f"[weibo] 微博返回「页面不存在」（pagenotfound）。"
            f"常见原因是关键词没有正确编码。URL={url[:120]}"
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