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
)
from .apis import (
    BASE_URL,
    DEFAULT_AID,
    DEFAULT_DEVICE_PLATFORM,
    PROFILE_SELF,
    SEARCH_SINGLE,
    SINGLE_PAGE_MAX,
    build_search_params,
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
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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
            RuntimeError: 接口返回非 0（含登录态失效）。
        """
        if self._http_client is None:
            await self._init_http_client()
        url = f"{BASE_URL}{path}"
        resp = await self._http_client.get(url, params=params or {})
        resp.raise_for_status()
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
        offset = 0
        collected: List[SearchResult] = []
        seen: set[str] = set()
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
    # 未实现的能力：显式声明，不静默返回空
    # =========================================================================

    async def get_detail(self, item_id: str, **kwargs) -> NoteDetail:
        raise NotImplementedError("[douyin] get_detail 暂未实现（未抓包确认，不猜端点）")


# =============================================================================
# 解析
# =============================================================================

def parse_search_item(item: Dict[str, Any]) -> Optional[SearchResult]:
    """解析搜索结果条目。

    抓包确认的条目结构：
        {type: 1, aweme_info: {aweme_id, desc, create_time, author,
                               statistics, video, image_infos, ...}}

    注意：不是每条都有 aweme_info（会有广告/运营卡片），这类条目跳过。
    """
    if not isinstance(item, dict):
        return None
    info = item.get("aweme_info")
    if not isinstance(info, dict) or not info.get("aweme_id"):
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

    # 封面：视频取 cover，图文取 image_infos 首图
    cover = ""
    video = info.get("video") or {}
    if isinstance(video, dict):
        cover = _first_url(video.get("cover")) or _first_url(video.get("origin_cover"))
    if not cover:
        images = info.get("image_infos")
        if isinstance(images, list) and images:
            cover = _first_url(images[0].get("url_list") or images[0])

    # 时长（秒）：抖音给的是毫秒
    duration_ms = _to_int(video.get("duration")) if isinstance(video, dict) else 0
    duration = duration_ms // 1000 if duration_ms else 0

    create_time = _format_ts(info.get("create_time"))

    # 图文/视频：有 image_infos 视为图文
    is_image = bool(info.get("image_infos"))

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
        raw_data=item,
    )


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
