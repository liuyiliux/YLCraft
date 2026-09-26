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

import logging
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
    SEARCH_SINGLE,
    build_search_params,
)

logger = logging.getLogger("ylcraft.platforms.douyin")


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
        """搜索抖音内容（视频 / 图文）。

        只支持 SearchType.NOTE / VIDEO；搜用户等类型在抖音是另一条链路，
        未抓包确认前不实现（不做未经验证的猜测）。
        """
        if params.search_type not in (SearchType.NOTE, SearchType.VIDEO, None):
            raise NotImplementedError(
                f"[douyin] 暂不支持搜索类型 {params.search_type}（只实现了内容搜索）"
            )

        query = build_search_params(
            keyword=params.keyword,
            offset=0,
            count=min(params.max_results or 10, 20),
        )
        data = await self._call(SEARCH_SINGLE, query)

        items = self._extract_items(data)
        results: List[SearchResult] = []
        for item in items:
            parsed = parse_search_item(item)
            if parsed is not None:
                results.append(parsed)
            if len(results) >= (params.max_results or 10):
                break
        return results

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
