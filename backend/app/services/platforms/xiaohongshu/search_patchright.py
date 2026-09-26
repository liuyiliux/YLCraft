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

    需要传入已登录的浏览器上下文；client 须提供 `patchright_page`
    （由上层连接管理器注入）。没有浏览器时显式报错，不静默返回空。
    """
    page = getattr(client, "_patchright_page", None)
    if page is None:
        raise RuntimeError(
            "[xhs] Patchright 搜索需要浏览器上下文（_patchright_page）。"
            "请先在平台连接里用『浏览器』方式保存小红书 Cookie，"
            "或在调用处注入已登录的 Page。"
        )

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
