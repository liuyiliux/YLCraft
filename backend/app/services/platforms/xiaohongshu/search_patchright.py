"""
YLCraft — 小红书搜索（Patchright 浏览器方案）

背景（2026-09-26 抓包实测，勿凭记忆改回）：
- 小红书搜索端点已从 `edith.../v1/search/notes` 迁移到
  `so.xiaohongshu.com/api/sns/web/v2/search/notes`（域名+版本都变了）。
- 该接口需要 `X-s`/`X-t` 签名，签名函数 `window._webmsxyw` 是混淆 JS，
  且实测**跨域调用会 406**（在 www 页面上对 so. 域 fetch 被 CORS/风控拒绝）。
- 在已登录的浏览器页面里走它自己的搜索框 → 结果渲染成 DOM
  （`section.note-item`，实测 30 条/页），可稳定解析。

结论：Python 里重写签名不可行也不必要；用 Patchright 打开搜索页读 DOM。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List
from urllib.parse import quote

from ..types import SearchResult, SearchParams
from .apis import SEARCH_PAGE

logger = logging.getLogger("ylcraft.platforms.xiaohongshu.search_pr")

SEARCH_URL = SEARCH_PAGE

# 在搜索页上下文里解析已渲染的笔记卡片
JS_PARSE_CARDS = """
() => {
  const cards = [...document.querySelectorAll('section.note-item')];
  return cards.map(c => {
    const a = c.querySelector('a.cover');
    const t = c.querySelector('.title, [class*=title]');
    const au = c.querySelector('.name, [class*=author] .name');
    const lk = c.querySelector('[class*=like] .count, .like-wrapper .count');
    const hasVideo = !!c.querySelector('[class*=play], svg.play');
    // href 形如 /search_result/{id}?xsec_token=...&xsec_source=...
    const href = a ? (a.getAttribute('href') || '') : '';
    const m = href.match(/\\/search_result\\/([a-f0-9]+)/);
    return {
      id: m ? m[1] : '',
      xsec_token: (href.match(/xsec_token=([^&]+)/) || [])[1] || '',
      title: t ? t.innerText.trim() : '',
      author: au ? au.innerText.trim() : '',
      likes: lk ? lk.innerText.trim() : '0',
      is_video: hasVideo,
      href: href,
    };
  }).filter(x => x.id);
}
"""


async def search_via_patchright(client, params: SearchParams) -> List[SearchResult]:
    """用 Patchright 打开小红书搜索页，读取渲染后的笔记卡片。

    两种入口：
      1. client 已注入 `_patchright_page`（复用调用方的浏览器上下文）
      2. 否则用 `search_with_runtime()` 自建浏览器 + 注入已保存的 Cookie
         （client.config.cookie）

    没有可用浏览器/Cookie 时显式报错，不静默返回空。
    """
    page = getattr(client, "_patchright_page", None)
    if page is None:
        # 没有现成页面就走自建浏览器路径（注入 client 的 Cookie）
        return await search_with_runtime(client, params)

    url = SEARCH_URL.format(keyword=quote(params.keyword or ""))
    await page.goto(url, wait_until="domcontentloaded")
    # 等搜索结果渲染（实测 30 条卡片出现约需 3~10s）
    try:
        await page.wait_for_selector("section.note-item", timeout=15000)
    except Exception:
        logger.warning("[xhs] 等待 note-item 超时，按当前 DOM 继续")
    await page.wait_for_timeout(1500)

    raw_cards: List[Dict[str, Any]] = await page.evaluate(JS_PARSE_CARDS)
    max_n = params.max_results or 20
    results = [parse_card(c) for c in raw_cards[:max_n]]
    logger.info("[xhs] patchright search %r -> %d cards", params.keyword, len(results))
    return results


async def search_with_runtime(client, params: SearchParams) -> List[SearchResult]:
    """自建浏览器执行搜索：注入 Cookie → **先预热首页** → 打开搜索页读卡片。

    ## 三个实测要点（2026-09-26，都是踩过才知道的）

    1. **必须用 `add_cookies` 注入，不能用请求头传 Cookie。**
       对照实测：`fetch_page(headers={"Cookie": ...})` → 0 张卡片；
       `ctx.add_cookies(...)` → 27~30 张。小红书的登录态判断依赖
       浏览器 cookie jar 里的域属性，光在请求头带不够。

    2. **必须先访问首页"预热"，不能直接打开搜索页。**
       对照实测：
           先 goto /explore 再 goto 搜索页 → ✅ 27 张卡片
           直接 goto 搜索页               → ❌ 超时 / 0 张
       搜索页依赖首页建立的会话上下文，直接进会拿不到数据。

    3. **不能用无头模式。** 实测无头会被甩到验证码/登录页。

    用 `patchright_runtime` 的统一出口，不自己 new playwright。
    """
    cookie = getattr(getattr(client, "config", None), "cookie", "") or ""
    if not cookie:
        raise RuntimeError(
            "[xhs] 小红书搜索需要登录 Cookie：请先在平台连接里用『浏览器』方式"
            "保存小红书（未登录时该站会重定向到 /login，搜不到结果）。"
        )

    from app.services.browser.patchright_runtime import get_patchright_runtime

    runtime = get_patchright_runtime()
    ctx = await runtime.new_context(
        headless=False,  # 无头会被甩验证码页（实测）
        viewport={"width": 1440, "height": 900},
    )
    try:
        # 要点 1：显式注入 cookie jar（Header 方式实测无效）
        pairs = [p for p in cookie.split("; ") if "=" in p]
        if pairs:
            await ctx.add_cookies([
                {
                    "name": p.split("=", 1)[0],
                    "value": p.split("=", 1)[1],
                    "domain": ".xiaohongshu.com",
                    "path": "/",
                }
                for p in pairs
            ])

        page = await ctx.new_page()

        # 要点 2：先访问首页预热，否则搜索页拿不到数据（实测）
        try:
            await page.goto("https://www.xiaohongshu.com/explore",
                            wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(6000)
        except Exception as exc:
            logger.warning("[xhs] 首页预热未完成（继续尝试搜索）：%s", exc)

        url = SEARCH_URL.format(keyword=quote(params.keyword or ""))
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:
            raise RuntimeError(
                f"[xhs] 打开搜索页超时：{type(exc).__name__}。"
                "通常是 Cookie 失效或平台限流，请重新获取小红书 Cookie 后重试。"
            ) from exc

        # 等卡片渲染（实测约 5~10s）
        try:
            await page.wait_for_selector("section.note-item", timeout=15000)
        except Exception:
            logger.warning("[xhs] 等待 note-item 超时，按当前 DOM 继续")
        await page.wait_for_timeout(1500)

        final_url = page.url or ""
        if "/login" in final_url:
            raise RuntimeError(
                "[xhs] 被重定向到登录页：Cookie 已失效或未登录，"
                "请重新获取小红书 Cookie。"
            )

        raw_cards: List[Dict[str, Any]] = await page.evaluate(JS_PARSE_CARDS)
        max_n = params.max_results or 20
        results = [parse_card(c) for c in raw_cards[:max_n]]
        logger.info(
            "[xhs] runtime search %r -> %d cards", params.keyword, len(results),
        )
        return results
    finally:
        await ctx.close()


def _parse_cards_from_html(html: str) -> List[Dict[str, Any]]:
    """从渲染后的 HTML 里抽出卡片 id / xsec_token（不依赖浏览器 evaluate）。

    只取稳定可得的两项：note id 与 xsec_token。
    标题/作者/点赞在 HTML 里的结构随版本变化大，交给调用方按需再取，
    避免在这里写死易碎的 HTML 结构。
    """
    import re

    cards: List[Dict[str, Any]] = []
    seen: set[str] = set()
    # href 形如 /search_result/{24位hex}?xsec_token=...&xsec_source=
    for m in re.finditer(
        r'/search_result/([a-f0-9]{24})\?xsec_token=([^&"\']+)', html
    ):
        note_id, token = m.group(1), m.group(2)
        if note_id in seen:
            continue
        seen.add(note_id)
        cards.append({"id": note_id, "xsec_token": token})
    return cards


def parse_card(c: Dict[str, Any]) -> SearchResult:
    """把 DOM 卡片转成统一 SearchResult。

    xsec_token 是小红书详情/跳转的必要参数，放进 raw_data 和 URL；
    不虚构 author_id/cover（DOM 卡片里没有，详情接口才有）。
    """
    note_id = c.get("id") or ""
    likes_raw = str(c.get("likes") or "0")
    token = c.get("xsec_token") or ""
    return SearchResult(
        id=note_id,
        title=c.get("title") or "",
        author=c.get("author") or "",
        author_id="",  # 搜索卡片 DOM 不含作者 id，详情页才有
        cover="",      # 卡片背景图是 CSS background，需要详情接口取
        url=(f"https://www.xiaohongshu.com/search_result/{note_id}"
             f"?xsec_token={token}&xsec_source="),
        platform="xiaohongshu",
        type="video" if c.get("is_video") else "note",
        likes=parse_count(likes_raw),
        raw_data={"card": c, "xsec_token": token},
    )


def parse_count(s: str) -> int:
    """'2.3万' -> 23000；'1128' -> 1128。"""
    s = (s or "").strip()
    try:
        if "万" in s:
            return int(float(s.replace("万", "")) * 10000)
        return int(s)
    except (ValueError, TypeError):
        return 0
