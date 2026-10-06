"""YLCraft — 微博客户端。

## 实测结论（2026-09-27，在真实浏览器内验证）

    GET https://m.weibo.cn/api/container/getIndex
        ?containerid=100103type=1&q=美食&page_type=searchall&page=1
    → {"ok":1,"data":{"cards":[{"card_type":9,"mblog":{...}}],
                      "cardlistInfo":{"total":739}}}

## ⚠️ 必须登录（与抖音不同）

不带 Cookie 时：HTTP 432 / 重定向到 Sina Visitor System /
`{"ok":-100,"url":".../sso/signin..."}`。

**`ok == -100` 是"未登录"，不是"没搜到结果"** ——
把它报成"关键词无结果"会把人带偏，所以这里显式区分。

## 图片与视频（实测字段，不用猜后缀）

`mblog.original_pic` 直接给**原图 URL**；
视频在 `mblog.page_info`（`type=="video"`）：

    media_info.stream_url / stream_url_hd
    urls.mp4_720p_mp4 / mp4_hd_mp4 / mp4_ld_mp4
    page_pic.url（封面）/ duration（秒）

所以不需要像某些项目那样拼 `/orj360/` `/mw690/` 后缀。
"""
from __future__ import annotations

import asyncio
import calendar
import logging
import re
import time
from typing import Any, Dict, List, Optional

from ..base import BasePlatformClient, register_platform
from ..types import (
    ClientConfig,
    ClientMode,
    # ⚠️ 必须导入 —— `WeiboLoginRequiredError` 要继承它才能被 API 层
    # 的 `except LoginExpiredError` 映射成 401（见该类的 docstring）
    LoginExpiredError,
    NoteDetail,
    SearchParams,
    SearchResult,
    UserProfile,
)
from .apis import (
    MOBILE_HOST,
)
from .search_desktop import DESKTOP_MAX_PAGE

logger = logging.getLogger("ylcraft.platforms.weibo")

# 移动端 UA（微博移动 API 对桌面 UA 不友好）
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


class WeiboLoginRequiredError(LoginExpiredError):
    """微博未登录（ok=-100）。

    与"没有搜索结果"必须区分 —— 前者要用户去补登录态，
    后者才是关键词真没内容。

    ## ⚠️ 必须继承 `LoginExpiredError`（2026-10-02 修）

    原来这里是 `WeiboLoginRequiredError(RuntimeError)` —— 于是
    API 层的 `except LoginExpiredError` 分支**全部落空**，
    微博登录态过期时返回 **HTTP 500**「获取我的资料失败」。

    500 在语义上是"服务端故障"，用户不会想到要去账号中心重新登录
    —— 而这恰恰是用户自己能解决的问题。
    审计见 `tests/test_error_class_hierarchy.py`。
    """


