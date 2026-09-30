"""
YLCraft — 抖音平台客户端

端点由 browser-skill 接管用户已登录 Chrome 抓包确认（2026-09-26），
不是猜的；证据在 `.local/douyin-xhs-search-capture.json`（脱敏，不入库）。

实测结论：
  GET /aweme/v1/web/general/search/single/?keyword=小说&...
  → status_code=0 / has_more=1 / cursor=5
  → data[] 每项 {type, aweme_info{aweme_id, desc, author, statistics, create_time, video}}

抖音搜索**不需要** msToken/a_bogus 签名（与番茄不同），带 Cookie 即可。
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any, Dict, List, Optional

import httpx

from ..base import BasePlatformClient, register_platform
from ..types import (
    ClientConfig,
    ClientMode,
    NoteDetail,
    SearchParams,
    SearchResult,
    SearchType,
    UserProfile,
)
from .apis import (
    AWEME_DETAIL,
    BASE_URL,
    DEFAULT_AID,
    DEFAULT_CHANNEL,
    DEFAULT_DEVICE_PLATFORM,
    DEFAULT_PC_CLIENT_TYPE,
    DEFAULT_PLATFORM,
    DETAIL_BASE_URL,
    DISCOVER_SEARCH,
    PROFILE_OTHER,
    PROFILE_SELF,
    SEARCH_SINGLE,
    SINGLE_PAGE_MAX,
    USER_POST,
    USER_POST_PAGE_MAX,
    build_search_params,
    build_user_post_params,
    build_user_profile_params,
    build_user_search_params,
    resolve_search_channel,
)

logger = logging.getLogger("ylcraft.platforms.douyin")


class PlatformUnavailableError(RuntimeError):
    """平台对当前环境不可用（不是"没搜到"，是平台侧拒绝）。

    典型场景：抖音对自动化环境整体降级——搜索返回空、
    账号接口报「用户未登录」，但同一 Cookie 在真实浏览器里完全正常。

    单独定义一个异常类型，是为了让上层**不要**把它当成"搜索失败"去降级重试：
    重试只会再失败一次，并把"环境被风控"伪装成"找到 0 条结果"。
    """


class DouyinSearchRateLimited(PlatformUnavailableError):
    """抖音搜索被**速率限制**（稍等即可恢复）。

    ## 实测（2026-09-29）

        count=5  第 1 次  → 4 个 ✅
        紧接着连发多次    → 全 0 ❌
        等 ~60 秒后       → 4 个 ✅

    **响应完全正常**：HTTP 200、`status_code=0`、字段齐全，
    只是 `user_list` 为空 —— 靠响应的任何字段都判断不出被限流。

    所以用"**首次请求就返回空**"作为信号，并给**可操作**提示
    （等一会儿 / 重新登录），而不是静默返回 0 个让用户以为
    "抖音搜不了博主"。

    继承 `PlatformUnavailableError` 是为了让上层**不要**降级到
    yt-dlp 再试一次（那只会再空一次，把限流伪装成"没结果"）。
    """


@register_platform("douyin")
@register_platform("dy")
class DouyinClient(BasePlatformClient):
    """抖音客户端（API 模式）。

    Patchright 模式未实现：`search()` 会显式抛出而不是静默返回空列表，
    避免"看起来没结果、其实是没实现"这种假阴性。
    """

    def __init__(self, config: ClientConfig):
        super().__init__(config)

    # =========================================================================
    # 请求头
    # =========================================================================

    def _build_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self.config.user_agent or self._get_default_user_agent(),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.douyin.com/",
            "Origin": "https://www.douyin.com",
        }

    def _get_default_user_agent(self) -> str:
        """默认 UA。

        ⚠️ **版本号很关键**（2026-09-27 实测）：

            Chrome/154 → ✓ 正常返回
            Chrome/120 → ✗ **返回空 body（HTTP 200，len=0）**
            不带 UA    → ✓ 正常返回（httpx 默认 UA 反而能过）

        原来写的 Chrome/120 会让 `aweme/post`（用户作品列表）**静默失败**——
        响应不是 JSON，解析时报 `Expecting value: line 1 column 1`，
        看起来像"接口坏了"，实际是 UA 版本被拒。

        这里跟抓包时浏览器的真实版本保持一致。
        """
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
        )

    def _get_platform_domain(self) -> str:
        return ".douyin.com"

    # =========================================================================
    # 统一请求出口
    # =========================================================================

    async def _call(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """GET 抖音 Web API 并校验 status_code。

        Raises:
            PlatformUnavailableError: 被风控拦截（403 + ArgusSecurityPlugin）。
            RuntimeError: 接口返回非 0（含登录态失效）。

        ## 为什么要单独识别 403（2026-09-27，调研发现）

        抖音有个 **ArgusSecurityPlugin** 边缘网关，对**白名单路径**做概率性拦截
        （社区实测约 5/8 被拦）。响应体是：

            Blocked by ArgusSecurityPlugin Uifid Not Found
            Blocked by ArgusSecurityPlugin Signature Not Found

        **这是"风控失败"，不是"没有数据"。** 如果不区分，
        用户会看到"这个 UP 主没有作品"——把风控失败静默吞成空结果，
        属于最费时间的那类假阴性。

        实测（我方环境，2026-09-27）：`aweme/post` 与 `profile/other`
        目前**不带签名也能返回数据**（多次调用均 status_code=0），
        所以这条分支暂时不会触发；但网关策略会变，必须提前区分。
        """
        if self._http_client is None:
            await self._init_http_client()
        url = f"{BASE_URL}{path}"
        resp = await self._http_client.get(url, params=params or {})

        if resp.status_code == 403:
            body = (resp.text or "")[:200]
            raise PlatformUnavailableError(
                f"[douyin] 请求 {path} 被风控拦截（HTTP 403）：{body}。"
                "这是 ArgusSecurityPlugin 网关的概率性拦截（实测社区约 5/8），"
                "**不是「该用户没有数据」**——请稍后重试，或检查登录态是否失效。"
            )

        resp.raise_for_status()

        # 空 body：抖音会用「HTTP 200 + 空响应体」表示拒绝
        # （实测：UA 版本过旧时 aweme/post 就是这种表现）。
        # 不识别的话，json() 会抛 `Expecting value: line 1 column 1`，
        # 看起来像"接口坏了"，实际是请求特征被拒。
        if not (resp.text or "").strip():
            raise PlatformUnavailableError(
                f"[douyin] 请求 {path} 返回了空响应体（HTTP 200）。"
                "抖音会用这种形式表示拒绝——常见原因是 User-Agent 版本过旧"
                "（实测 Chrome/120 被拒、Chrome/154 正常），"
                "或需要重新获取登录态。**不是「该用户没有数据」**。"
            )

        data = resp.json()
        code = data.get("status_code")
        if code != 0:
            raise RuntimeError(
                f"抖音接口返回 status_code={code}"
                f"（若为登录态失效，请重新获取 Cookie）"
            )
        return data

    # =========================================================================
    # 搜索
    # =========================================================================

    async def search(self, params: SearchParams) -> List[SearchResult]:
        """搜索抖音内容（自动翻页 + 空结果重试）。

        支持的 search_type（对应抖音搜索页四个页签，URL 抓包确认）：
            note / general → 综合（视频+图文，默认）
            video          → 视频
            user           → 用户
            live           → 直播

        未实现的类型回退到「综合」，不抛错——用户选了没做完的类型时，
        给综合结果比给一句报错更有用（且前端已按后端能力收敛选项）。

        ## 为什么要翻页（2026-09-27 实测）

        用户反馈"抖音搜索显示很多，我们只有九条"。原因是原实现
        **只请求一次、count 固定 10**，所以永远只有 9~10 条。

        实测抖音接口支持 offset/count 翻页（同一 keyword 下
        offset=0/20/40 返回的 cursor 依次为 0/40/60，说明分页参数生效）。

        现在按需求条数自动翻页：单页最多 20（实测上限），
        需要更多就按 offset 递增继续取，直到够数或 has_more=0。

        ## ⚠️ 但 offset 翻页**已失效**（2026-09-28 复测）

        上面那条"offset=0/20/40 有效"是 2026-09-27 的结论，**现在不成立**：

            offset=0   count=20  -> 18 条  cursor=20  has_more=True   ✅
            offset=20  count=20  ->  0 条  cursor=40  has_more=False  ❌
            offset=5   count=5   ->  0 条  cursor=10  has_more=False  ❌

        而且**在真实浏览器里跑同样的请求，offset=20 也是 0 条** ——
        所以这是抖音的**服务端行为变化**，不是我们的代码问题，
        也不是"自动化被限制"。

        **结论：抖音目前只能拿首页（约 18 条）**。
        `page=2` 会得到 0 条（不再返回与第 1 页重复的数据，
        这比之前"两页相同"更接近真实语义 —— 确实是"没有第 2 页"）。
        代码保留 offset 递增逻辑：若抖音恢复该能力，无需改动即可生效。

        ## 为什么要重试（2026-09-26 实测，48 次采样）

        抖音搜索会**不定期**返回空 data（code=0 但 data=[]）。实测采样：

            6/6 成功 → 3 分钟后 0/6 失败 → 6/20 成功 → 15/15 成功 → 8/8 ×2 成功

        总计 48 次里 43 次成功（约 90%），且**失败后隔一会儿就能恢复**。
        重试 3 次、间隔递增（2/4/6 秒），总耗时约 12 秒。
        """
        channel = resolve_search_channel(params.search_type)
        want = max(1, params.max_results or 10)

        # 单页上限 20（实测；请求更多也不会多给）
        page_size = min(want, SINGLE_PAGE_MAX)

        # ⚠️ 必须把 `page` 换算成 offset（2026-09-28 修）
        #
        # 抖音接口没有 `page` 参数，只有 `offset`。原实现**忽略 page、
        # offset 恒从 0 开始**，于是前端点"第 2 页"会拿到和第一页
        # **完全相同**的数据（实测：两页首条 id 一样）。
        #
        # 换算：page=N（1 起）→ offset=(N-1)*page_size
        page_no = max(1, int(getattr(params, "page", 1) or 1))
        offset = (page_no - 1) * page_size

        collected: List[SearchResult] = []
        seen: set[str] = set()
        # page 模式只取"这一页"；不传 page（=1）时按 want 连续翻页
        max_pages = max(1, math.ceil(want / page_size))

        for page_idx in range(max_pages):
            query = build_search_params(
                keyword=params.keyword,
                offset=offset,
                count=page_size,
                search_channel=channel,
            )

            data = await self._call(SEARCH_SINGLE, query)
            items = self._extract_items(data)

            # 空结果重试（失败常是"一阵一阵"的，多试几次往往能过）
            # 注意：只在**第一页**重试。翻页中途为空通常是真的到底了，
            # 再重试只是白等。
            if not items and page_idx == 0:
                for delay in (2, 4, 6):
                    logger.info("[douyin] 首页搜索为空，%d 秒后重试", delay)
                    await asyncio.sleep(delay)
                    data = await self._call(SEARCH_SINGLE, query)
                    items = self._extract_items(data)
                    if items:
                        break

            if not items:
                if page_idx == 0:
                    await self._raise_if_environment_degraded()
                break  # 后续页为空 = 到底了

            for item in items:
                parsed = parse_search_item(item)
                if parsed is None or parsed.id in seen:
                    continue
                seen.add(parsed.id)
                collected.append(parsed)

            if len(collected) >= want:
                break

            # 用响应里的 cursor 推进（比自算 offset 更贴合服务端）
            cursor = data.get("cursor")
            next_offset = int(cursor) if isinstance(cursor, int) and cursor > offset \
                else offset + page_size
            if not data.get("has_more") and not cursor:
                break
            offset = next_offset
            logger.info(
                "[douyin] 已取 %d/%d 条，继续翻页 offset=%d",
                len(collected), want, offset,
            )

        # ⚠️ **给前端 `_has_more`**（2026-09-29 补）
        #
        # 原来不设 → 前端**没有「下一页」入口**（用户反映"搜索没有更多页"）。
        #
        # 但抖音这里要**如实**：实测 offset 翻页服务端已失效
        # （见方法 docstring：offset=20 返回 0 条，浏览器里也一样）。
        # 所以只有"本页拿满且有 cursor"时才说还有更多 —— 不编造。
        if collected and len(collected) >= page_size:
            collected[0].raw_data["_has_more"] = bool(data.get("has_more"))
        elif collected:
            collected[0].raw_data["_has_more"] = False

        return collected[:want]

    async def search_page(
        self,
        keyword: str,
        offset: int = 0,
        count: int = 10,
    ) -> Dict[str, Any]:
        """带分页的搜索，返回 {items, cursor, has_more}。

        抖音分页用 offset/count + 响应的 cursor/has_more（0 起，抓包确认）。
        """
        query = build_search_params(keyword=keyword, offset=offset, count=count)
        data = await self._call(SEARCH_SINGLE, query)
        raw_items = self._extract_items(data)
        items = [p for p in (parse_search_item(i) for i in raw_items) if p is not None]
        return {
            "items": items,
            "offset": offset,
            "count": len(items),
            "cursor": data.get("cursor"),
            "has_more": bool(data.get("has_more")),
        }

    async def _raise_if_environment_degraded(self) -> None:
        """空结果时判断是不是"环境被降级"，是就抛出可读错误。

        实测（2026-09-26）同一 cookie、同一时刻：
            用户真实 Chrome  → 搜索返回 5 条
            Patchright 自动化 → 搜索返回 0 条（data=[]，msg 为空）
        而**账号接口可能是正常的**（实测 user=True）——
        所以"账号正常"不能推出"搜索正常"。

        这里的判据是：**搜索返回空 + 账号接口正常** →
        说明 cookie 有效、登录态没问题，那空结果就不是"没登录"造成的，
        而是抖音对自动化环境的搜索接口作了限制。
        （如果账号接口也异常，那是 cookie 失效，走正常错误通道。）

        不区分的话，用户只会看到"找到 0 条结果"，误以为关键词没结果。
        """
        try:
            if self._http_client is None:
                await self._init_http_client()
            from .apis import BASE_URL

            resp = await self._http_client.get(
                f"{BASE_URL}{PROFILE_SELF}",
                params={"aid": DEFAULT_AID, "device_platform": DEFAULT_DEVICE_PLATFORM},
            )
            body = resp.json()
        except Exception:
            return  # 探测失败就不下结论，交给上层按"确实没结果"处理

        user = body.get("user") or {}
        cookie_ok = bool(user.get("uid"))

        if cookie_ok:
            # cookie 有效却搜不到 → 搜索接口被限制（不是"没登录"）
            raise PlatformUnavailableError(
                "[douyin] 搜索接口未返回数据（data 为空），但账号接口正常，"
                "说明 Cookie 有效、登录态没问题。"
                "实测同一 Cookie 在真实 Chrome 里能搜到结果，"
                "判断是抖音对自动化环境的搜索接口作了限制。"
                "可稍后重试（该限制时有时无），或改用其它平台采集。"
            )

        raise PlatformUnavailableError(
            "[douyin] 抖音未识别当前登录态："
            f"账号接口报「{body.get('status_msg') or '未登录'}」"
            f"（status_code={body.get('status_code')}）。"
            "请在界面重新用「浏览器」方式获取一次抖音 Cookie。"
        )

    @staticmethod
    def _extract_items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从响应里取出条目数组。

        响应结构（抓包确认）：顶层 `status_code` / `data` / `cursor` / `has_more`。
        `data` 实测是**按数字索引的对象**，不是标准数组，所以这里做了兼容；
        拿不到就返回空列表并记一条 warning——**不静默吞掉**。
        """
        raw = data.get("data")
        if isinstance(raw, dict):
            # {"0": {...}, "1": {...}} 形式
            items = [raw[k] for k in sorted(raw, key=lambda x: int(x) if x.isdigit() else 0)]
        elif isinstance(raw, list):
            items = raw
        else:
            items = []
        if not items:
            logger.warning("[douyin] 搜索响应中未取到条目（data=%s）", type(raw).__name__)
        return items

    # =========================================================================
    # 用户（搜索 / 资料 / 作品列表）——2026-09-27 实测实现
    # =========================================================================

    async def search_users(self, keyword: str, max_results: int = 20) -> List[UserProfile]:
        """按关键词搜抖音用户。

        ⚠️ 走的是 `discover/search`，**不是** general/search/single。
        实测给后者加 `search_channel=aweme_user` 完全不生效
        （返回结果与 aweme_general 一模一样）。

        实测：「美食」9 条、「李子柒」10 条。
        返回里带 `sec_uid`，是后续查资料/作品列表的必需参数。
        """
        want = max(1, max_results)
        page_size = min(want, SINGLE_PAGE_MAX)
        offset = 0
        out: List[UserProfile] = []
        seen: set[str] = set()

        while len(out) < want:
            data = await self._call(
                DISCOVER_SEARCH,
                build_user_search_params(keyword, offset=offset, count=page_size),
            )
            users = data.get("user_list") or []
            if not users:
                if offset == 0:
                    # ⚠️ **限流时不要静默返回空**（2026-09-29 实测）
                    #
                    # 抖音的 `discover/search` 有**速率限制**：
                    #
                    #     连续请求 → user_list 为空（但 HTTP 200、
                    #                status_code=0，看不出异常）
                    #     等 ~60 秒 → 又能拿到 4 个
                    #
                    # 静默返回空的话，用户看到"找到 0 个用户"，
                    # 会以为"抖音搜不了博主"或"关键词没结果"，
                    # 完全不知道"等一会儿再试就行"。
                    #
                    # 所以抛**可操作**错误。注意 status_code 仍是 0，
                    # 不能靠它判断 —— 只能用"首次请求就空"这个信号。
                    raise DouyinSearchRateLimited(
                        f"[douyin] 搜博主没有返回结果（关键词={keyword!r}）。\n"
                        "抖音对搜索有**速率限制** —— 短时间内连续搜索会被"
                        "暂时拦截（实测等待约 1 分钟即可恢复）。\n"
                        "请稍等片刻重试；若一直如此，可到「账号中心」"
                        "重新登录抖音刷新登录态。"
                    )
                break

            for entry in users:
                u = entry.get("user_info") if isinstance(entry, dict) else None
                if not isinstance(u, dict):
                    continue
                uid = str(u.get("uid") or "")
                if not uid or uid in seen:
                    continue
                seen.add(uid)
                out.append(parse_user_info(u))
                if len(out) >= want:
                    break

            if not data.get("has_more") and not data.get("cursor"):
                break
            offset += page_size

        return out[:want]

    async def get_self_profile(self) -> Optional[UserProfile]:
        """查**自己**的资料（做「我的数据」用）。

        实测（账号本人）：
            昵称=逸流AI  抖音号=46906933844
            粉丝=122  关注=3  获赞=2735  作品=22

        与 `get_user_profile(sec_uid)` 的区别：这个不需要参数，
        用当前 Cookie 的登录态。
        """
        data = await self._call(
            PROFILE_SELF,
            {"aid": DEFAULT_AID, "device_platform": DEFAULT_DEVICE_PLATFORM},
        )
        user = data.get("user")
        if not isinstance(user, dict) or not user:
            logger.warning("[douyin] profile/self 未返回 user（可能未登录）")
            return None
        profile = parse_user_info(user)
        # 自查接口给的是 uid 而非 sec_uid 时，sec_uid 也在 user 里
        return profile

    async def get_user_profile(self, sec_user_id: str) -> Optional[UserProfile]:
        """查用户资料。

        ⚠️ 参数必须是 **sec_user_id**（`MS4wLjABAAAA…`），不是数字 uid。
        实测用数字 uid 打开主页是空页面；sec_user_id 则正常。
        该方法由 B 站客户端同名方法对齐。

        实测（李子柒）：粉丝 4830万 / 关注 1 / 获赞 2.55亿 / 作品 774。
        """
        if not sec_user_id:
            return None
        data = await self._call(
            PROFILE_OTHER, build_user_profile_params(sec_user_id)
        )
        user = data.get("user")
        if not isinstance(user, dict) or not user:
            logger.warning("[douyin] 用户资料为空（sec_user_id=%s）", sec_user_id[:24])
            return None
        return parse_user_info(user)

    async def get_user_videos(
        self,
        sec_user_id: str,
        max_results: int = 20,
    ) -> List[SearchResult]:
        """取用户的作品列表（含图文与视频）。

        分页：把上次响应的 `max_cursor` 原样作为下次请求的 `max_cursor`。

        实测（李子柒）：9 条 / has_more=1 / max_cursor=1627632695000。
        """
        want = max(1, max_results)
        page_size = min(want, USER_POST_PAGE_MAX)
        cursor = 0
        out: List[SearchResult] = []
        seen: set[str] = set()

        while len(out) < want:
            data = await self._call(
                USER_POST,
                build_user_post_params(sec_user_id, max_cursor=cursor, count=page_size),
            )
            items = data.get("aweme_list") or []
            if not items:
                break

            for item in items:
                parsed = parse_search_item(item)
                if parsed is None or parsed.id in seen:
                    continue
                seen.add(parsed.id)
                out.append(parsed)
                if len(out) >= want:
                    break

            if not data.get("has_more"):
                break
            next_cursor = data.get("max_cursor")
            if not isinstance(next_cursor, int) or next_cursor == cursor:
                break
            cursor = next_cursor

        return out[:want]

    # =========================================================================
    # 详情
    # =========================================================================

    async def get_detail(self, item_id: str, **kwargs) -> NoteDetail:
        """获取作品详情（视频 / 图文）。

        三条路径，按优先级：

          1. **调用方已带 `raw`**（搜索时的原始条目）→ 直接解析，零请求。
             搜索结果的 `aweme_info` 已含详情所需的一切。

          2. **否则调真实详情接口**（2026-09-27 实测发现）：
                 GET https://www-hj.douyin.com/aweme/v1/web/aweme/detail/
             ⚠️ 域名是 `www-hj.douyin.com`，不是 www.douyin.com ——
             自己拼 www 域名会拿不到数据（这也是它长期没被找到的原因）。

          3. 接口也失败 → 抛可读错误。

        ## 图文笔记的地址选择（实测确认）

        每张图有两个地址，**别混用**：
          · `url_list`          → 压缩图（q75.webp），列表展示用
          · `download_url_list` → **原图**（实测 2160x2880），无水印下载用
        这里优先取 `download_url_list`。
        """
        raw = (kwargs or {}).get("raw")
        if raw:
            return _detail_from_raw(raw, item_id)

        params = {
            "device_platform": DEFAULT_DEVICE_PLATFORM,
            "aid": DEFAULT_AID,
            "channel": DEFAULT_CHANNEL,
            "pc_client_type": DEFAULT_PC_CLIENT_TYPE,
            "platform": DEFAULT_PLATFORM,
            "aweme_id": item_id,
        }
        data = await self._call_absolute(
            f"{DETAIL_BASE_URL}{AWEME_DETAIL}", params
        )
        detail = data.get("aweme_detail") or {}
        if not detail:
            raise RuntimeError(
                f"[douyin] 详情接口未返回 aweme_detail（status_code="
                f"{data.get('status_code')}, msg={data.get('status_msg') or '-'}）。"
                "可能是作品不存在、已删除，或需要登录态。"
            )
        return _detail_from_aweme(detail, item_id)

    async def _call_absolute(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """请求**绝对 URL**（详情接口在另一个域名上，不能走 _call 的 BASE_URL 拼接）。

        与 `_call` 的区别：不校验 status_code（详情接口有场景返回非 0
        但仍有可用数据；由调用方判断 aweme_detail 是否存在）。
        """
        if self._http_client is None:
            await self._init_http_client()
        resp = await self._http_client.get(url, params=params or {})
        resp.raise_for_status()
        return resp.json()


# =============================================================================
# 解析
# =============================================================================

def parse_search_item(item: Dict[str, Any]) -> Optional[SearchResult]:
    """解析一条作品条目（**兼容两种结构**）。

    抖音有两个接口返回作品，但**结构不同**（实测 2026-09-27）：

      · 搜索接口（general/search/single）
            `data[] = {type: 1, aweme_info: {aweme_id, desc, ...}}`
        → 作品数据**包在 `aweme_info` 里**，外层还有广告/运营卡片需跳过

      · 用户作品列表（aweme/post）
            `aweme_list[] = {aweme_id, desc, author, video, ...}`
        → **裸的 aweme 对象，没有 `aweme_info` 包装**

    早先这里只认第一种，导致 `get_user_videos()` 明明拿到 5 条数据，
    却因为解析返回 None 而被过滤成 **0 条**（表现为"这个 UP 主没有作品"）。
    现在两种都认。
    """
    if not isinstance(item, dict):
        return None

    # 优先取 aweme_info 包装；没有就认为本身就是裸 aweme 对象
    info = item.get("aweme_info")
    if not isinstance(info, dict):
        info = item
    if not info.get("aweme_id"):
        return None

    aweme_id = str(info.get("aweme_id"))
    desc = info.get("desc") or ""

    author = ""
    author_id = ""
    author_info = info.get("author")
    if isinstance(author_info, dict):
        author = author_info.get("nickname") or ""
        author_id = str(author_info.get("uid") or author_info.get("sec_uid") or "")

    # 统计：抖音放在 statistics 里，且是 dict
    stats = info.get("statistics") or {}
    likes = _to_int(stats.get("digg_count"))
    comments = _to_int(stats.get("comment_count"))
    shares = _to_int(stats.get("share_count"))
    collects = _to_int(stats.get("collect_count"))
    views = _to_int(stats.get("play_count"))

    # ⚠️ **图集的图片在 `images`，不是 `image_infos`**（2026-09-29 实测）
    #
    # 抖音搜索里的**图集**（`aweme_type=68`）：
    #
    #     image_infos   → **不是列表**（空/其它类型）
    #     images        → **10 张图**（每项 {uri, url_list}）
    #
    # 原来只读 `image_infos`，于是：
    #   · 图集被误判成 `video`（is_image=False）
    #   · 图片一张都拿不到
    #   · 「图文下载」退化成只有封面
    #
    # 两个字段都读（兼容不同接口形态），`images` 优先。
    album_images = info.get("images")
    if not (isinstance(album_images, list) and album_images):
        album_images = info.get("image_infos")

    # 封面：视频取 cover，图文取首图
    cover = ""
    video = info.get("video") or {}
    if isinstance(video, dict):
        cover = _first_url(video.get("cover")) or _first_url(video.get("origin_cover"))
    if not cover and isinstance(album_images, list) and album_images:
        first = album_images[0]
        cover = _first_url(
            (first.get("url_list") if isinstance(first, dict) else None) or first
        )

    # 时长（秒）：抖音给的是毫秒
    duration_ms = _to_int(video.get("duration")) if isinstance(video, dict) else 0
    duration = duration_ms // 1000 if duration_ms else 0

    create_time = _format_ts(info.get("create_time"))

    # 图文/视频：**优先信 `aweme_type`**（权威字段），再退回"有没有图"
    #
    #     0   = 视频
    #     68  = 图集（图文）
    #
    # 实测：纯看 `images` 也准，但 `aweme_type` 是抖音自己的标注，
    # 更可靠（图集可能一张图都没有时的边界情况）。
    aweme_type = str(info.get("aweme_type") or "")
    if aweme_type == "68":
        is_image = True
    elif aweme_type == "0":
        is_image = False
    else:
        is_image = bool(album_images)

    # ⚠️ **提取无水印视频地址**（2026-09-29 补）
    #
    # 原来是缺的 —— 搜索结果里 `type=video` 却**没有播放地址**，
    # 用户点详情播放直接失败（实测 9/9 条视频都缺）。
    #
    # 地址在 `video.play_addr.url_list`（实测 3 个候选）。
    #
    # ⚠️ **必须挑 mp4，且排除图文笔记的配乐**：
    # 实测图文笔记的 `video.play_addr` 指向的是 **mp3**（配乐），
    # 拿它当视频播会失败。
    video_url = ""
    if not is_image and isinstance(video, dict):
        for key in ("play_addr", "play_addr_h264", "play_addr_265", "download_addr"):
            addr = video.get(key)
            if not isinstance(addr, dict):
                continue
            for u in (addr.get("url_list") or []):
                s = str(u)
                if not s.startswith("http"):
                    continue
                # 排除音频（图文笔记的坑）
                if ".mp3" in s or ".m4a" in s or "audio" in s.lower():
                    continue
                video_url = s
                break
            if video_url:
                break

    return SearchResult(
        id=aweme_id,
        title=desc,  # 抖音没有独立标题，用正文首行
        author=author,
        author_id=author_id,
        cover=cover,
        url=f"https://www.douyin.com/video/{aweme_id}",
        platform="douyin",
        type="note" if is_image else "video",
        likes=likes,
        comments=comments,
        shares=shares,
        collects=collects,
        views=views,
        desc=desc,
        create_time=create_time,
        duration=duration,
        raw_data={
            **item,
            # 前端详情播放读这个（与 X / 微博的字段名统一）
            "_video_url": video_url,
            # ⚠️ **图集图片也要放这里**（2026-09-29）
            #
            # `SearchResult` 没有 images 字段，平台统一把多图放在
            # `raw_data._images`（`crawler/service.py` 从这里取，
            # 填进 `CrawlerResult.images`）。
            #
            # 原来抖音**没放** —— 于是图集：
            #   · 前端详情看不到图
            #   · 「图文下载」退化成只有封面一张
            "_images": _album_image_urls(album_images) if is_image else [],
        },
    )


def _album_image_urls(album_images: Any) -> List[str]:
    """从抖音的图集字段里取原图地址列表。

    两种形态都兼容：
        `images[]`       → {uri, url_list: [...]}
        `image_infos[]`  → 同上
    取不到的不编造（返回空）。
    """
    out: List[str] = []
    if not isinstance(album_images, list):
        return out
    for img in album_images:
        if not isinstance(img, dict):
            if isinstance(img, str) and img.startswith("http"):
                out.append(img)
            continue
        u = _first_url(img.get("url_list")) or _first_url(img)
        if u:
            out.append(u)
    return out


def _detail_from_raw(raw: Dict[str, Any], item_id: str) -> NoteDetail:
    """从搜索结果的原始条目构造详情。

    搜索响应里的 `aweme_info` 已包含详情所需的一切，所以这里不重新请求。

    能取到：
      · 描述/标题、作者、统计（赞/评/转/藏/播放）
      · 封面、时长
      · **无水印视频地址**（play_addr 优先于 download_addr）
      · 图集（image_infos 里的图片列表）

    取不到的不编造（留空）。
    """
    info = (raw or {}).get("aweme_info") or {}
    if not info:
        # 容错：调用方可能直接传了 aweme_info
        info = raw or {}

    aweme_id = str(info.get("aweme_id") or item_id or "")
    desc = info.get("desc") or ""

    author = ""
    author_id = ""
    a = info.get("author")
    if isinstance(a, dict):
        author = a.get("nickname") or ""
        author_id = str(a.get("uid") or a.get("sec_uid") or "")

    stats = info.get("statistics") or {}
    video = info.get("video") or {}
    if not isinstance(video, dict):
        video = {}

    # 无水印视频：play_addr 通常是可直链的；退而求其次用 download_addr
    video_url = ""
    for key in ("play_addr", "play_addr_h264", "download_addr"):
        video_url = _first_url(video.get(key))
        if video_url:
            break

    cover = _first_url(video.get("cover")) or _first_url(video.get("origin_cover"))

    # 图集（图文笔记）
    # ⚠️ 图集的图片在 `images`（不是 `image_infos`）—— 见 `parse_search_item`
    # 的说明。两个字段都读，`images` 优先。
    images: List[str] = _album_image_urls(info.get("images"))
    if not images:
        images = _album_image_urls(info.get("image_infos"))
    if not cover and images:
        cover = images[0]

    duration_ms = _to_int(video.get("duration"))
    # 优先信 `aweme_type`（0=视频，68=图集）
    aweme_type = str(info.get("aweme_type") or "")
    if aweme_type == "68":
        is_image = True
    elif aweme_type == "0":
        is_image = False
    else:
        is_image = bool(images)

    return NoteDetail(
        id=aweme_id,
        title=desc,
        desc=desc,
        author=author,
        author_id=author_id,
        platform="douyin",
        type="note" if is_image else "video",
        images=images,
        video=video_url,
        video_cover=cover,
        duration=duration_ms // 1000 if duration_ms else 0,
        likes=_to_int(stats.get("digg_count")),
        comments=_to_int(stats.get("comment_count")),
        shares=_to_int(stats.get("share_count")),
        collects=_to_int(stats.get("collect_count")),
        views=_to_int(stats.get("play_count")),
        create_time=_format_ts(info.get("create_time")),
        raw_data=raw,
    )


def _detail_from_aweme(detail: Dict[str, Any], item_id: str) -> NoteDetail:
    """从 aweme/detail 接口的 `aweme_detail` 构造详情。

    实测结构（图文笔记）：
        {"aweme_id","desc","create_time","author":{...},
         "statistics":{"digg_count","comment_count","share_count","collect_count"},
         "images":[{"url_list":[...], "download_url_list":[...], "width","height"}],
         "video":{"play_addr":{"url_list":[...]},"cover":{...},"duration",...}}

    图片地址优先级：**download_url_list（原图）> url_list（压缩图）**。
    实测 download_url_list 给的是 2160x2880 的原图，正是"无水印下载"要的。
    """
    aweme_id = str(detail.get("aweme_id") or item_id or "")
    desc = detail.get("desc") or ""

    author = ""
    author_id = ""
    a = detail.get("author")
    if isinstance(a, dict):
        author = a.get("nickname") or ""
        author_id = str(a.get("uid") or a.get("sec_uid") or "")

    stats = detail.get("statistics") or {}
    video = detail.get("video") or {}
    if not isinstance(video, dict):
        video = {}

    # 图集：优先原图
    images: List[str] = []
    for img in (detail.get("images") or []):
        if not isinstance(img, dict):
            continue
        url = _first_url(img.get("download_url_list")) or _first_url(img.get("url_list"))
        if url:
            images.append(url)

    # 视频地址与封面。
    #
    # ⚠️ 图文笔记**不要**取 video_url：实测它的 `video.play_addr` 指向的其实是
    #    配乐（`ies-music-hj/xxx.mp3`），当成视频地址会让前端误判成视频作品。
    #    所以有 images 时直接跳过视频地址。
    video_url = ""
    if not images:
        for key in ("play_addr", "play_addr_h264", "download_addr"):
            candidate = _first_url(video.get(key))
            # 排除音频地址（实测图文笔记的 play_addr 会是 mp3/m4a）
            if candidate and not _looks_like_audio(candidate):
                video_url = candidate
                break

    cover = _first_url(video.get("cover")) or _first_url(video.get("origin_cover"))
    if not cover and images:
        cover = images[0]

    duration_ms = _to_int(video.get("duration"))

    return NoteDetail(
        id=aweme_id,
        title=desc,
        desc=desc,
        author=author,
        author_id=author_id,
        platform="douyin",
        # 有 images 就是图文，否则是视频
        type="note" if images else "video",
        images=images,
        video=video_url,
        video_cover=cover,
        duration=duration_ms // 1000 if duration_ms else 0,
        likes=_to_int(stats.get("digg_count")),
        comments=_to_int(stats.get("comment_count")),
        shares=_to_int(stats.get("share_count")),
        collects=_to_int(stats.get("collect_count")),
        views=_to_int(stats.get("play_count")),
        create_time=_format_ts(detail.get("create_time")),
        raw_data=detail,
    )


def parse_user_info(u: Dict[str, Any]) -> UserProfile:
    """把抖音的 user / user_info 结构转成统一 UserProfile。

    两种来源的字段名一致（实测）：
      · 用户搜索：`user_list[].user_info`
      · 用户资料：`user`

    实测字段：uid, sec_uid, nickname, signature, avatar_thumb,
              follower_count, following_count, total_favorited,
              aweme_count, unique_id, custom_verify, enterprise_verify_reason

    注意 `sec_uid` 放在 raw_data 里（后续查作品列表要用它）。
    """
    return UserProfile(
        id=str(u.get("uid") or ""),
        name=u.get("nickname") or "",
        avatar=_first_url(u.get("avatar_thumb")) or _first_url(u.get("avatar_168x168")),
        platform="douyin",
        followers=_to_int(u.get("follower_count")),
        following=_to_int(u.get("following_count")),
        total_likes=_to_int(u.get("total_favorited")),
        total_videos=_to_int(u.get("aweme_count")),
        desc=u.get("signature") or "",
        # 认证：自定义认证文案或企业认证文案非空即视为已认证
        verified=bool(u.get("custom_verify") or u.get("enterprise_verify_reason")),
        raw_data={
            "sec_uid": u.get("sec_uid") or "",
            "unique_id": u.get("unique_id") or "",
            "custom_verify": u.get("custom_verify") or "",
            "enterprise_verify_reason": u.get("enterprise_verify_reason") or "",
            "short_id": u.get("short_id") or "",
            "user": u,
        },
    )


def _looks_like_audio(url: str) -> bool:
    """判断地址是不是音频文件。

    实测坑：图文笔记的 `video.play_addr` 指向的是**配乐**
    （`lf9-music-east.douyinstatic.com/obj/ies-music-hj/xxx.mp3`），
    把它当视频地址会让前端误判成视频作品。
    """
    low = (url or "").lower()
    return any(ext in low for ext in (".mp3", ".m4a", ".aac", "ies-music"))


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _first_url(value: Any) -> str:
    """抖音的封面字段常是 {url_list: [...]}，取第一个可直接访问的地址。"""
    if isinstance(value, dict):
        value = value.get("url_list")
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            return str(first.get("url") or "")
        return str(first)
    return ""


def _format_ts(ts: Any) -> str:
    """抖音 create_time 是秒级时间戳。"""
    import datetime as _dt

    try:
        return _dt.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""
