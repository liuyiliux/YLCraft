"""YLCraft — 推特/X 搜索（Patchright 浏览器 + DOM 解析）。

## 为什么走浏览器 + 读 DOM

四条路都试过，只有浏览器可靠：

| 方案 | 实测结果 |
|------|---------|
| httpx + guest token + queryId | **HTTP 404** |
| 页面内 fetch（无额外头） | **HTTP 403** |
| 页面内 fetch + `x-csrf-token` | **仍 403** |
| 从 JS bundle 动态提取 queryId | 不可行（懒加载分散） |
| **打开搜索页 + 读 DOM** | ✅ 已验证可读到推文 |

另外 gallery-dl 里硬编码的 queryId（`4fpceYZ6-YQCx_JSl_Cn_A`）
**实测已失效**（404），当前真实值是 `uGB-gNd5HE4TkpO70OcFNw`。
但 queryId 会轮换，硬编码必然再次失效，所以**不采用 GraphQL 路径**。

## ⚠️ 必须登录

实测（Patchright 全新 profile，真·未登录）：

    https://x.com/search?q=美食&src=typed_query
    → 重定向 https://x.com/i/jf/onboarding/web?redirect_after_login=...
    → article 数 = 0

**别被 `document.cookie` 误导**：`auth_token` 是 httpOnly，看不到 ≠ 没登录。
可靠判据是**只有登录后才出现的界面元素**（发帖 / 账号菜单）。

所以推特要能用，前提是用户在 YLCraft 的浏览器 profile 里登录过一次推特。
未登录时这里报**可操作的登录提示**，而不是"0 条结果"。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from ...browser.patchright_runtime import get_patchright_runtime
from ..session_pool import PooledSession, SessionPool
from ..types import NoteDetail, SearchParams, SearchResult

logger = logging.getLogger("ylcraft.platforms.twitter")

_pool = SessionPool(idle_seconds=900)

HOME_URL = "https://x.com/"

# 搜索页（未登录会被重定向到登录引导页）
SEARCH_URL_TMPL = "https://x.com/search?q={q}&src=typed_query"
SEARCH_MEDIA_URL_TMPL = "https://x.com/search?q={q}&f=media&src=typed_query"


class TwitterLoginRequiredError(RuntimeError):
    """推特未登录（搜索被重定向到登录引导页，或没有登录后才有的界面元素）。

    与"没有搜索结果"必须区分 —— 前者要用户去登录，后者才是关键词没内容。
    """


# 读推文卡片。
#
# 要点：
#   · 用 indexOf 而非 CSS 属性选择器（`a[href*="/status/"]` 传参时
#     容易因引号转义变成无效选择器，实测踩过）
#   · 图片只取 `pbs.twimg.com/media`（`profile_images` 是头像，要排除）
#   · 从 `/status/<id>` 取推文 ID 与作者 handle
JS_PARSE_TWEETS = """
() => {
  const arts = [...document.querySelectorAll('article')];
  const out = [];
  for (const a of arts) {
    const links = [...a.querySelectorAll('a')].map(x => x.getAttribute('href') || '');
    const status = links.find(h => /\\/status\\/\\d+$/.test(h)) || '';
    const m = status.match(/^\\/([^/]+)\\/status\\/(\\d+)/) || [];
    const imgs = [...a.querySelectorAll('img')].map(x => x.src)
      .filter(s => s.indexOf('pbs.twimg.com/media') >= 0);
    const vids = [...a.querySelectorAll('video')].map(v => v.src || '').filter(Boolean);
    const grp = a.querySelector('[role="group"]');
    out.push({
      id: m[2] || '',
      handle: m[1] || '',
      media: imgs,
      video: vids,
      aria: grp ? (grp.getAttribute('aria-label') || '') : '',
      text: (a.innerText || '').replace(/\\s+/g, ' ').slice(0, 400),
    });
  }
  return JSON.stringify({ url: location.href, articles: out.length, tweets: out });
}
"""

# 登录态检测：**不看 cookie**（auth_token 是 httpOnly，看不到 ≠ 没登录），
# 而看只有登录后才出现的界面元素。
JS_CHECK_LOGIN = """
() => ({
  hasCompose: !!document.querySelector('[data-testid="SideNav_NewTweet_Button"]'),
  hasAccount: !!document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]'),
  hasLoginBtn: !!document.querySelector('[data-testid="loginButton"]'),
  url: location.href,
})
"""


def _pool_key(conn_key: str) -> str:
    return f"twitter:{conn_key or 'default'}"


async def _get_session(conn_key: str) -> PooledSession:
    """取（或新建）一个已打开推特首页的会话。"""
    key = _pool_key(conn_key)
    session = _pool.get(key)
    if session is None:
        rt = get_patchright_runtime()
        ctx = await rt.new_context(
            headless=False,
            viewport={"width": 1440, "height": 900},
            persistent_platform="twitter",
        )
        page = await ctx.new_page()
        session = PooledSession(ctx=ctx, page=page)
        _pool.put(key, session)
        logger.info("[twitter] 新建浏览器会话 key=%s", key)

    if not session.warmed:
        try:
            await session.page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:
            _pool.drop(key)
            raise RuntimeError(
                f"[twitter] 打开 x.com 失败：{type(exc).__name__}。"
                "通常是网络问题（访问 x.com 需要可用的网络环境）。"
            ) from exc
        await session.page.wait_for_timeout(9000)
        session.warmed = True
    session.touch()
    return session


async def check_logged_in(page) -> None:
    """未登录时抛可操作的错误。"""
    try:
        state = await page.evaluate(JS_CHECK_LOGIN)
    except Exception:
        return

    d = state or {}
    if d.get("hasCompose") or d.get("hasAccount"):
        return
    raise TwitterLoginRequiredError(
        "[twitter] 检测到未登录。Twitter/X 的搜索**强制要求登录**"
        "（实测：未登录打开搜索页会被重定向到登录引导页，article 数为 0）。\n"
        "解决办法：到「账号中心」用浏览器方式打开 x.com 登录一次 —— "
        "登录态会保存在 YLCraft 的持久化 profile 里，之后即可搜索。"
    )


async def search_via_patchright(
    params: SearchParams,
    *,
    conn_key: str = "",
    page: int = 1,
    media_only: bool = False,
) -> List[SearchResult]:
    """在浏览器里搜推特（打开搜索页 → 读 DOM）。

    优点：不依赖会轮换的 GraphQL queryId。
    限制：只拿首屏 + 少量滚动加载的推文（约 10-20 条）。
    """
    want = max(1, params.max_results or 20)
    session = await _get_session(conn_key)
    await check_logged_in(session.page)

    raw_st = getattr(params, "search_type", "") or "note"
    stype = str(getattr(raw_st, "value", raw_st))
    use_media = media_only or stype in ("video", "image", "media")

    tmpl = SEARCH_MEDIA_URL_TMPL if use_media else SEARCH_URL_TMPL
    url = tmpl.format(q=quote(params.keyword, safe=""))

    try:
        await session.page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception as exc:
        _pool.drop(_pool_key(conn_key))
        raise RuntimeError(f"[twitter] 打开搜索页失败：{type(exc).__name__}") from exc

    try:
        await session.page.wait_for_selector("article", timeout=25000)
    except Exception:
        logger.warning("[twitter] 等待推文超时，按当前 DOM 继续")
    await session.page.wait_for_timeout(6000)

    # 滚动加载。
    #
    # ⚠️ 这里踩过两个坑（2026-09-28，用户反馈"只有 9 个"）：
    #
    #   坑 1（滚动方式）：原实现是**固定滚 2 次、每次 `scrollBy(0, 1600)`**。
    #     实测几乎没效果 —— 首屏 5 条，`scrollBy(0,1600)` 只到 6 条，
    #     而 `scrollTo(0, scrollHeight)`（滚到底）能到 10 条。
    #     原因：一屏推文就 ~900px，滚 1600 只多加载一两条；
    #     推特是在**接近底部**时才触发下一批。
    #
    #   坑 2（虚拟列表，更隐蔽）：就算滚到底，**最后读一次 DOM 也拿不全**。
    #     诊断显示 DOM 里 article 数量会**波动**：
    #         滚1: 5→10   滚2: 10→9   滚4: 9→6   滚8: 9→15
    #     因为推特是虚拟列表，**滚动时回收离屏节点** ——
    #     中间滚过的推文已经不在 DOM 里了。
    #
    # 所以现在用 `_scroll_and_collect`：**边滚边收集 + 按 id 去重累积**。
    data = await _scroll_and_collect(session.page, want)

    if not data.get("articles"):
        # article=0 可能是被重定向到登录页，再确认一次
        await check_logged_in(session.page)
        logger.info("[twitter] 搜索 %r 无结果（article=0）", params.keyword)
        return []

    out: List[SearchResult] = []
    seen: set[str] = set()
    for t in data.get("tweets") or []:
        parsed = parse_tweet(t)
        if parsed is None or parsed.id in seen:
            continue
        seen.add(parsed.id)
        out.append(parsed)
        if len(out) >= want:
            break

    logger.info("[twitter] 搜索 %r -> %d 条（DOM）", params.keyword, len(out))
    return out[:want]


async def _scroll_and_collect(page, want: int, max_rounds: int = 12) -> Dict[str, Any]:
    """**边滚边收集**推文（应对推特的虚拟列表）。

    ## 为什么必须"边滚边收"（实测 2026-09-28）

    原来只滚到底、最后读一次 DOM，结果拿不全。诊断显示
    **DOM 里的 article 数量会波动**：

        滚 1: 5 -> 10
        滚 2: 10 -> 9     ← 变少了！
        滚 4: 9 -> 6      ← 更少
        滚 5: 6 -> 10
        滚 8: 9 -> 15

    原因：推特是**虚拟列表** —— 滚动时回收离屏节点，
    DOM 里只保留可视区附近的那批。
    所以"滚到底再读一次"会丢掉中间滚过的推文。

    正确做法是每滚一次就把**当时 DOM 里的**推文抓下来、
    按 id 去重累积。

    ## 终止条件

      · 累积够 `want` 条
      · 连续 2 轮没有新增（真的到底了）
      · 达到 max_rounds（防止无限滚）
    """
    merged: Dict[str, Any] = {}
    stagnant = 0
    last_count = 0

    for i in range(max_rounds):
        # 抓当前 DOM 里的推文并入总表（按 id 去重）
        try:
            raw = await page.evaluate(JS_PARSE_TWEETS)
            batch = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:
            break

        new = 0
        for t in (batch.get("tweets") or []):
            tid = str((t or {}).get("id") or "")
            if tid and tid not in merged:
                merged[tid] = t
                new += 1

        if len(merged) >= want:
            break

        # 连续两轮没有新增 → 到底了
        if new == 0 and len(merged) == last_count:
            stagnant += 1
            if stagnant >= 2:
                break
        else:
            stagnant = 0
        last_count = len(merged)

        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            break
        # 等下一批渲染（实测 3.2s 比较稳）
        await page.wait_for_timeout(3200)

    return {
        "articles": len(merged),
        "tweets": list(merged.values()),
    }


async def close_pool() -> None:
    await _pool.close_all()


# =============================================================================
# 解析（模块级，便于测试）
# =============================================================================

def parse_tweet(t: Dict[str, Any]) -> Optional[SearchResult]:
    """把 DOM 提取的推文转成统一 SearchResult。

    ⚠️ `SearchResult` 没有 images/video 字段（那些在 NoteDetail 里），
    所以图片与视频直链放进 `raw_data._images` / `raw_data._video_url`
    （与微博同一约定，crawler 层会取出来填进 CrawlerResult）。
    """
    if not isinstance(t, dict):
        return None
    tid = str(t.get("id") or "")
    if not tid:
        return None

    handle = str(t.get("handle") or "")
    text = str(t.get("text") or "")
    media = [upgrade_image_url(u) for u in (t.get("media") or []) if u]
    video = [u for u in (t.get("video") or []) if u]
    counts = parse_aria_counts(str(t.get("aria") or ""))

    return SearchResult(
        id=tid,
        title=text[:80],
        desc=text,
        author=handle,
        author_id=handle,
        cover=media[0] if media else "",
        url=(
            f"https://x.com/{handle}/status/{tid}"
            if handle else f"https://x.com/i/status/{tid}"
        ),
        platform="twitter",
        type="video" if video else "note",
        likes=counts["likes"],
        comments=counts["comments"],
        shares=counts["shares"],
        views=counts["views"],
        raw_data={
            "_images": media,
            "_video_url": video[0] if video else "",
            "handle": handle,
            "dom": t,
        },
    )


def parse_detail_from_raw(raw: Dict[str, Any], item_id: str) -> Optional[NoteDetail]:
    """用搜索结果里的 DOM 数据组装详情（零额外请求）。"""
    if not isinstance(raw, dict):
        return None
    dom = raw.get("dom") or {}
    text = str(dom.get("text") or "")
    media = [u for u in (raw.get("_images") or []) if u]
    video = str(raw.get("_video_url") or "")
    handle = str(raw.get("handle") or "")
    if not text and not media and not video:
        return None
    return NoteDetail(
        id=item_id,
        title=text[:80],
        desc=text,
        author=handle,
        author_id=handle,
        platform="twitter",
        type="video" if video else "note",
        images=media,
        video=video,
        video_cover=media[0] if media else "",
        raw_data=dom,
    )


def parse_aria_counts(aria: str) -> Dict[str, int]:
    """从互动区的 aria-label 里取数字。

    实测格式（中文界面）："20 回复、24 喜欢、704 次观看"
    英文界面："20 replies, 24 likes, 704 views"

    取不到留 0（**不编造**）。
    """
    def grab(*keys: str) -> int:
        for k in keys:
            # 允许数字与关键词之间夹少量字符：实测中文会说
            # "2 次转帖"（数字与"转帖"之间有"次"），
            # 英文是 "2 reposts"。所以用 `[^0-9]{0,4}` 而不是 `\s*`。
            m = re.search(rf"([\d,]+)[^0-9]{{0,4}}{k}", aria)
            if m:
                try:
                    return int(m.group(1).replace(",", ""))
                except ValueError:
                    continue
        return 0

    return {
        "comments": grab("回复", "repl"),
        "likes": grab("喜欢", "like"),
        "shares": grab("转帖", "转推", "retweet", "repost"),
        "views": grab("次观看", "观看", "view"),
    }


def upgrade_image_url(url: str) -> str:
    """把推特图片升到原图（`name=orig`）。

    来源 gallery-dl `extractor/twitter.py`：
        self._size_image = "orig"
    形如 `...?format=jpg&name=large` → `...?format=jpg&name=orig`

    ⚠️ 该规则**未在我方环境验证**（未登录拿不到真实推文图片）。
    只做字符串替换，失败时原样返回 —— 不会让流程崩。
    """
    if not url or "pbs.twimg.com" not in url:
        return url
    if "profile_images" in url:
        return url          # 头像是头像，不是推文配图
    if "name=" in url:
        head, _, _tail = url.rpartition("name=")
        return f"{head}name=orig"
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}name=orig"
