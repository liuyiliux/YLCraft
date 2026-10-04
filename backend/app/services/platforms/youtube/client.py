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
    ContentNotFoundError,
    LoginExpiredError,
    NetworkError,
    NoteDetail,
    RiskControlError,
    SearchParams,
    SearchResult,
    UserProfile,
)
from .apis import DURATION_BOUNDS, build_search_url, parse_video_id

logger = logging.getLogger("ylcraft.platforms.youtube")


# -----------------------------------------------------------------------------
# 人机校验（"Sign in to confirm you're not a bot"）
# -----------------------------------------------------------------------------
#
# ⚠️⚠️ **这不是我们代码的问题，也不是"平台不支持评论"**（2026-10-04 实测澄清）
#
# 错误信息直译是"登录以确认你不是机器人"，容易误判成"必须登录才能看评论"。
# 实测结论是**反的**：不需要登录就能拿到评论，只要那个视频没被拦。
#
# 同一 IP、同一分钟、同一份代码（yt-dlp 默认 client、无 cookie）：
#
#     搜索        njK0eebUsQw ✅16  dQw4w9WgXcQ ✅299
#                 9bZkp7q19f0 ✅257  BaW_jenozKc ✅7
#     watch 页    dQw4w9WgXcQ ✅ 2,400,000 条评论
#                 njK0eebUsQw / 9bZkp7q19f0 ❌ not a bot
#
# → 搜索 4/4 全通说明**不是**全局 IP 封禁；失败是**按视频**的。
# 扩大到 8 个视频（含 Despacito / Adele Hello / Happy 这类顶流）：
# 成功 **1/8**，唯一成功的是 240 万播放的那条。
#
# 已逐个试过、能想到的技术手段，**全部无效**（所以不要让后来人再试一遍）：
#
#     player_client = web / web_safari / web_embedded / android / ios /
#                     tv / mweb        → 7 个全试过，失败视频一律失败
#     player_skip   = webpage          → 跳过 HTML 直连 innertube，仍失败
#                     js,webpage,html   → 仍失败
#     cookiesfrombrowser = edge        → cookie 读得到，仍失败
#     **PO Token**（bgutil 2.0.1）      → **也无效**，见下
#
# ⚠️ PO Token 是 2025 年后 YouTube 反爬的真正开关，按 client 类型签发。
# 本项目**真的装了测**（git clone + npm ci + npx tsc + 起了 HTTP server，
# /ping 返回 `{"version":"2.0.1"}`），两种模式都试了：
#
#     bgutil:script-node  失败视频 仍 not a bot；dQw4w9WgXcQ 变成 no formats
#     bgutil:http         失败视频 仍 not a bot；dQw4w9WgXcQ 变成 no formats
#
# 官方文档原话（提前说过）："Providing a PO token does **not** guarantee
# bypassing 403 errors or bot checks, but it _may_ help" —— 实测确认。
# 配 `player_client=web` 时它**反而把能用的视频也弄坏**（少 format）。
#
# ⚠️ `web_embedded` / `mweb` **有副作用**：它们会把本来能用的
# dQw4w9WgXcQ 也弄坏（`Requested format is not available`）。
# 所以它们**不能**当后备方案 —— 这条也写进 meta，别再上。
#
# ## 精确定位（直连 watch 页看 HTML，2026-10-04）
#
# 同一 IP、同一分钟、同一个 urllib 请求：
#
#     dQw4w9WgXcQ   HTTP 200  1,298,628 字节   playabilityStatus = **OK**
#                   含 'not a bot' = False
#     njK0eebUsQw   HTTP 200  1,228,029 字节   playabilityStatus = **LOGIN_REQUIRED**
#                   含 'not a bot' = **True**
#
# 两个都是 **HTTP 200**、都带 `videoDetails` 和 `ytInitialData` ——
# 也就是说**页面拿全了，是 YouTube 在页面里把这条视频标成 LOGIN_REQUIRED**。
# 所以不是"连不上""被重定向""cookie 没带对"，而是**服务端按视频做的判定**。
# 没有可绕的客户端侧开关。
#
# 结论：只能靠**等 / 换出口 IP / 在浏览器里打开那条视频完成人机校验**。
# 所以按 `RiskControlError` 抛（→ 上层 429），而不是裸 RuntimeError（→ 500）：
# 500 在语义上是"我们坏了"，429 才是"平台侧拒绝，等一等或换 IP"。

