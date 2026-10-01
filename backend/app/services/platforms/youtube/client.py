"""YLCraft — YouTube 客户端（yt-dlp 实现，2026-10-01 实测打通）。

## 为什么是 yt-dlp 而不是自己逆向 innertube

网络通之后（用户开 VPN），yt-dlp 是现成且久经考验的路径：
项目下载链路一直在用它，签名 / innertube API / 客户端轮换
它内部全处理了。自己逆向 YouTube 的 API 是无底洞。

## 实测（2026-10-01，VPN 环境）

    ytsearch5:python tutorial               → 5 条（相关度）
    .../results?...&sp=EgIIAQ%3D%3D         → 54 条（最新，首条 92s 新视频）
    .../results?...&sp=CAMSAhAB             → 479 条（播放量，首条 4937万）
    https://www.youtube.com/@freecodecamp/videos → 1724 条

三个排序**首条互不相同** → 排序真实生效。

## 已知边界（如实，不隐藏）

  · extract_flat 模式拿不到完整统计（部分字段 view_count 为 None）；
    评论区 / 字幕不在这里的职责内。
  · duration 过滤：`sp=` 与排序参数**互斥**（YouTube 只认一个 sp），
    所以「排序 + 时长」组合时时长在**客户端按 duration 字段过滤**。
  · 翻页：yt-dlp 的 flat 搜索一次给全量（~400+ 条），客户端分页切片。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..base import BasePlatformClient, register_platform
from ..types import (
    ClientConfig,
    LoginExpiredError,
    NoteDetail,
    SearchParams,
    SearchResult,
    UserProfile,
)
from .apis import DURATION_BOUNDS, build_search_url, parse_video_id

logger = logging.getLogger("ylcraft.platforms.youtube")


def _ydl_opts(flat: bool = True) -> Dict[str, Any]:
    """yt-dlp 公共选项。

    ⚠️ 不要在这里加 `proxy`——用户 VPN 是系统级的（TUN/增强模式），
    yt-dlp 走系统网络即可。如果将来要支持显式代理，从 config.proxy 传。
    """
    opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 25,
        # 实测部分环境需要带 UA（裸 python-requests UA 会被拒）
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        },
    }
    if flat:
        opts["extract_flat"] = True
    return opts


def _entry_to_result(e: Dict[str, Any]) -> Optional[SearchResult]:
    """把 yt-dlp 的 flat entry 转成统一 SearchResult。

    flat 模式字段不全（view_count 可能为 None）—— 如实置 0，
    不猜。`get_detail` 会补全。

    ⚠️ **播放列表要过滤**（实测踩过）：搜索结果的 flat entries 里
    会混入 `PL...` 开头的播放列表卡片（id 形如
    `PLTjRvDozrdlx...`，duration=None）—— 它们不是视频，
    详情页打不开。判据：**视频 ID 恰好 11 位**（YouTube 的
    video id 固定 11 字符），`PL` 开头的列表 id 是几十位。
    """
    vid = e.get("id") or ""
    # 视频 ID 固定 11 位；PL/OL/UU 等列表前缀的 id 远长于 11
    if len(vid) != 11 or vid.startswith(("PL", "OL", "UU", "RD")):
        return None
    title = (e.get("title") or "").strip()
    # flat entry 的 url 可能就是 watch 链接；没有就自己拼
    url = e.get("url") or f"https://www.youtube.com/watch?v={vid}"
    duration = int(e.get("duration") or 0)
    views = int(e.get("view_count") or 0)
    return SearchResult(
        id=vid,
        platform="youtube",
        type="video",
        title=title or "(无标题)",
        author=e.get("channel") or e.get("uploader") or "",
        author_id=e.get("channel_id") or e.get("uploader_id") or "",
        cover=(e.get("thumbnails") or [{}])[-1].get("url", "")
        if isinstance(e.get("thumbnails"), list) else (e.get("thumbnail") or ""),
        url=url if url.startswith("http") else f"https://www.youtube.com/watch?v={vid}",
        views=views,
        duration=duration,
        desc=(e.get("description") or "")[:300],
        create_time=_fmt_upload_date(e.get("upload_date")),
        raw_data={"_source": "yt_dlp_flat", "entry": {k: e.get(k) for k in (
            "id", "title", "duration", "view_count", "channel", "channel_id",
            "upload_date", "url",
        )}},
    )


def _fmt_upload_date(d: Optional[str]) -> str:
    """yt-dlp 的 upload_date 是 'YYYYMMDD'，转 ISO。"""
    if d and len(d) == 8 and d.isdigit():
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return ""


def _duration_pass(duration_sec: int, duration_key: str) -> bool:
    bounds = DURATION_BOUNDS.get(duration_key)
    if not bounds:
        return True
    lo, hi = bounds
    return lo <= duration_sec < hi


@register_platform("youtube")
class YoutubeClient(BasePlatformClient):
    """YouTube 采集客户端（yt-dlp）。"""

    def _build_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self._get_default_user_agent(),
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
        }

    def _get_default_user_agent(self) -> str:
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )

    def _get_platform_domain(self) -> str:
        return ".youtube.com"

    # =========================================================================
    # 搜索
    # =========================================================================

    async def search(self, params: SearchParams) -> List[SearchResult]:
        """搜索 YouTube 视频。

        search_type / sort_by 语义（实测见模块 docstring）：
          · sort_by: relevance(默认) / date(最新) / viewcount(播放量)
          · params.extra.duration: short / medium / long（客户端过滤）
          · params.page: 客户端分页（flat 一次取回，切片）
        """
        keyword = (params.keyword or "").strip()
        if not keyword:
            return []

        sort = (params.sort_by or "relevance").strip().lower()
        if sort in ("", "default", "general", "hot", "totalrank"):
            sort = "relevance"
        # note / video 类型都按视频搜
        duration = str((params.extra or {}).get("duration") or "")
        page = max(1, int(params.page or 1))
        want = max(1, int(params.max_results or 20))

        url = build_search_url(keyword, sort=sort, duration=duration)
        # 排序 + 时长组合时 YouTube 只认一个 sp → 用排序 URL，
        # 时长交给客户端过滤（取回更多条再筛）
        fetch_n = want * page * (4 if duration else 1) + 20

        entries = await self._extract_entries(url, fetch_n)
        results: List[SearchResult] = []
        for e in entries:
            r = _entry_to_result(e)
            if r is None:
                continue
            if duration and not _duration_pass(r.duration, duration):
                continue
            results.append(r)

        # 客户端分页
        start = (page - 1) * want
        paged = results[start:start + want]
        # has_more 放第一条的 raw_data（与其它平台约定一致）
        if paged:
            paged[0].raw_data["_has_more"] = len(results) > start + want
            paged[0].raw_data["_total"] = len(results)
        return paged

    async def _extract_entries(self, url: str, n: int = 20) -> List[Dict[str, Any]]:
        """跑 yt-dlp（在线程池里，避免阻塞事件循环）。"""
        import asyncio
        import yt_dlp

        def _run():
            opts = _ydl_opts(flat=True)
            opts["playlistend"] = max(n, 20)
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            info = await asyncio.to_thread(_run)
        except Exception as exc:
            msg = str(exc)
            # 网络断 / VPN 关了是最常见的失败，给可操作提示
            if "timed out" in msg.lower() or "connect" in msg.lower() or "resolve" in msg.lower():
                raise RuntimeError(
                    f"[youtube] 无法连接 YouTube（{type(exc).__name__}）。"
                    "请确认 VPN 已开启且模式为全局/TUN（PAC 模式下 python 进程"
                    "可能不走代理）。"
                ) from exc
            raise RuntimeError(f"[youtube] 搜索失败: {msg[:200]}") from exc

        if not info:
            return []
        entries = info.get("entries") or []
        return [e for e in entries if e]

    # =========================================================================
    # 详情
    # =========================================================================

    async def get_detail(self, item_id: str, **kwargs) -> NoteDetail:
        """取视频完整元数据（非 flat），含无水印封面/描述/统计。

        ⚠️ 这里**不返回 video 直链**（YouTube 的流是分段加密的，
        直链几分钟就失效）——下载走 /api/v1/download 的 yt-dlp 链路
        （它本来就支持 YouTube，见 download.py::_download_with_ytdlp）。
        """
        vid = parse_video_id(item_id)
        import asyncio
        import yt_dlp

        def _run():
            opts = _ydl_opts(flat=False)
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)

        try:
            info = await asyncio.to_thread(_run)
        except Exception as exc:
            msg = str(exc)
            if "timed out" in msg.lower() or "connect" in msg.lower():
                raise RuntimeError(
                    f"[youtube] 无法连接 YouTube（{type(exc).__name__}）。请确认 VPN 已开启。"
                ) from exc
            if "unavailable" in msg.lower() or "private" in msg.lower():
                raise RuntimeError(f"[youtube] 视频不可用或已删除（id={vid}）") from exc
            raise RuntimeError(f"[youtube] 详情获取失败: {msg[:200]}") from exc

        if not info:
            raise RuntimeError(f"[youtube] 未取到视频信息（id={vid}）")

        return NoteDetail(
            id=info.get("id") or vid,
            platform="youtube",
            type="video",
            title=info.get("title") or "",
            desc=(info.get("description") or "")[:2000],
            author=info.get("channel") or info.get("uploader") or "",
            author_id=info.get("channel_id") or info.get("uploader_id") or "",
            images=[info.get("thumbnail") or ""] if info.get("thumbnail") else [],
            # ⚠️ 不给 video 直链（分段流，几分钟失效）——下载走 /download
            video="",
            video_cover=info.get("thumbnail") or "",
            duration=int(info.get("duration") or 0),
            views=int(info.get("view_count") or 0),
            likes=int(info.get("like_count") or 0),
            comments=int(info.get("comment_count") or 0),
            create_time=_fmt_upload_date(info.get("upload_date")),
            tags=list((info.get("tags") or [])[:20]),
            raw_data={"_source": "yt_dlp_full", "_page_url": f"https://www.youtube.com/watch?v={vid}"},
        )

    # =========================================================================
    # 用户维度（频道）
    # =========================================================================

    async def search_users(self, keyword: str, max_results: int = 20) -> List[UserProfile]:
        """搜频道。

        实测（2026-10-01）：`sp=EgIQAg%3D%3D`（type=channel）返回
        `UC...` 频道条目：
            Python Arabic Community / Python Programmer / Python ...

        ⚠️ 频道 ID 是 **`UC` 开头 24 位**，与视频 ID（11 位）不同 ——
        解析时不要套用视频那条判据。
        """
        kw = (keyword or "").strip()
        if not kw:
            return []
        from urllib.parse import quote_plus

        url = (
            "https://www.youtube.com/results?search_query="
            f"{quote_plus(kw)}&sp=EgIQAg%253D%253D"
        )
        entries = await self._extract_entries(url, max_results)

        out: List[UserProfile] = []
        for e in entries:
            cid = str(e.get("id") or "")
            # 频道 ID：UC + 22 位；不是就跳过（可能混入视频/播放列表）
            if not cid.startswith("UC") or len(cid) != 24:
                continue
            out.append(UserProfile(
                id=cid,
                name=(e.get("title") or "").strip(),
                platform="youtube",
                avatar=(e.get("thumbnails") or [{}])[-1].get("url", "")
                if isinstance(e.get("thumbnails"), list) else "",
                # flat 拿不到粉丝数 —— 如实置 0（get_user_profile 才有）
                followers=0,
                desc=(e.get("description") or "")[:200],
            ))
            if len(out) >= max_results:
                break
        return out

    async def get_user_profile(self, user_id: str) -> UserProfile:
        """频道资料。user_id 支持 @handle / UC... 频道 ID / 完整 URL。

        ⚠️ `UC...`（24 位）走 `/channel/`，handle 走 `/@handle` ——
        拼错会 404（与 `get_user_notes` 同一个坑）。
        """
        import asyncio
        import yt_dlp

        handle = user_id.strip()
        if handle.startswith("http"):
            url = handle
        elif handle.startswith("UC") and len(handle) == 24:
            url = f"https://www.youtube.com/channel/{handle}"
        else:
            if not handle.startswith("@"):
                handle = f"@{handle}"
            url = f"https://www.youtube.com/{handle}"

        def _run():
            opts = _ydl_opts(flat=True)
            opts["playlistend"] = 1
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        info = await asyncio.to_thread(_run)
        if not info:
            raise RuntimeError(f"[youtube] 频道不存在或不可访问（{user_id}）")
        return UserProfile(
            id=info.get("channel_id") or info.get("uploader_id") or "",
            name=info.get("channel") or info.get("uploader") or "",
            avatar=info.get("thumbnails") and (info["thumbnails"] or [{}])[-1].get("url", "") or "",
            platform="youtube",
            followers=int(info.get("channel_follower_count") or 0),
            total_videos=int(info.get("playlist_count") or 0),
            desc=(info.get("description") or "")[:300],
        )

    async def get_user_notes(self, user_id: str, max_results: int = 20) -> List[SearchResult]:
        """频道视频列表。

        ⚠️ **频道 ID 与 handle 是两种不同的标识**（实测踩过）：
          · `UC68KSmHePPePCjW4v57VPQg` → 必须走 `/channel/{id}/videos`
          · `@freecodecamp` / `freecodecamp` → 走 `/{handle}/videos`
        把 `UC...` 当成 handle 拼成 `@UC...` 会 **404**（实测）。
        """
        handle = user_id.strip()
        if handle.startswith("http"):
            url = handle.rstrip("/") + "/videos"
        elif handle.startswith("UC") and len(handle) == 24:
            # 频道 ID —— 走 /channel/ 路径
            url = f"https://www.youtube.com/channel/{handle}/videos"
        else:
            if not handle.startswith("@"):
                handle = f"@{handle}"
            url = f"https://www.youtube.com/{handle}/videos"

        entries = await self._extract_entries(url, max_results)
        out = []
        for e in entries[:max_results]:
            r = _entry_to_result(e)
            if r:
                out.append(r)
        return out
