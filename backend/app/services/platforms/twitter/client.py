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
        """搜推特。

        ## 优先纯 HTTP，失败回退浏览器 DOM（2026-09-28）

        **HTTP 路径**（`search_http`）：
          · 不需要浏览器运行时（快）
          · cursor 翻页，想拿多少拿多少
          · 字段全（精确时间 / 语言 / 媒体类型）
          需要 `auth_token` + `ct0`，且要生成 `x-client-transaction-id`

        **DOM 路径**（`search_dom`）作回退：
          · 当 transaction-id 生成失败、或 X 改了接口结构时用
          · 代价：必须开浏览器；受虚拟列表限制，只能"边滚边收集"

        ## ⚠️ 两条路都必须登录

        凭证失效时抛**可操作错误**（含"去账号中心登录"），
        **不返回"0 条结果"** —— 后者会让人误以为关键词没内容。
        """
        cookie = self.header_cookie()

        # 1) 优先 HTTP
        if cookie:
            from .search_http import TwitterAuthError, search_via_http
            from .xclid import TransactionIdError

            try:
                return await search_via_http(params, cookie_header=cookie)
            except TwitterAuthError:
                # 凭证问题不是"接口不可用"，必须抛出去让用户去登录 ——
                # 回退 DOM 只会得到同样结果，而且更慢。
                raise
            except TransactionIdError as exc:
                logger.warning(
                    "[twitter] transaction-id 生成失败，回退浏览器路径：%s",
                    str(exc)[:120],
                )
            except Exception as exc:
                logger.warning(
                    "[twitter] HTTP 路径失败（%s: %s），回退浏览器路径",
                    type(exc).__name__, str(exc)[:120],
                )
        else:
            logger.info("[twitter] 没有 cookie，直接走浏览器路径")

        # 2) 回退 DOM
        from .search_dom import search_via_patchright

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