_BOT_CHECK_MARK = "not a bot"

#: 供 meta / 文档引用的实测结论（单条，不重复写）
BOT_CHECK_FACTS = {
    "measured_on": "2026-10-04",
    "search_ok": "4/4",
    "watch_ok": "1/8",
    "client_variants_tried": 7,
    "skip_webpage": "无效",
    "cookies_from_browser": "无效（edge cookie 可读）",
    # 实测装了 bgutil 2.0.1（HTTP server + script 两种模式）→ 仍失败
    "po_token": "无效（bgutil 2.0.1，两种模式实测）",
    "http_status": 200,
    "playability": "LOGIN_REQUIRED",
    "remedy": "等待 / 更换出口 IP / 在浏览器打开该视频完成人机校验",
}


def _is_bot_check(msg: str) -> bool:
    """判断 yt-dlp 的错误是不是人机校验。

    ⚠️ 匹配必须**紧**。yt-dlp 会在这句话后面拼一大段 cookie 教程
    （`Use --cookies-from-browser or --cookies for the authentication`），
    且不同版本的措辞有差异（`You're` / `you’re` 的弯引号）。
    所以只认 "not a bot" 这个稳定片段，**不要**去匹配整句 ——
    否则 `Sign in to confirm your age`（年龄限制）会误判成机器人校验，
    而这两者的处置完全相反（换 IP 没用 vs 需要登录/成人验证）。
    """
    low = (msg or "").lower()
    return _BOT_CHECK_MARK in low


