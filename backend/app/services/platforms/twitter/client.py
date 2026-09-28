"""YLCraft — 推特/X 客户端（注册到 PlatformClientFactory）。

搜索/详情走 Patchright + DOM（原因见 `search_dom.py` 顶部说明），
这里只实现基类契约。

## 一句话结论

推特 **必须登录**，且 **必须走浏览器**：
  · httpx（guest token + queryId）→ 404
  · 页面内 fetch → 403
  · 未登录打开搜索页 → 被重定向到登录引导页，article=0
"""
from __future__ import annotations

import logging
from typing import Dict, List

from ..base import BasePlatformClient, register_platform
from ..types import (
    ClientMode,
    NoteDetail,
    SearchParams,
    SearchResult,
)

logger = logging.getLogger("ylcraft.platforms.twitter")


@register_platform("twitter")
# 别名：前端「内容搜索」页用 `twitter`；另外注册 `x` / `tw`
# 以免别的调用方写别名时报 Unsupported platform（微博踩过这个坑）。
@register_platform("x")
@register_platform("tw")
class TwitterClient(BasePlatformClient):
    """推特/X 客户端。

    用法：
        config = ClientConfig(platform="twitter", mode=ClientMode.API)
        async with TwitterClient(config) as client:
            results = await client.search(SearchParams(keyword="美食"))
    """

    def _build_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self.config.user_agent or self._get_default_user_agent(),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def _get_default_user_agent(self) -> str:
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
        )

    def _get_platform_domain(self) -> str:
        return ".x.com"

    async def search(self, params: SearchParams) -> List[SearchResult]:
        """搜推特（浏览器 + DOM）。

        **未登录会抛 `TwitterLoginRequiredError`**（可操作提示），
        而不是返回空列表 —— 后者会让人误以为"关键词没内容"。
        """
        from .search_dom import search_via_patchright

        if self.config.mode == ClientMode.API:
            logger.info(
                "[twitter] 该平台直连不可用（guest token 不足 + queryId 轮换），"
                "自动转浏览器路径"
            )
        return await search_via_patchright(
            params,
            conn_key=self.config.conn_id or "",
            page=max(1, int(getattr(params, "page", 1) or 1)),
        )

    async def get_detail(self, item_id: str, **kwargs) -> NoteDetail:
        """取推文详情。

        DOM 路径已含正文/作者/图片/视频，所以优先复用调用方带的 raw
        （搜索时抓到的 DOM 数据），避免再开一次页面。
        """
        from .search_dom import parse_detail_from_raw

        raw = (kwargs or {}).get("raw")
        if isinstance(raw, dict):
            detail = parse_detail_from_raw(raw, item_id)
            if detail is not None:
                return detail
        raise RuntimeError(
            f"[twitter] 未能获取推文详情（id={item_id}）。"
            "推特详情需要浏览器路径（且必须登录）—— "
            "请先搜索取到该推文，再基于搜索结果查看详情。"
        )
