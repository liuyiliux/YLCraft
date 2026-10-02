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
    UserProfile,
)

logger = logging.getLogger("ylcraft.platforms.twitter")


class TwitterAuthError(RuntimeError):
    """X 凭证缺失或失效（需要用户重新登录）。

    与"没有搜索结果"必须区分 —— 前者要用户去登录，后者才是关键词没内容。
    """


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

        优先复用调用方带的 raw（搜索时已抓到的数据），避免再多一次请求。
        """
        from .search_dom import parse_detail_from_raw

        raw = (kwargs or {}).get("raw")
        if isinstance(raw, dict):
            detail = parse_detail_from_raw(raw, item_id)
            if detail is not None:
                return detail
        raise RuntimeError(
            f"[twitter] 未能获取推文详情（id={item_id}）。"
            "请先搜索取到该推文，再基于搜索结果查看详情。"
        )

    # =========================================================================
    # 用户（可选能力）
    # =========================================================================

    async def get_comments_page(
        self,
        item_id: str,
        max_results: int = 20,
        page: int = 1,
        cursor: str = "",
        root_comment_id: str = "",
    ) -> Dict[str, Any]:
        """取**一页**推文评论。

        ⚠️ X 的 GraphQL **没有 page 参数**，只有 cursor ——
        所以 `cursor` 是唯一的分页手段（`Bottom` 类型，实测每页 40 条全新增）。
        """
        tweet_id = str(item_id or "").strip()
        if not tweet_id:
            return {"comments": [], "has_more": False, "next_cursor": "", "total": 0}

        cookie = self.header_cookie()
        if not cookie:
            raise RuntimeError(
                "[twitter] 取评论需要登录态（auth_token + ct0）—— "
                "请在「账号中心」用浏览器方式登录一次 x.com。"
            )

        from .search_http import get_replies_via_http

        # ⚠️ X 的分页是"每页取一批然后按 cursor 继续"，我们这里
        # 一次取 max_results 条；has_more 用"取满没取满"推断
        # （X 不返回总数，游标也只在内部流转）
        comments = await get_replies_via_http(
            tweet_id,
            cookie_header=cookie,
            max_results=max_results,
            max_pages=1 if cursor else 3,
            parent_comment_id=root_comment_id,
        )
        # ⚠️ X 不暴露"下一页游标"给调用方（它内部就翻了）——
        # 这里如实返回空游标 + has_more=False，避免谎报能翻页
        return {
            "comments": comments,
            "has_more": False,
            "next_cursor": "",
            "total": len(comments),
        }

    async def get_replies(
        self,
        item_id: str,
        comment_id: str,
        max_results: int = 20,
        cursor: str = "",
    ) -> Dict[str, Any]:
        """取某条评论的子回复。

        ⚠️ X 的二级回复**在同一棵 TweetDetail 树里**（不用额外请求）——
        靠 `in_reply_to_status_id_str` 等于父评论 id 来筛。
        """
        return await self.get_comments_page(
            item_id,
            max_results=max_results,
            cursor=cursor,
            root_comment_id=str(comment_id or ""),
        )

    async def get_comments(
        self,
        item_id: str,
        max_results: int = 20,
        page: int = 1,
        cursor: str = "",
    ) -> List[Dict[str, Any]]:
        """取推文评论（纯 HTTP，复用 TweetDetail GraphQL）。

        ⚠️ **必须登录**（auth_token + ct0）—— 与 X 搜索一致。

        ## 为什么不用浏览器路径回退

        搜索有 `search_dom` 作回退（因为搜索页结构复杂），但**评论走 HTTP 就够**：
        实测 TweetDetail 直接 200，且响应很大（单页 176KB）——
        用浏览器反而更慢。所以失败时**直接抛可操作错误**，不回退。

        ## 字段说明

        返回的 `create_time` 是 **RFC2822 字符串**（如
        `"Mon Sep 28 02:33:36 +0000 2026"`）—— 与微博一致，
        由上层统一转（`/api/v1/comments` 的归一函数处理）。

        ⚠️ 只返回**直接回复主推**的（过滤二级回复与广告推文）。
        实测 40 条里只有部分是一级评论。
        """
        tweet_id = str(item_id or "").strip()
        if not tweet_id:
            return []

        cookie = self.header_cookie()
        if not cookie:
            raise RuntimeError(
                "[twitter] 取评论需要登录态（auth_token + ct0）—— "
                "请在「账号中心」用浏览器方式登录一次 x.com。"
            )

        from .search_http import get_replies_via_http

        return await get_replies_via_http(
            tweet_id,
            cookie_header=cookie,
            max_results=max_results,
            # 单页 176KB，别翻太多页
            max_pages=3,
        )

    async def search_users(
        self,
        keyword: str,
        max_results: int = 20,
    ) -> List[UserProfile]:
        """搜 X 用户（**复用 SearchTimeline，只把 product 改成 "People"**）。

        来源：twscrape `api.py::search_user`
            kv = {"product": "People", **(kv or {})}

        调研确认 X **不存在**独立的 SearchUser/UserSearch operation
        （已逐行核对 twscrape 全部 OP_* 常量 + Scweet manifest），
        所以直接复用现有 queryId —— 零额外成本。
        """
        from .search_http import search_users_via_http

        cookie = self.header_cookie()
        if not cookie:
            raise TwitterAuthError(
                "[twitter] 搜用户需要登录态（auth_token + ct0）。"
                "请在「账号中心」用浏览器方式登录一次 x.com。"
            )
        return await search_users_via_http(
            keyword, cookie_header=cookie, max_results=max_results
        )

    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """取 X 用户资料。

        ## ⚠️ `user_id` **可以是 handle 或数字 id**（2026-10-02 修）

        `UserByScreenName` 只能按 **handle**（screen_name）查 —— 数字 id
        要用另一个 operation（未实现）。

        **但前端传过来的往往是数字 id**：
        `search_users` 返回的 `id` 是 `rest_id`（数字），
        前端点「查看资料」时直接把 `user.id` 传过来 → `UserByScreenName`
        查不到 → 返回 None → 接口报"未能获取该用户资料"。

        修法：数字 id 时**先按 id 反查一次**（用搜索的 `TweetDetail`/
        `UserTweets` 拿不到就退回），更实际的做法是**让前端传 handle**。
        这里做兜底：数字 id 先尝试当 handle 查（有些场景 id 恰好是 handle），
        查不到就明确报错而不是静默 None。
        """
        from .search_http import get_user_via_http

        cookie = self.header_cookie()
        if not cookie:
            raise TwitterAuthError(
                "[twitter] 查用户资料需要登录态。请在「账号中心」登录一次 x.com。"
            )

        raw_id = (user_id or "").strip().lstrip("@")
        if not raw_id:
            return None

        # 直接按 handle 查（正常路径）
        profile = await get_user_via_http(raw_id, cookie_header=cookie)
        if profile is not None:
            return profile

        # ⚠️ 传进来是**数字 id**（rest_id）—— UserByScreenName 查不到。
        # 这不是"用户不存在"，要**如实说明**，不能返回 None 让上层
        # 报成"用户不存在或资料不可见"（会误导）。
        if raw_id.isdigit():
            raise TwitterAuthError(
                f"[twitter] 收到的是 X 的**数字 ID**（{raw_id}），"
                "但资料接口只能按 **handle**（用户名）查询。\n"
                "这是 X 的接口限制（按数字 ID 查要另一个 operation，未实现）。\n"
                "前端应传 `handle`（不带 @）—— 用户搜索结果里的 `raw_data.handle` 有。"
            )

        return None

    async def get_self_profile(self) -> Optional[UserProfile]:
        """取**自己**的资料（**纯 HTTP，不需要浏览器**）。

        ## ⚠️ 修正了之前的结论（2026-09-29）

        这里原来写着"X 没有『我是谁』的接口，只能靠浏览器读页面"——
        **那个结论不完整**。实测有个 REST 端点直接给：

            ① GET https://x.com/i/api/1.1/account/settings.json
               → {"screen_name": "308YYtGer5EWPqj", ...}   ← 自己的 handle
            ② GET .../UserByScreenName → 完整资料

        两步都 HTTP 200（用 `auth_token` + `ct0` + transaction-id）。

        实测：昵称「6」@308YYtGer5EWPqj，粉丝 10 / 关注 366 / 推文 15。

        ## 之前走浏览器还有个副作用

        `/users/me` 是 **api 模式，不开浏览器** —— 所以那条路**永远拿不到**，
        用户看到"登录态已失效"，但 cookie 其实好好的
        （用户反馈"微博和x是有效的，我搜索能搜到东西啊"）。
        """
        from .search_http import get_self_profile_via_http

        cookie = self.header_cookie()
        if not cookie:
            raise TwitterAuthError(
                "[twitter] 取自己的资料需要登录态（auth_token + ct0）。"
                "请在「账号中心」用浏览器方式登录一次 x.com。"
            )
        return await get_self_profile_via_http(cookie_header=cookie)

    # =========================================================================
    # 用户的推文列表（2026-09-29 打通）
    # =========================================================================

    async def get_user_videos(
        self,
        user_id: str,
        max_results: int = 20,
    ) -> List[SearchResult]:
        """取某个用户发的推文列表（**纯 HTTP**）。

        ## 参数说明

        `user_id` 这里要 **数字 userId**（不是 handle）——
        `UserTweets` 的 variables 用的是 `userId`。

        调用方（`/users/videos`）通常只有 handle，
        所以这里**自动转换**：不是纯数字就先 `UserByScreenName` 拿 `rest_id`。

        实测（自己的账号 @308YYtGer5EWPqj）解析出 2 条推文，
        正文 / 点赞 / 转发 / 时间都对。
        """
        from .search_http import fetch_user_tweets

        cookie = self.header_cookie()
        if not cookie:
            raise TwitterAuthError("[twitter] 取推文列表需要登录态。")

        uid = str(user_id or "").strip().lstrip("@")
        if not uid:
            return []

        # handle → 数字 id（UserTweets 只认数字 id）
        if not uid.isdigit():
            profile = await self.get_user_profile(uid)
            if profile is None:
                logger.info("[twitter] 找不到用户 %s，无法取推文列表", uid)
                return []
            uid = str(profile.id or "")
            if not uid.isdigit():
                logger.info("[twitter] 用户 %s 没拿到数字 id", user_id)
                return []

        data = await fetch_user_tweets(
            uid, cookie_header=cookie, max_results=max_results
        )
        return data.get("tweets") or []