@register_platform("weibo")
# 别名 `wb`：**前端「内容搜索」页的平台列表用的就是 `wb`**
# （`PLATFORMS` 里 `{ value: 'wb', label: '微博' }`）。
# 不注册这个别名，用户在界面上选微博会直接报
# `ValueError: Unsupported platform: wb`（实测踩过）。
@register_platform("wb")
class WeiboClient(BasePlatformClient):
    """微博客户端（搜索 / 详情 / 图文与视频解析）。

    用法：
        config = ClientConfig(platform="weibo", mode=ClientMode.API, cookie=<微博cookie>)
        async with WeiboClient(config) as client:
            results = await client.search(SearchParams(keyword="美食"))
    """

    # =========================================================================
    # 基类契约
    # =========================================================================

    def _build_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self.config.user_agent or MOBILE_UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": f"{MOBILE_HOST}/",
            "X-Requested-With": "XMLHttpRequest",
        }

    def _get_default_user_agent(self) -> str:
        return MOBILE_UA

    def _get_platform_domain(self) -> str:
        # ⚠️⚠️ **必须返回 None，不能只给一个域**（2026-10-06 修，用户实测踩到）
        #
        # 原来返回 `.weibo.cn`，于是 `base._set_cookies_to_browser`
        # 把 cookie **只种到 m 站域**。但微博搜索现在走桌面版
        # `https://s.weibo.com/weibo?q=...` —— 那是 `.weibo.com`，
        # **一个 cookie 都收不到**，页面被踢到登录页 → 搜出 0 条。
        #
        # ⚠️ 日志当时还打了 `[wb] Cookies set to browser` ——
        #    那句话在骗人：cookie 种了，但种错了域。
        #    "无异常"不等于"生效了"。
        #
        # 返回 None = 让 `_set_cookies_to_browser` 走
        # `_get_platform_domains()`，那边会把两个域都给全。
        return None

    async def search(self, params: SearchParams) -> List[SearchResult]:
        """按关键词搜微博。

        ## ⚠️ 微博搜索**走直连 HTTP**，不需要浏览器（2026-10-07 更正）

        这个 docstring 原来写着"必须走浏览器（Service Worker 依赖）"，
        **那是错的**，而且我把它当成实测结论写进了代码。

        真正的原因是我给**网页请求**加了接口才用的头：

            GET https://s.weibo.com/weibo?q=沈阳
            -H 'x-requested-with: XMLHttpRequest'      ← 就是这个

        带上它微博返回"页面不存在"（`pagenotfound&retcode=6102`），
        我拿这个被踢的结果得出"直连不行" —— **白开了两天浏览器**。

        去掉那个头之后实测（登录态，全程不开浏览器）：

            page=1/2/3/10/50  全都有内容，页与页零重叠
            0.3~1 秒/页       （浏览器那条是 15 秒 + 250MB 内存）

        ⇒ 现在交给 `search_patchright.search_via_patchright`，
          它**先试直连**，直连异常/被限流时才退回浏览器兜底。
          函数名还叫 `_patchright` 是历史遗留，别被名字骗了。

        ## mode 的影响

        `mode=API` 与 `mode=PATCHRIGHT` 现在**走同一条路**
        （先直连、失败才浏览器）。保留分支只是为了不改调用方。
        """
        from .search_patchright import search_via_patchright

        return await search_via_patchright(
            params,
            conn_key=self.config.conn_id or "",
            client=self,
            page=max(1, int(getattr(params, "page", 1) or 1)),
            # ⚠️ 必须**放宽到平台上限**（10-06 实测：桌面版有 50 页），
            #    不能用默认的 3 —— 否则用户选「每页 50 条」只拿到 30 条，
            #    而且页面上不会有任何提示说"被截断了"。
            #    函数内部会按 `want` 算够几页就停，取满即止，
            #    所以给 50 不会导致每次都翻 50 页。
            max_pages=DESKTOP_MAX_PAGE,
        )

    async def get_detail(self, item_id: str, **kwargs) -> NoteDetail:
        """取微博详情。

        三条路径：
          1. 调用方带 `raw`（搜索时的 mblog）→ 直接解析，零请求
          2. 否则按 id 打开详情页解析（HTML 里的 `$render_data`）
          3. 都拿不到 → 抛可读错误

        优先走 1：搜索结果的 mblog 已含详情所需的一切
        （正文/作者/图片/视频/统计）。
        """
        raw = (kwargs or {}).get("raw")
        if isinstance(raw, dict) and raw.get("id"):
            detail = parse_mblog_detail(raw)
            if detail is not None:
                return detail

        # 2) 打开详情页解析
        detail = await self._fetch_detail_by_page(item_id)
        if detail is not None:
            return detail

        raise RuntimeError(
            f"[weibo] 未能获取微博详情（id={item_id}）。"
            "可能原因：微博已删除、仅粉丝可见，或登录态失效。"
        )

    # =========================================================================
    # 用户（可选能力，走浏览器 —— 与搜索同样的原因）
    # =========================================================================

    async def search_users(
        self,
        keyword: str,
        max_results: int = 20,
    ) -> List[UserProfile]:
        """搜微博用户（**实测免登录可用**）。

            containerid=100103type=3&q={关键词}&page_type=searchall&page=N
            → cards[].card_type=11 → card_group[] → user{}

        一页约 20 个。走浏览器（微博依赖 Service Worker，见模块 docstring）。
        """
        from .search_patchright import search_users_via_patchright

        return await search_users_via_patchright(
            keyword,
            conn_key=self.config.conn_id or "",
            client=self,
            max_results=max_results,
        )

    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """取用户资料（`containerid=100505{uid}` → `data.userInfo`）。"""
        from .search_patchright import get_user_via_patchright

        return await get_user_via_patchright(
            user_id, conn_key=self.config.conn_id or "", client=self
        )

    async def get_self_profile(self) -> Optional[UserProfile]:
        """取**自己**的资料。

        ⚠️ 微博没有"我是谁"的接口，且**未登录时不能从页面抓 uid**
        （那是推荐流里的别人）—— 所以未登录直接返回 None。
        详见 `search_patchright.get_self_profile_via_patchright`。
        """
        from .search_patchright import get_self_profile_via_patchright

        return await get_self_profile_via_patchright(
            conn_key=self.config.conn_id or "", client=self
        )

    # =========================================================================
    # 某用户发的微博列表（2026-09-29 打通）
    # =========================================================================

    async def get_user_videos(
        self,
        user_id: str,
        max_results: int = 20,
    ) -> List[SearchResult]:
        """取某个用户发的微博列表。

        ⚠️ `user_id` 是**微博 uid（数字）**，不是昵称。

        实测（自己的 uid 7628413874）：page=1/2/3 各 10 条不同内容。

        前置：会话**必须注入登录 cookie** —— `page>=2` 要求登录态
        （`page=1` 是公开数据）。见 `search_patchright._inject_cookies`。
        """
        from .search_patchright import get_user_posts_via_patchright

        uid = str(user_id or "").strip()
        if not uid:
            return []
        return await get_user_posts_via_patchright(
            uid,
            max_results=max_results,
            conn_key=self.config.conn_id or "",
            client=self,
        )

    async def get_replies(
        self,
        item_id: str,
        comment_id: str,
        max_results: int = 20,
        cursor: str = "",
    ) -> Dict[str, Any]:
        """取某条微博评论的子回复（楼中楼）。

        ## ⚠️⚠️ 这里原来写着"微博不支持单独取子回复"——**那个结论是错的**
        ## （2026-10-04 实测推翻，第二次）

        当时的理由是"实测 20 条评论里 0 条带 `comments`"，
        并拿 MediaCrawler（★66k）"也只读 comment.comments、且默认开关关着"
        做交叉验证。

        **两处都不成立**：

          ① 那批"0 条带 comments"是**抽样**抽到的另一批内容。
             换成确定有楼中楼的样本（用户给的 5336295257679240），
             顶层 20 条**全部**带 `comments`（共 32 条），`rootid` 零串号。
          ② 「别人也没实现」**不能**证明「平台没有这个数据」——
             MediaCrawler 可能是没做，而不是做不了。

        这是同一个坑的第三次：快手（`reply_count=0` → 写"取不到"）、
        B站（信了文档说"随顶层返回"，实际数组全空）、微博（抽样没抽到）。
        **字段是提示，接口才是事实；抽样碰不到 ≠ 平台没有。**

        ## 实现

        子回复**就在顶层响应的 `comments` 字段里**，不需要额外端点 ——
        所以这里走顶层接口再按 id 筛，而不是调 `/comments/hotFlowChild`
        （那个端点实测 `ok=0`，本次也没再试它 —— 顶层已经够用）。

        ⚠️ 顶层接口**分页**（`max_id`），所以要把顶层翻完才能保证找得到
        目标评论；这里最多翻 `MAX_TOP_PAGES` 页，超了如实报错而不是
        假装"没有回复"（那会让用户以为没人回）。
        """
        mid = str(item_id or "").strip()
        cid = str(comment_id or "").strip()
        if not mid or not cid:
            return {"comments": [], "has_more": False, "next_cursor": "", "total": 0}

        max_pages = 6          # 顶层翻页上限（找不到就不编造）
        cursor_id: Any = 0
        found: Optional[Dict[str, Any]] = None
        exhausted = False     # 是不是翻到最后一页了（区分"没找到"vs"没翻到"）

        for _ in range(max_pages):
            resp = await self._call("/comments/hotflow", {
                "id": mid, "mid": mid, "max_id_type": 0,
                **({"max_id": cursor_id} if cursor_id else {}),
            })
            data = (resp or {}).get("data") or {}
            if not isinstance(data, dict):
                break
            # ⚠️ 顶层列表在 `data.data`（不是 data.comments）—— 与
            # get_comments_page 读的是同一层，别写错
            for c in data.get("data") or []:
                if isinstance(c, dict) and str(c.get("id") or "") == cid:
                    found = c
                    break
            if found is not None:
                break
            cursor_id = data.get("max_id") or 0
            if not cursor_id or str(cursor_id) == "0":
                exhausted = True
                break
        else:
            exhausted = False    # 翻页用尽（for-else）

        if found is None:
            if exhausted:
                # 已翻到最后一页还是没这条 → 内容确实不在
                return {"comments": [], "has_more": False,
                        "next_cursor": "", "total": 0}
            # ⚠️ 翻页用尽仍没找到 → **明说**，不返回空列表冒充"没人回复"
            raise NotImplementedError(
                f"[weibo] 在前 {max_pages} 页顶层评论里没找到 id={cid}。\n"
                f"这条评论可能在更靠后的页（微博热门评论会按热度重排）。\n"
                f"⚠️ 这不是「没有回复」—— 是**没翻到**。\n"
                f"（顶层评论仍可用：去掉 parent_id 参数。）"
            )

        # ⚠️ 用 `_norm_reply`（单一事实来源）—— 顶层内嵌和这里给前端的数据
        # 必须一致，否则"直接展开"和"点开加载"会显示不同内容。
        all_subs = [_norm_reply(s) for s in (found.get("comments") or [])]
        all_subs = [s for s in all_subs if s]
        want = max(1, int(max_results or 20))
        out = all_subs[:want]

        nxt = cursor_id
        has_more = bool(nxt) and str(nxt) not in ("", "0") and len(all_subs) > want
        return {
            "comments": out,
            "has_more": has_more,
            "next_cursor": str(nxt) if has_more else "",
            # ⚠️ 不编造：微博**不给**子回复总数（顶层 reply_count 恒 0），
            # 这里给"本页实际条数"，不拿视频总评论数冒充
            "total": len(out),
        }

    async def get_comments_page(
        self,
        item_id: str,
        max_results: int = 20,
        page: int = 1,
        cursor: str = "",
    ) -> Dict[str, Any]:
        """取**一页**微博评论，带回游标（支持"加载更多"）。

        ⚠️ 微博分页是 **`max_id` 游标不是页码** ——
        上层只传 `page` 的话第二次会拿到相同数据（前端点"加载更多"没反应）。
        所以这里必须把 `max_id` 透出去。
        """
        mid = str(item_id or "").strip()
        if not mid:
            return {"comments": [], "has_more": False, "next_cursor": "", "total": 0}

        want = max(1, int(max_results or 20))
        params: Dict[str, Any] = {"id": mid, "mid": mid, "max_id_type": 0}
        if cursor:
            params["max_id"] = cursor

        resp = await self._call("/comments/hotflow", params)
        data = resp.get("data") or {}
        if not isinstance(data, dict):
            return {"comments": [], "has_more": False, "next_cursor": "", "total": 0}

        out: List[Dict[str, Any]] = []
        for c in data.get("data") or []:
            if not isinstance(c, dict):
                continue
            cid = str(c.get("id") or "")
            if not cid:
                continue
            u = c.get("user") or {}
            pic = c.get("pic") or {}
            pics = c.get("pics") or []
            images = []
            if isinstance(pics, list):
                for p in pics:
                    large = (p or {}).get("large") or {}
                    if large.get("url"):
                        images.append(large["url"])
            elif pic.get("large", {}).get("url"):
                images.append(pic["large"]["url"])
            # ⚠️⚠️ `reply_count` 原来**写死 0**，而下一行 `replies` 却有真实数据
            #
            # 实测（2026-10-04，样本 5336295257679240）：顶层 20 条评论
            # **20/20 都有子回复**（共 32 条），而微博接口给我们的
            # `reply_count` 字段**全是 0** —— 只能自己数。
            #
            # 这个 bug 的后果很隐蔽：前端判断"要不要显示楼中楼入口"用的是
            #     (c.reply_count ?? c.rcount) > 0
            # 写死 0 ⇒ **用户永远看不到回复入口**，哪怕数据就在手里。
            # 数据明明抓到了，却因为一个数不显示 —— 这比"取不到"更难查。
            _raw_reps = c.get("comments") or []
            _raw_reps = _raw_reps if isinstance(_raw_reps, list) else []
            # ⚠️⚠️ 原来这里直接 `"replies": _reps` —— **原样透传微博的原始结构**，
            # 而那个结构里内容在 `text` / 作者在 `user.screen_name`，
            # **没有** `content` / `author` 字段。
            # 前端拿到的是 `content: null` / `author: null` → 展开后是一片空白。
            #
            # 实测（2026-10-04 用户实测截图确认）：展开后有内容，
            # 是因为那条数据来自 **`/comments?parent_id=` 独立取**（那条路已统一形状），
            # 不是来自这里。所以这个 bug 之前**没被发现** ——
            # 只要前端没读过顶层内嵌的 replies 字段就看不出。
            #
            # 现在统一转成前端形状，两条路给的数据就一致了。
            _reps = [_norm_reply(r) for r in _raw_reps]
            _reps = [r for r in _reps if r]
            out.append({
                "id": cid,
                "content": _strip_html(c.get("text") or ""),
                "author": u.get("screen_name") or "",
                "author_id": str(u.get("id") or ""),
                "avatar": u.get("profile_image_url") or "",
                "likes": int(c.get("like_count") or 0),
                "create_time": _rfc2822_to_ts(c.get("created_at") or ""),
                # 微博自己给的 reply_count 恒为 0（实测 20/20）→ 只能数
                "reply_count": len(_reps),
                "location": (c.get("source") or "").replace("来自", "").strip(),
                "images": images,
                "replies": _reps,
            })

        nxt = data.get("max_id")
        has_more = bool(nxt) and str(nxt) != "0"
        return {
            "comments": out[:want],
            # ⚠️ 游标要透出去（`max_id`），否则前端翻不了页
            "next_cursor": str(nxt) if has_more else "",
            "has_more": has_more,
            # 外层 total_number 才是该微博总评论数（评论项里的恒为 0）
            "total": int(data.get("total_number") or 0),
        }

    async def get_comments(
        self,
        item_id: str,
        max_results: int = 20,
        page: int = 1,
        cursor: str = "",
    ) -> List[Dict[str, Any]]:
        """取微博评论（纯 HTTP，**不需要**浏览器/Service Worker）。

        ## 接口（2026-10-01 实测确认可用）

            GET https://m.weibo.cn/comments/hotflow
                ?id={微博ID}&mid={同值}&max_id_type={0|1}&max_id={游标}
            Headers: Referer: https://m.weibo.cn/detail/{微博ID}   ← 必需
                     X-Requested-With: XMLHttpRequest

        ⚠️ 实测对比：`buildComments`（PC 端）返回 `ok:-100` 未登录；
        `hotflow`（移动端）`ok:1` 正常 —— **用 hotflow**。

        ## ⚠️ 结构坑：评论在 `data.data[]`（**双层**）

        响应是 `{"ok":1,"data":{"data":[...], "max_id":..., ...}}`。
        我第一版按顶层 `data` 取 → 拿到空列表。游标也在 `data` 层。

        ## 登录态（实测，要说清楚）

          · **第 1 页：匿名可用**（无 cookie 也 `ok:1`，反复验证成立）
          · **翻页（带 max_id）：需要登录**（匿名返回 `ok:-100`）

        所以 max_results 大时会翻页 → 需要 cookie。没 cookie 时**只返回首页**，
        如实返回（不报错、也不谎称"0 条评论"）。

        ## 字段（实测）

            id / text(**HTML，需去标签**) / like_count
            created_at(**RFC2822 字符串**，非时间戳)
            user.screen_name / user.id / user.profile_image_url
            source("来自 湖南" → IP属地)

        ⚠️ 评论项里的 `total_number` 实测恒为 0，别当回复数；
        外层 `data.total_number` 才是该微博总评论数。
        ⚠️ 限流非常敏感（实测连续探测约 10 次即被踢登录态）→ 每页 sleep ≥2s。
        """
        mid = str(item_id or "").strip()
        if not mid:
            return []

        want = max(1, int(max_results or 20))
        out: List[Dict[str, Any]] = []
        seen: set[str] = set()
        cur = cursor or ""

        # ⚠️ 循环调 `get_comments_page`（归一逻辑只写一处 —— 那里有完整的
        # 字段映射与游标处理）。翻页靠它返回的 `next_cursor`。
        for _ in range(max(1, (want + 19) // 20) + 1):
            if len(out) >= want:
                break
            try:
                page_data = await self.get_comments_page(
                    mid, max_results=20, cursor=cur
                )
            except WeiboLoginRequiredError:
                # 没登录态时翻页会走到这里 —— 首页数据拿到了就正常返回
                if out:
                    logger.info("[weibo] 翻页需登录态，返回已取到的 %s 条", len(out))
                    break
                raise

            for c in page_data.get("comments") or []:
                cid = str(c.get("id") or "")
                if not cid or cid in seen:
                    continue
                seen.add(cid)
                out.append(c)
                if len(out) >= want:
                    break

            if not page_data.get("has_more"):
                break
            nxt = str(page_data.get("next_cursor") or "")
            if not nxt or nxt == cur:
                break
            cur = nxt
            await asyncio.sleep(2)   # 实测限流敏感，保守 2s

        return out[:want]

    # =========================================================================
    # 统一请求出口
    # =========================================================================

    async def _call(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """GET 微博 API 并**显式区分登录态问题**。"""
        if self._http_client is None:
            await self._init_http_client()
        url = f"{MOBILE_HOST}{path}"
        resp = await self._http_client.get(url, params=params or {})

        if resp.status_code == 432:
            raise WeiboLoginRequiredError(
                "[weibo] 请求被微博拒绝（HTTP 432）。"
                "微博要求登录态：请在「账号中心」用浏览器方式保存微博 Cookie。"
            )
        resp.raise_for_status()

        text = resp.text or ""
        if not text.strip():
            raise WeiboLoginRequiredError(
                f"[weibo] 请求 {path} 返回空响应体。"
                "微博在未登录时会这样拒绝，请检查登录态。"
            )
        if not text.lstrip().startswith("{"):
            # 被重定向到访客/登录页（HTML）
            raise WeiboLoginRequiredError(
                f"[weibo] 请求 {path} 返回的不是 JSON（可能被重定向到 "
                "Sina Visitor System）。请在「账号中心」重新保存微博登录态。"
            )

        data = resp.json()
        ok = data.get("ok")
        if ok == -100:
            raise WeiboLoginRequiredError(
                "[weibo] 微博返回 ok=-100（未登录）。"
                f"响应里的登录地址：{data.get('url', '')[:80]}。"
                "**这不是「没有搜索结果」**——请在「账号中心」保存微博 Cookie。"
            )
        return data

    # =========================================================================
    # 解析
    # =========================================================================

    @staticmethod
    def _extract_mblogs(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从响应里取出微博正文（card_type=9）。

        搜索结果的 cards 里混着 card_type=9（正文，有 mblog）
        与 11（广告/运营），只取前者。
        """
        cards = (data.get("data") or {}).get("cards") or []
        out: List[Dict[str, Any]] = []
        for card in cards:
            if not isinstance(card, dict):
                continue
            if card.get("card_type") != CARD_TYPE_MBLOG:
                continue
            mb = card.get("mblog")
            if isinstance(mb, dict) and mb.get("id"):
                out.append(mb)
        return out

    async def _fetch_detail_by_page(self, item_id: str) -> Optional[NoteDetail]:
        """按 id 打开详情页，解析 HTML 里的 `$render_data`。

        来源：MediaCrawler `get_note_info_by_id`（用正则从 HTML 提取）。

        ⚠️ 正则匹配 `var $render_data = ([...])[0]` —— 结构与站点版本
        相关，失效时这里返回 None（由调用方给可读错误），不静默返回空详情。
        """
        if self._http_client is None:
            await self._init_http_client()
        url = f"{MOBILE_HOST}/detail/{item_id}"
        resp = await self._http_client.get(url)
        if resp.status_code != 200:
            logger.warning("[weibo] 详情页返回 HTTP %s", resp.status_code)
            return None

        m = re.search(r"var \$render_data = (\[.*?\])\[0\]", resp.text or "", re.DOTALL)
        if not m:
            logger.warning("[weibo] 详情页未找到 $render_data（id=%s）", item_id)
            return None
        try:
            import json as _json

            payload = _json.loads(m.group(1))
            status = payload[0].get("status") if payload else None
        except Exception as exc:
            logger.warning("[weibo] $render_data 解析失败：%s", exc)
            return None

        if not isinstance(status, dict):
            return None
        return parse_mblog_detail(status)


# =============================================================================
# 解析函数（模块级，便于测试）
# =============================================================================

def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_count(value: Any) -> int:
    """把微博的计数字符串转成 int。

    ⚠️ 实测微博的 `followers_count` 是**带单位的字符串**（如 `"58.8万"`），
    不是数字 —— 直接 `int()` 会炸。这里处理 万/亿/K/M 与千分位逗号。

        实测样本（2026-09-28）：
            "58.8万"    -> 588000
            "1720.1万"  -> 17201000
            608         -> 608
    """
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)

    s = str(value).strip().replace(",", "")
    if not s:
        return 0
    try:
        if "亿" in s:
            return int(float(s.replace("亿", "")) * 100_000_000)
        if "万" in s:
            return int(float(s.replace("万", "")) * 10_000)
        up = s.upper()
        if up.endswith("K"):
            return int(float(up[:-1]) * 1_000)
        if up.endswith("M"):
            return int(float(up[:-1]) * 1_000_000)
        return int(float(s))
    except (TypeError, ValueError):
        return 0


def _first_url(value: Any) -> str:
    """微博的图片/封面字段可能是 str 或 {url: ...}。"""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("url") or ""
    return ""


def parse_mblog(mb: Dict[str, Any]) -> Optional[SearchResult]:
    """把 mblog 转成统一 SearchResult。

    实测字段（70+ 个里取需要的）：
        id / mid / bid, text, created_at, user{...},
        original_pic / bmiddle_pic / thumbnail_pic, pics[],
        attitudes_count / comments_count / reposts_count, page_info
    """
    if not isinstance(mb, dict):
        return None
    mid = str(mb.get("id") or mb.get("mid") or "")
    if not mid:
        return None

    user = mb.get("user") or {}
    text_html = mb.get("text") or ""
    text = _strip_html(text_html)

    # 封面：优先第一张图的原图，其次视频封面
    cover = _first_url(mb.get("original_pic")) or _first_url(mb.get("bmiddle_pic"))
    images = _extract_images(mb)
    if not cover and images:
        cover = images[0]
    page_info = mb.get("page_info") or {}
    if not cover and isinstance(page_info, dict):
        cover = _first_url((page_info.get("page_pic") or {}))

    is_video = isinstance(page_info, dict) and page_info.get("type") == "video"
    video_url = _extract_video_url(mb) if is_video else ""

    # ⚠️ SearchResult **没有** images / video 字段（那些在 NoteDetail 里）。
    # 所以图片列表与视频地址放进 raw_data，供上层（crawler / 详情）读取。
    # 与抖音的做法一致 —— 不为了塞字段去改公共类型。
    raw = dict(mb)
    raw["_images"] = images
    raw["_video_url"] = video_url

    return SearchResult(
        id=mid,
        title=text[:80],          # 微博没有独立标题，用正文首段
        desc=text,
        author=user.get("screen_name") or "",
        author_id=str(user.get("id") or ""),
        cover=cover,
        url=f"{MOBILE_HOST}/detail/{mid}",
        platform="weibo",
        type="video" if is_video else "note",
        likes=_to_int(mb.get("attitudes_count")),
        comments=_to_int(mb.get("comments_count")),
        shares=_to_int(mb.get("reposts_count")),
        create_time=mb.get("created_at") or "",
        raw_data=raw,
    )


def parse_mblog_detail(mb: Dict[str, Any]) -> Optional[NoteDetail]:
    """把 mblog 转成统一 NoteDetail。"""
    if not isinstance(mb, dict):
        return None
    mid = str(mb.get("id") or mb.get("mid") or "")
    if not mid:
        return None

    user = mb.get("user") or {}
    text = _strip_html(mb.get("text") or "")
    images = _extract_images(mb)
    video = _extract_video_url(mb)
    page_info = mb.get("page_info") or {}
    cover = _first_url(mb.get("original_pic")) or _first_url(mb.get("bmiddle_pic"))
    if not cover and isinstance(page_info, dict):
        cover = _first_url((page_info.get("page_pic") or {}))
    if not cover and images:
        cover = images[0]

    duration = 0
    if isinstance(page_info, dict):
        try:
            duration = int(float(page_info.get("duration") or 0))
        except (TypeError, ValueError):
            duration = 0

    return NoteDetail(
        id=mid,
        title=text[:80],
        desc=text,
        author=user.get("screen_name") or "",
        author_id=str(user.get("id") or ""),
        platform="weibo",
        type="video" if video else "note",
        images=images,
        video=video,
        video_cover=cover,
        duration=duration,
        likes=_to_int(mb.get("attitudes_count")),
        comments=_to_int(mb.get("comments_count")),
        shares=_to_int(mb.get("reposts_count")),
        create_time=mb.get("created_at") or "",
        raw_data=mb,
    )


def _extract_images(mb: Dict[str, Any]) -> List[str]:
    """取微博的图片列表（**尽量取原图**）。

    ## 实测结构（2026-09-27）

        pics[0] = {
            "url":   ".../orj360/<pid>.jpg",     # 缩略图 360px
            "size":  "orj360",
            "large": {"url": ".../mw2000/<pid>.jpg",   # 2048 宽
                      "size": "large",
                      "geo": {...}},
        }
        original_pic = ".../large/<pid>.jpg"   # 真·原图（**只有第一张**）

    ## 关键规律

    `large.url` 的路径段是 `/mw2000/`，原图是 `/large/`，
    **但文件名（pid）完全相同** —— 所以每张图都能推导出原图 URL：

        https://wx4.sinaimg.cn/mw2000/<pid>.jpg   →   .../large/<pid>.jpg

    实测验证（2026-09-27）：`large` 版 1.88MB vs `mw2000` 版 962KB，
    两张都 HTTP 200 可直连下载（**下载不需要 Cookie**）。

    所以这里**优先推导原图**，推导不出来才退到 `large.url`。
    """
    out: List[str] = []
    for pic in (mb.get("pics") or []):
        if not isinstance(pic, dict):
            continue
        large = pic.get("large") or {}
        url = _first_url(large) or pic.get("url") or ""
        if not url:
            continue
        out.append(_to_original_url(url))

    if not out:
        single = _first_url(mb.get("original_pic"))
        if single:
            out.append(single)
    return out


# 微博图床的尺寸路径段 → 原图路径段
_WEIBO_SIZE_SEGMENTS = ("/mw2000/", "/mw690/", "/bmiddle/", "/orj360/", "/orj480/",
                        "/thumbnail/", "/small/", "/square/", "/thumb150/")


def _to_original_url(url: str) -> str:
    """把微博图床 URL 转成原图 URL（把尺寸段换成 `/large/`）。

    实测：`mw2000` 与 `large` 的文件名（pid）相同，只有路径段不同。
    已经是 `/large/` 或 `/original/` 的原样返回。
    """
    if not url:
        return url
    for seg in _WEIBO_SIZE_SEGMENTS:
        if seg in url:
            return url.replace(seg, "/large/", 1)
    return url


def _extract_video_url(mb: Dict[str, Any]) -> str:
    """取视频直链（优先最高清晰度）。

    实测字段（page_info.type == "video"）：
        page_info.urls.mp4_720p_mp4 / mp4_hd_mp4 / mp4_ld_mp4
        page_info.media_info.stream_url / stream_url_hd
    """
    page_info = mb.get("page_info") or {}
    if not isinstance(page_info, dict):
        return ""

    urls = page_info.get("urls") or {}
    if isinstance(urls, dict):
        for key in ("mp4_720p_mp4", "mp4_hd_mp4", "mp4_ld_mp4"):
            v = urls.get(key)
            if isinstance(v, str) and v:
                return v

    media = page_info.get("media_info") or {}
    if isinstance(media, dict):
        for key in ("stream_url_hd", "stream_url"):
            v = media.get(key)
            if isinstance(v, str) and v:
                return v
    return ""


def parse_user(u: Dict[str, Any]) -> Optional[UserProfile]:
    """把微博的 user 对象转成统一 UserProfile。

    ## 实测字段（2026-09-28，共 29 个）

        id / screen_name / description / profile_image_url / avatar_hd
        followers_count / follow_count / statuses_count
        verified / verified_reason / gender / cover_image_phone

    ⚠️ **`followers_count` 是字符串**（实测 `"58.8万"`），不是数字 ——
    要用 `parse_count` 解析。`follow_count` / `statuses_count` 是数字。
    `verified` 是 bool，`verified_reason` 是认证说明。
    """
    if not isinstance(u, dict):
        return None
    uid = str(u.get("id") or "")
    if not uid:
        return None

    return UserProfile(
        id=uid,
        name=u.get("screen_name") or "",
        avatar=u.get("avatar_hd") or u.get("profile_image_url") or "",
        platform="weibo",
        desc=u.get("description") or "",
        followers=parse_count(u.get("followers_count")),
        following=_to_int(u.get("follow_count")),
        total_videos=_to_int(u.get("statuses_count")),
        # 微博的 `like` 是"收到的赞"；取不到就 0（不编造）
        total_likes=_to_int(u.get("like")),
        verified=bool(u.get("verified")),
        raw_data={
            "verified_reason": u.get("verified_reason") or "",
            "gender": u.get("gender") or "",
            "profile_url": u.get("profile_url") or f"https://m.weibo.cn/u/{uid}",
            "cover_image_phone": u.get("cover_image_phone") or "",
            "user": u,
        },
    )


def _norm_reply(s: Any) -> Optional[Dict[str, Any]]:
    """把微博**原始**的子回复转成前端统一形状。

    ## 为什么需要（2026-10-04 实测踩到）

    微博原始子回复的结构是：

        { "text": "…", "user": {"screen_name": "…"}, "like_count": "74", … }

    **没有** `content` / `author` 字段。顶层 `get_comments_page` 原来
    直接 `"replies": <原始 dict>` 透传，于是前端拿到的每条子回复都是
    `content: null` / `author: null` —— 展开后是一片空白。

    ## 为什么之前没被发现

    因为前端点「查看 N 条回复」走的是**另一条路**
    （`/comments?parent_id=` → `get_replies`），那条路已经转好了，
    所以用户实测截图里**能正常显示内容**。
    顶层内嵌这份空壳只是"没人读"而已 —— 一旦前端改用内嵌数据
    （少发一次请求，更快），就会立刻暴露。

    ## 单一事实来源

    `get_replies` 也调这个函数 —— 两条路给前端的数据必须一致，
    否则"从顶层展开"和"点开加载"会显示不同内容。
    """
    if not isinstance(s, dict):
        return None
    u = s.get("user") or {}
    text = _strip_html(s.get("text") or "")
    author = u.get("screen_name") or ""
    if not text and not author:
        return None      # 空壳（既没内容也没作者）→ 不给前端
    return {
        "id": str(s.get("id") or ""),
        "content": text,
        "author": author,
        "author_id": str(u.get("id") or ""),
        "avatar": u.get("profile_image_url") or "",
        "likes": int(s.get("like_count") or 0),
        "create_time": _rfc2822_to_ts(s.get("created_at") or ""),
        # ⚠️ 子回复**自己没有**子回复（微博只两层）→ 0 是**真的 0**
        "reply_count": 0,
        "location": (s.get("source") or "").replace("来自", "").strip(),
        # "回复给谁"：微博**不给**独立字段，它就写在 text 里
        # （"回复@某某:"）—— 所以这里留空，前端不要再加前缀（会重复）
        "reply_to": "",
        # 博主本人回复（实测 is_mblog_author=True）—— 前端可据此标记
        "is_author_reply": bool(s.get("is_mblog_author")),
        "images": [],
        "replies": [],
    }


def _strip_html(html: str) -> str:
    """去掉微博正文里的 HTML 标签（正文是 `<a>` 包裹的富文本）。"""
    if not html:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    # 常见实体
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                 ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        text = text.replace(a, b)
    return text.strip()


def _rfc2822_to_ts(s: str) -> int:
    """微博时间字符串 → Unix 秒。

    实测格式：`"Tue Sep 29 18:18:23 +0800 2026"`（RFC2822，不是时间戳）。
    解析失败返回 0（不猜 —— 让上层显示空时间，而不是编一个）。
    """
    if not s:
        return 0
    try:
        t = time.strptime(s, "%a %b %d %H:%M:%S %z %Y")
        return int(calendar.timegm(t))
    except Exception:
        return 0