def _bot_check_error(vid: str, action: str) -> RiskControlError:
    """构造人机校验异常（搜索 / 详情 / 评论共用同一段事实，避免各写各的）。

    ⚠️ 文案要**说真话**：不能写"请重新登录"（实测不需要登录就能取），
    也不能只丢一句英文（用户看不懂、也不知道下一步干什么）。
    所以带上"同一 IP 下别的视频能取"这个反证 + 具体处置办法。
    """
    f = BOT_CHECK_FACTS
    return RiskControlError(
        f"[youtube] {action}被 YouTube 人机校验拦截（视频 {vid}）。\n"
        f"这不是「视频不存在」，也不是「必须登录才能看」——"
        f"同一 IP 下其它视频能正常{action}"
        f"（{f['measured_on']} 实测 {f['watch_ok']}）。\n"
        f"YouTube 在返回的页面里把这条视频标成了 "
        f"playabilityStatus={f['playability']}（HTTP {f['http_status']}，"
        f"页面本身是全的），所以是**按视频**判的，客户端侧没有开关可绕。\n"
        f"已试过且无效：{f['client_variants_tried']} 种 player_client、"
        f"跳过网页直连 API、读本机浏览器 cookie、"
        # ⚠️ 下面**不**直接插 f['po_token']：那条值自带括号
        # （"无效（bgutil 2.0.1，…）"），嵌进来会变成
        # "（无效（…））"。用户看到的是错误信息，不能让它难读。
        f"**PO Token**（bgutil 2.0.1 两种模式实测，仍失败）。\n"
        f"可行的办法：{f['remedy']}。"
    )


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

    async def get_comments(
        self,
        item_id: str,
        max_results: int = 20,
        page: int = 1,
        cursor: str = "",
    ) -> List[Dict[str, Any]]:
        """取视频评论（走 yt-dlp 的 innertube 实现）。

        ## ⚠️ 为什么用 yt-dlp（2026-10-01 调研 + 实测确认）

        自己调 innertube `/youtubei/v1/next` 理论上可行，但：
          · YouTube 正在从 `commentRenderer` 迁到 `commentViewModel`
            + `frameworkUpdates.entityBatchUpdate.mutations` 实体表
          · 两套格式要同时维护，且会随 YouTube 改动持续返工
          · yt-dlp **两套都实现了**
        实测自造 continuation token 拿不到评论（HTTP 200 但 14KB 无评论字段）
        —— 那只是 yt-dlp 的兜底路径，主路径是从 watch 页 `ytInitialData` 取。

        ## ⚠️⚠️ 最关键的一条：必须设 `max_comments` 上限

        不设就是**无上限**，会一直翻页到取完。实测某视频报
        ~10,631,705 条评论，不设上限跑了 **10 分钟没停**，只能杀掉。
        这里按 `max_results` 严格限制（另加安全上限 MAX）。

        ## 耗时（实测，同一视频）

            顶层 100 条 → 4.5s
            顶层 500 条 → 17.25s
            带回复       → 显著变慢（每条回复线程额外一次请求）

        所以**默认只取顶层**（max_replies=0），回复靠前端按需再取。

        ## 不需要 API key / 不需要登录

        实测未传 cookie、未传 key 直接取到 100 条。
        """
        import asyncio

        import yt_dlp

        vid = str(item_id or "").strip()
        if not vid:
            return []

        # ⚠️ 安全上限：即便调用方要很多，也不超过这个数（防跑飞）
        MAX_SAFE = 200
        want = min(max(1, int(max_results or 20)), MAX_SAFE)

        def _run():
            opts = _ydl_opts(flat=False)   # ⚠️ flat 模式没有 comments
            opts["getcomments"] = True
            opts["extractor_args"] = {
                "youtube": {
                    # 五段语义：max_comments, max_parents, max_replies,
                    #           max_replies_per_thread, max_depth
                    "max_comments": [str(want), str(want), "0", "10", "1"],
                    # 默认只要顶层（回复靠按需再取，省时间）
                    "comment_sort": ["top"],
                }
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(
                    f"https://www.youtube.com/watch?v={vid}", download=False
                )

        try:
            info = await asyncio.to_thread(_run)
        except Exception as exc:
            msg = str(exc)
            if "timed out" in msg.lower() or "connect" in msg.lower():
                raise NetworkError(
                    f"[youtube] 取评论时无法连接（{type(exc).__name__}）。"
                    "请确认 VPN 已开启。"
                ) from exc
            # ⚠️ 顺序要紧：人机校验**必须排在** NetworkError 之后 ——
            # 它的提示语里含 "authentication"/"cookies"，但不含
            # "timed out"/"connect"，实际不会撞；这里写明顺序是为了
            # 以后有人往 _run 里加重试参数时不会踩。
            if _is_bot_check(msg):
                raise _bot_check_error(vid, "取评论") from exc
            raise RuntimeError(f"[youtube] 取评论失败: {msg[:200]}") from exc

        if not info:
            return []

        out: List[Dict[str, Any]] = []
        for c in info.get("comments") or []:
            if not isinstance(c, dict):
                continue
            # ⚠️ 顶层评论 parent == "root"；回复的 parent 是父评论 id
            parent = c.get("parent")
            if parent != "root":
                continue   # 默认只要顶层
            ts = c.get("timestamp")
            create_time = ""
            if isinstance(ts, (int, float)) and ts > 0:
                import datetime as _dt

                try:
                    create_time = _dt.datetime.fromtimestamp(int(ts)).isoformat()
                except Exception:
                    create_time = ""
            out.append({
                "id": str(c.get("id") or ""),
                "content": c.get("text") or "",
                "author": c.get("author") or "",
                "author_id": c.get("author_id") or "",
                "avatar": c.get("author_thumbnail") or "",
                "likes": int(c.get("like_count") or 0),
                # ⚠️ yt-dlp 的 timestamp 是**估算值**（源码标了 FIXME），
                #    精度只到月/年 —— 如实给，不假装精确
                "create_time": create_time,
                "reply_count": 0,   # yt-dlp 返回平铺列表，无回复计数
                "location": "",
                "replies": [],
                "_time_text": c.get("_time_text") or "",   # 原始相对时间文本
                "_is_pinned": bool(c.get("is_pinned")),
            })
        return out[:want]

    async def get_comments_page(
        self,
        item_id: str,
        max_results: int = 20,
        page: int = 1,
        cursor: str = "",
    ) -> Dict[str, Any]:
        """取**一页** YouTube 评论。

        ⚠️ **没有真游标**：yt-dlp 一次把评论都取回来了（`max_comments` 控制），
        我们只能在本地切片。所以这里的 `next_cursor` 用**偏移量**表示
        （`"offset=20"` 这种形式），上层原样传回来即可继续。

        这样前端"加载更多"能正常工作，且**不会重复请求** yt-dlp
        （真游标要重新跑 yt-dlp，很慢）。
        """
        vid = str(item_id or "").strip()
        if not vid:
            return {"comments": [], "has_more": False, "next_cursor": "", "total": 0}

        # 解析偏移量（我们自己约定的格式）
        start = 0
        if cursor and cursor.startswith("offset="):
            try:
                start = int(cursor.split("=", 1)[1])
            except ValueError:
                start = 0

        want = max(1, int(max_results or 20))
        # 一次取到 start+want（yt-dlp 的调用成本高，别为 20 条跑两遍）
        fetch_n = min(start + want, 200)
        all_comments = await self.get_comments(vid, max_results=fetch_n)

        page_items = all_comments[start:start + want]
        nxt = start + len(page_items)
        has_more = nxt < len(all_comments)
        return {
            "comments": page_items,
            "has_more": has_more,
            "next_cursor": f"offset={nxt}" if has_more else "",
            "total": len(all_comments),
        }

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
                # ⚠️ `NetworkError`（不是裸 RuntimeError）——
                # 它声明 retryable=True / should_fallback=True，
                # 上层据此知道"这是网络问题，可以重试/降级"（2026-10-01）
                raise NetworkError(
                    f"[youtube] 无法连接 YouTube（{type(exc).__name__}）。"
                    "请确认 VPN 已开启且模式为全局/TUN（PAC 模式下 python 进程"
                    "可能不走代理）。"
                ) from exc
            # 搜索页也会被拦（实测当时 4/4 能过，但换 IP / 换时段不保证）。
            # 这里同样按风控抛 —— 别让用户以为是"搜不到这个词"（静默空结果）。
            if _is_bot_check(msg):
                raise _bot_check_error("搜索结果", "搜索") from exc
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
                raise NetworkError(
                    f"[youtube] 无法连接 YouTube（{type(exc).__name__}）。请确认 VPN 已开启。"
                ) from exc
            if "unavailable" in msg.lower() or "private" in msg.lower():
                # 内容确实没了 → 重试无意义（也不该降级到 yt-dlp）
                raise ContentNotFoundError(
                    f"[youtube] 视频不可用或已删除（id={vid}）"
                ) from exc
            # ⚠️ 必须排在 unavailable 之后：yt-dlp 对同一个视频可能同时
            # 报两者，但"视频被删了"和"被风控拦截"给用户的处置完全不同
            # （前者没救，后者换 IP 有救）。
            if _is_bot_check(msg):
                raise _bot_check_error(vid, "取详情") from exc
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

    async def get_user_videos(self, user_id: str, max_results: int = 20) -> List[SearchResult]:
        """频道视频列表（**路由用的方法名**）。

        ⚠️ `users.py::/users/videos` 调的是 `get_user_videos`，
        而基类里同类能力叫 `get_user_notes`。两个名字都提供，
        避免"实现了但路由找不到"——

        实测踩过：只写 `get_user_notes` 时 `/users/videos` 报
        `'YoutubeClient' object has no attribute 'get_user_videos'` → 500。
        """
        return await self.get_user_notes(user_id, max_results=max_results)

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
