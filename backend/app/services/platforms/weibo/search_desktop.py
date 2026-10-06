"""YLCraft — 微博**桌面版**搜索（`s.weibo.com`）翻页取结果。

## 为什么需要这个文件（2026-10-06 实测）

移动版 `m.weibo.cn/api/container/getIndex` 的 `page` 参数**翻不动**：

    page=1 → 9 条     page=2 → **0 条**（ok=1，正常受理，就是没内容）

我为这件事翻过**三次车**，三个结论互不相同（页码式 → 游标式 → 单页式），
每次都因为同一个根因：**只看接口，没看页面自己怎么发请求。**

### ⭐ 决定性实验：让页面自己翻一次（2026-10-06）

在**已登录**（`/api/config` → `data.login=true`、`uid=7628413874`）的浏览器里打开

    https://m.weibo.cn/p/index?containerid=100103type%3D1%26q%3D沈阳

监听 `page.on("request")`，然后滚到底 —— 页面**自己**发的是：

    /api/container/getIndex?containerid=100103type%3D1%26q%3D沈阳&page=2
    /api/container/getIndex?containerid=100103type%3D1%26q%3D沈阳&page=3
    /api/container/getIndex?containerid=100103type%3D1%26q%3D沈阳&page=4

页面上卡片数 **18 → 28 → 40 → 50** —— **它确实翻到了第 4 页。**
⇒ "微博只有 1 页"这个结论是**我的取法**造成的，不是平台限制。

## ⚠️⚠️ 测"能不能翻页"之前，**必须先确认登录态**（我栽过两次）

两次都是同一类错误，两个不同的坑：

**① 手工脚本没加载 `.env`**

    `database.py:26` 的 `os.getenv("DATABASE_URL", "...localhost:5432...")`
    兜底生效 → 读不到远端库 → 注入 cookie 失败 → **访客态**

后果：测出 `page=2 → ok=-100` → 我当成"平台没数据"。
正确写法：`load_dotenv(BACKEND / ".env")` **放在 import app 之前**。

**② 判据看错字段位置**

    {"data":{"login":true,"uid":"7628413874", ...}, "ok":1}
                        ↑ 在 `data` 里，不在顶层

我看顶层 `cfg.get("login")` → `None` → 误判"未登录"。

**访客态 vs 登录态长得完全不一样**：

|            | `page=2` 返回                                   |
| ---------- | ----------------------------------------------- |
| 访客态     | `ok=-100` + passport 登录页 URL                  |
| 登录态     | `ok=1` + **0 条**（正常受理，只是没内容）        |

混在一起看必然误判 —— 我就是这么归因错一次的。

### 把页面那条请求原样抄下来，还是 0 条

逐项对照过，**四个变量全部单独测过**，没有一个是真凶：

| 变量                                   | 结果           |
| -------------------------------------- | -------------- |
| 有无 `page_type=searchall`             | 都是 9/0 条    |
| 有无 `x-xsrf-token`（页面确实发了它）  | 都是 9/0 条    |
| `referer` = 首页 vs 真实搜索页         | 都是 9/0 条    |
| `type` = 1 / 60 / 61 / 64             | 都是 9/0 条    |

所以走 fetch 抄请求这条路**已经走到头**，原因**未查明**（不写进结论）。
MediaCrawler（★76k）用的也正是这条 `m.weibo.cn` + `page=N`，同样只拿到 1 页
—— 它是去重标的，不是能翻页的证据。

### ⇒ 改走桌面版 `s.weibo.com`（实测 2026-10-06）

    https://s.weibo.com/weibo?q={关键词}&page={N}

**服务端渲染**，登录浏览器里逐页实测：

    page=1  40 条（含 20 个带 mid 的）
    page=2  10 个 mid，**与 page=1 重叠 0 个**
    page=3  10 个，重叠 0
    page=5 / 10 / **50**  都还有 10 个，与 page=1 重叠 0

⇒ **一页 10 条、最多 50 页 = 500 条**，而且页与页**零重叠**（真翻页，不是重复）。

## 本文件做什么

只取"列表"（标题 / 作者 / 计数 / 封面 / mid），**不做详情**。

- 详情仍走原来的 `m.weibo.cn` 路径（`parse_mblog_detail` 不变）——
  那是实测过字段最全的，不需要为了搜索去改它。
- `statuses/show?id={mid}` 可用（顶层直接是 mblog，本体没有 `data.mblog` 外壳），
  但**每条多一次请求**；列表页 DOM 里字段已经够用，所以默认不调。

## 登录态

桌面版**必须登录**。用库里那份 cookie 走 httpx 直连实测：

    GET https://s.weibo.com/weibo?q=沈阳   → 跳 passport.weibo.com/visitor/visitor

所以这里和 `search_patchright.py` 一样**在浏览器里取**（cookie 由调用方注入）。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger("ylcraft.platforms.weibo.desktop")

# 桌面版搜索页（**服务端渲染**，不是 SPA）
DESKTOP_SEARCH_URL = "https://s.weibo.com/weibo?q={keyword}&page={page}"

# 桌面版的**分类参数是 `xsort`**（2026-10-06 从页面自己的标签链接读出来的，
# 不是猜的）：
#
#     综合   /weibo?q=沈阳&Refer=weibo_weibo        ← 无 xsort
#     热门   /weibo?q=沈阳&xsort=hot&Refer=hotmore
#
# ⚠️ 移动版的 `type=1/60/61/64` 在桌面版**完全无效** —— 实测 `type=61`
# 返回的是与默认一模一样的 20 条（一模一样，100% 重叠）。
# 我先前试过的 `t=1/31/34` 也不对（`t=31` 出来的"不同"是实时结果在变，
# 不是分类生效）。**别再猜参数名，去读页面上的 href。**
DESKTOP_XSORT: Dict[str, str] = {
    "all": "",            # 综合（桌面版不带 xsort）
    "default": "",
    "note": "",
    "realtime": "",       # ⚠️ 桌面版**没有**实时分类（页面上只有 综合 / 热门）
    "popular": "hot",     # 热门
    "hot": "hot",
}

# 桌面版**没有**「实时」标签 —— 显式记下来，见 `search_via_patchright`
# 里"回退到综合要打日志"那条。前端有这个标签时不静默冒充。
DESKTOP_NO_REALTIME = "realtime"

# 实测上限：第 50 页仍有内容，再往后就是空页
DESKTOP_MAX_PAGE = 50

# 实测每页 10 条（用来估"要翻几页才够 want 条"）
DESKTOP_PAGE_SIZE = 10

# 从页面里抓结果卡片的 JS。
#
# ⚠️ 不用正则解析 HTML —— 实测 `card-wrap` 的属性顺序不固定
# （`mid="..."` 有时在 class 前、有时在后），正则漏掉了一半，
# 页面明明有 44 条却只抽出 20 个。**在 DOM 上取属性**没有这个问题。
#
# ⚠️⚠️ 卡片结构有两种（同一页面同时存在，2026-10-06 实测）：
#
#     旧版  div.card-wrap > .card-tool
#     新版  div.card       > .card-act > ul > li
#
#     两种都要能抓 —— 只写一种，另一半结果会静默变成空字段。
#     上一版只认 `.card-tool`，跑出来作者名/三个计数**全是空的**。
JS_EXTRACT_CARDS = r"""
() => {
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  // ⚠️ 一个 li 里可能是 "1.2万" / "3456" / "转赞人数超过10"，
  //    也可能就一个字都没有（转发为 0 时显示的是**文字"转发"**）。
  const num = (s) => {
    const t = clean(s);
    if (!t) return '';
    const m = t.match(/[\d.]+\s*[万亿]?/);
    return m ? m[0].replace(/\s+/g, '') : '';
  };
  const out = [];
  for (const el of document.querySelectorAll('div.card-wrap[mid], div.card[mid]')) {
    const mid = el.getAttribute('mid') || '';
    if (!/^\d+$/.test(mid)) continue;

    const body = el.querySelector('p.txt');
    // ⚠️ 作者名在 `a.name`，**不是** `.name a`（上一版写反了 → author 全空）
    const nameA = el.querySelector('a.name') || el.querySelector('.name a');
    // ⚠️⚠️ **按位置取，不能按"哪些像数字"筛**（上一版就是这么错的）：
    //   转发为 0 时第一个 li 文本是 "转发" 而非 "0"，
    //   数字过滤把整行筛没了 → 三个计数全变成 0。
    //   li 恒为 3 个，顺序实测恒为 转发 → 评论 → 点赞。
    const act = el.querySelector('.card-act') || el.querySelector('.card-tool');
    const lis = act ? Array.from(act.querySelectorAll('li')) : [];
    const pic = el.querySelector('.pic-wrap img, .media img, .card-wrap img');
    const html = el.innerHTML || '';

    out.push({
      mid: mid,
      text: clean(body ? body.innerText : ''),
      user: clean(nameA ? nameA.innerText : ''),
      userHref: (nameA && nameA.getAttribute('href')) || '',
      from: clean((el.querySelector('.from') || {}).innerText || ''),
      nums: [num(lis[0] ? lis[0].innerText : ''),
             num(lis[1] ? lis[1].innerText : ''),
             num(lis[2] ? lis[2].innerText : '')],
      img: (pic && pic.src && pic.src.indexOf('sinaimg.cn') >= 0) ? pic.src : '',
      // ⚠️ 视频判据用 `.media-video*` 与 `video.weibo.com` 链接。
      //    不要写 `[class*="video"]` —— 会命中无关类名（上一版的老毛病）
      is_video: !!el.querySelector('.media-video, .media-video-a, .video-icon')
              || html.indexOf('video.weibo.com') >= 0,
    });
  }
  return JSON.stringify(out);
}
"""


class DesktopLoginRequired(RuntimeError):
    """桌面版把我们踢到登录页了。

    单独一个异常类型，好让调用方能**区分**"没登录"和"没搜到"——
    前者要用户去账号中心补登录态，后者才是关键词真没内容。
    """


async def fetch_desktop_page(
    session,
    keyword: str,
    page: int,
    *,
    xsort: str = "",
) -> List[Dict[str, Any]]:
    """抓桌面版搜索的**一页**，返回原始卡片 dict 列表。

    `session` 是 `search_patchright._get_session` 借来的
    （它已经注入过 cookie、开过 m.weibo.cn）。这里 `goto` 到 s.weibo.com。

    ⚠️ 桌面站与 m 站是**两个域**，但 cookie 已按 `.weibo.com`/`.weibo.cn`
    两个域都种过（见 `_inject_cookies`），所以登录态是通的。

    ⚠️ `nodup=1` **故意不加** —— 页面上"查看全部搜索结果"那个链接带它，
    加了反而会因为去重逻辑拿到不同的一批，导致第 2 页内容跳变。
    """
    url = DESKTOP_SEARCH_URL.format(keyword=keyword, page=max(1, int(page)))
    if xsort:
        url = f"{url}&xsort={xsort}"
    try:
        await session.page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception as exc:
        logger.warning("[weibo] 桌面版搜索第 %d 页打不开：%s", page, exc)
        return []

    # ⚠️⚠️ 等渲染**必须给短超时**（实测教训）：
    #    搜到结果时 `card-wrap` 1 秒内就出现；
    #    **搜不到时页面永远不出现** —— 原来 timeout=15000，
    #    于是"搜一个不存在的词"要干等 15 秒（实测 16.8 秒）才返回空。
    #    用户看到的就是"卡住了十几秒"。
    #    现在 6 秒封顶，超时照样往下走（evaluate 会返回空列表）。
    try:
        await session.page.wait_for_selector(
            "div.card-wrap[mid], div.card[mid]", timeout=6000
        )
    except Exception:
        pass
    await session.page.wait_for_timeout(1200)

    try:
        raw = await session.page.evaluate(JS_EXTRACT_CARDS)
    except Exception as exc:
        logger.warning("[weibo] 桌面版第 %d 页抽卡失败：%s", page, exc)
        return []

    try:
        cards = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except (TypeError, ValueError) as exc:
        logger.warning("[weibo] 桌面版第 %d 页解析失败：%s", page, exc)
        return []
    if not isinstance(cards, list):
        return []

    body = ""
    try:
        body = await session.page.content()
    except Exception:
        pass
    if "passport.weibo.com" in body[:20000] or "请登录后查看" in body:
        raise DesktopLoginRequired()

    return [c for c in cards if isinstance(c, dict) and c.get("mid")]


def _parse_counts(nums: List[str]) -> tuple[int, int, int]:
    """把卡片上的三个数字还原成 (转发, 评论, 点赞)。

    ⚠️ 顺序是**实测**的，不是猜的：`.card-act li` / `.card-tool` 恒为 3 个，
        DOM 顺序恒为 转发 → 评论 → 点赞。

    ⚠️ **计数为 0 时页面上显示的是文字"转发"/"评论"，不是数字 0**
        （实测：`['转发', '1', '15']`）。所以 JS 侧按**位置**取值、
        取不到就交空串，这边给 0 —— **绝不把"文字"当成数字**。
        宁可少一个数，不要编一个数出来（这个毛病今天在评论总数上犯过）。
    """
    vals = []
    for t in list(nums)[:3]:
        try:
            vals.append(_cn_number(t))
        except (TypeError, ValueError):
            vals.append(0)
    while len(vals) < 3:
        vals.append(0)
    return vals[0], vals[1], vals[2]


def _cn_number(text: str) -> int:
    """把 "1.2万" / "3456" / "1亿" 解析成整数。

    ⚠️ 拿不到数字（空串、"转发"、"转赞人数超过10"）时返回 **0**，
        不猜、不报错 —— 调用方要的是一个整数，不是异常。
    """
    t = (text or "").strip().replace(",", "")
    if not t:
        return 0
    m = re.search(r"(\d+(?:\.\d+)?)\s*([万亿]?)", t)
    if not m:
        return 0
    try:
        value = float(m.group(1))
    except ValueError:
        return 0
    if m.group(2) == "万":
        value *= 10_000
    elif m.group(2) == "亿":
        value *= 100_000_000
    return int(value)


def _uid_from_href(href: str) -> str:
    """从 `//weibo.com/7215424647?refer_flag=...` 里取作者 uid。"""
    m = re.search(r"weibo\.(?:com|cn)/(?:u/)?(\d{6,})", href or "")
    return m.group(1) if m else ""


def parse_desktop_card(card: Dict[str, Any]) -> Any:
    """把一张桌面版卡片转成统一的 `SearchResult`。

    ⚠️ 桌面卡片**没有** `create_time` 的原始值，只有 "43分钟前" 这种相对时间，
    这里**如实留空**而不是编一个时间戳。详情页（`parse_mblog_detail`）
    才有精确的 `created_at`。
    """
    from ..types import SearchResult

    mid = str(card.get("mid") or "").strip()
    if not mid:
        return None
    text = (card.get("text") or "").strip()
    if not text:
        return None

    repost, comment, like = _parse_counts(list(card.get("nums") or []))
    img = card.get("img") or ""
    is_video = bool(card.get("is_video"))

    raw: Dict[str, Any] = {
        "_source": "desktop_search",
        "_from_text": card.get("from") or "",
        "_images": [img] if img else [],
        "_video_url": "",
    }

    return SearchResult(
        id=mid,
        title=text[:80],
        desc=text,
        author=card.get("user") or "",
        author_id=_uid_from_href(card.get("userHref") or ""),
        cover=img,
        url=f"https://m.weibo.cn/detail/{mid}",
        platform="weibo",
        type="video" if is_video else "note",
        likes=like,
        comments=comment,
        shares=repost,
        create_time="",
        raw_data=raw,
    )
