"""
YLCraft — 素材采集服务
使用新的 platforms 模块进行多平台视频/图文素材搜索与采集
支持平台：小红书、B站、抖音、快手、微博
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional

from pydantic import BaseModel, Field

from app.services.crawler.models import NoteDetail, SearchFilter, SearchEnhancedRequest, NoteDetailResponse, FetchNoWatermarkRequest
# 平台"当前环境不可用"（如抖音对自动化降级）——要原样抛给上层，
# 不能被当成"搜索失败"降级重试（那样会把风控伪装成"0 条结果"）。
from app.services.platforms.douyin.client import PlatformUnavailableError
from app.services.platforms.types import LoginExpiredError

logger = logging.getLogger("ylcraft.crawler")

# =============================================================================
# 数据模型
# =============================================================================

class CrawlerPlatform:
    """支持的平台列表"""
    # 国内平台
    XHS = "xhs"      # 小红书
    DOUYIN = "dy"     # 抖音
    KUAISHOU = "ks"  # 快手
    BILIBILI = "bili" # B站
    WEIBO = "wb"      # 微博
    # ZHIHU 已移除（2026-10-01 用户要求）。

class SearchRequest(BaseModel):
    """搜索请求"""
    platform: str = Field(..., description="平台: xhs/dy/ks/bili/wb")
    keyword: str = Field(..., description="搜索关键词")
    max_results: int = Field(20, description="最大结果数", ge=1, le=100)
    crawl_type: str = Field("search", description="采集类型")
    # 平台连接 ID：后端据此取 Cookie。
    #
    # ⚠️ 缺了它抖音会退化成游客态（status_code=2483）→ **结果恒为空**。
    #    画布的 platform_search 节点走 /crawler/search（本模型），
    #    此前没有这个字段，于是画布搜抖音一直是 0（2026-09-27 修）。
    conn_id: str = Field("", description="平台连接 ID（用于取登录态）")

class CrawlerResult(BaseModel):
    """采集结果项"""
    id: str = Field(..., description="内容ID")
    platform: str = Field(..., description="平台")
    type: str = Field("video", description="content type: video/image/article/audio")
    title: str = Field("", description="标题")
    desc: Optional[str] = Field(None, description="描述")
    cover: str = Field("", description="封面图URL")
    video_url: str = Field("", description="视频URL")
    images: list[str] = Field(default_factory=list, description="image URL list")
    author: str = Field("", description="作者")
    author_id: str = Field("", description="作者ID")
    likes: int = Field(0, description="点赞数")
    comments: int = Field(0, description="评论数")
    shares: int = Field(0, description="分享数")
    url: str = Field("", description="原文链接")
    create_time: str = Field("", description="发布时间")
    followers: int = Field(0, description="粉丝数（用户搜索用）")
    videos: int = Field(0, description="视频数（用户搜索用）")
    raw_data: dict = Field(default_factory=dict, description="原始数据")

class CrawlerTaskResponse(BaseModel):
    """采集任务响应"""
    task_id: str
    status: str = "pending"
    message: str = ""
    results: list[CrawlerResult] = []
    total: int = 0
    created_at: float = Field(default_factory=time.time)
    finished_at: Optional[float] = None

# =============================================================================
# 缓存任务存储（生产环境应使用 Redis）
# =============================================================================

_crawler_tasks: dict[str, dict] = {}


# =============================================================================
# 核心服务类
# =============================================================================

def crawler_result_asset_type(result: CrawlerResult):
    """Map crawler content semantics to the matching Asset Hub type.

    ⚠️ 图文（多图笔记）**不在这里返回 IMAGE**——见
    `is_multi_image_post()`：多图会建成 COLLECTION 容器 + 每张图一个 IMAGE 子节点，
    否则一整套图片只会剩下一张封面（用户反馈过"图文下载需要优化"）。
    """
    from app.db.models.asset_hub import AssetType

    content_type = str(result.type or '').strip().lower()
    if content_type in {'image', 'photo', 'gallery'} or (result.images and not result.video_url):
        return AssetType.IMAGE
    if content_type in {'article', 'note', 'text', 'post'}:
        return AssetType.TEXT
    if content_type in {'audio', 'music', 'podcast'}:
        return AssetType.AUDIO
    return AssetType.VIDEO


def is_multi_image_post(result: CrawlerResult) -> bool:
    """是否"多图图文"——需要建成集合。

    判据（实测）：
      · 有 images 列表且多于 1 张
      · 且没有视频（有视频的多图是"视频+封面图"，不是图集）
    """
    images = list(getattr(result, "images", None) or [])
    has_video = bool(getattr(result, "video_url", "") or "")
    return len(images) > 1 and not has_video

class CrawlerService:
    """
    素材采集服务
    使用新的 platforms 模块，降级到 yt-dlp
    """

    def __init__(self):
        self.use_mediacrawler = False
        logger.info(f"[CrawlerService] Initialized (using platforms module)")

    async def search_videos(
        self,
        platform: str,
        keyword: str,
        max_results: int = 20,
        search_type: str = "note",
        sort_by: str = "",
        page: int = 1,
        conn_id: str = "",
        **kwargs,
    ) -> list[CrawlerResult]:
        """
        搜索视频/图文素材
        优先使用 platforms 模块，失败则降级到 yt-dlp
        """
        # 1. 尝试新的 platforms 模块
        try:
            return await self._search_via_platforms(
                platform, keyword, max_results, search_type, sort_by, page,
                conn_id=conn_id, **kwargs,
            )
        except PlatformUnavailableError:
            # 平台明确"不可用"（如抖音对本环境降级）时**不要**降级到 yt-dlp：
            # yt-dlp 只会再返回一次空，最终让用户看到"找到 0 条结果"，
            # 把"环境被风控"误报成"关键词没结果"。直接抛给上层显示可读原因。
            raise
        except LoginExpiredError:
            # ⚠️ **登录态失效同样不能降级到 yt-dlp**（2026-10-01 加）
            # 降级只会再空一次，把"该重新登录"伪装成"没搜到"。
            # 用类型判断，不靠关键词猜（快手那条报错就不含关键词）。
            raise
        except Exception as e:
            # ⚠️ **登录态/风控类错误也不能降级到 yt-dlp**（2026-09-29）
            #
            # 实测：小红书被风控时 `_search_via_platforms` 抛
            # `RuntimeError: [xhs] 搜索接口返回 HTTP 461`，
            # 而这里**吞掉**并降级到 yt-dlp —— yt-dlp 又返回空，
            # 于是响应变成：
            #
            #     HTTP 200 {"success": true, "results": [],
            #               "message": "找到 0 条结果"}
            #
            # **用户完全不知道是被风控了**（这正是"静默返回空"的老毛病）。
            #
            # 判据：错误消息里出现登录态/风控关键词 → 直接抛给上层。
            msg = str(e)
            if any(k in msg for k in (
                "HTTP 461", "HTTP 403", "HTTP 401", "HTTP 429",
                "未登录", "登录态", "Cookie", "cookie", "风控", "antispam",
            )):
                logger.warning(
                    "[search_videos] %s 登录态/风控类错误，不降级到 yt-dlp：%s",
                    platform, msg[:120],
                )
                raise
            logger.warning(f"[search_videos] platforms module failed: {e}, falling back to yt-dlp")
        # 2. 降级方案：使用 yt-dlp 搜索
        return await self._search_via_ytdlp(platform, keyword, max_results)

    def _resolve_cookie_for(self, conn_id: str, platform: str) -> str:
        """从 `conn_id` 取 cookie（`k=v; k2=v2` 形式）。给 **api 模式**用。

        ## ⚠️ 用 `resolve_connection` + `netscape_to_header`（2026-09-29）

        我第一版用了 `PlatformConnectionService().get_raw_cookie(conn_id)`
        —— **它在这个上下文里返回 None**（`svc.get()` 查不到连接），
        导致 cookie 为空、搜索永远 0 条。

        改用 `resolve_connection`（它本来就带"ID 失效时回退到该平台最近
        连接"的兜底，是项目里已验证可用的取 cookie 路径），
        再用 `netscape_to_header` 转成 HTTP 头格式。

        patchright 模式不需要它（浏览器自己注入 cookie），
        但 api 模式**必须**显式传 —— 否则平台客户端会报"需要登录 Cookie"。
        """
        try:
            from app.services.platforms.login_health import (
                netscape_to_header,
                resolve_connection,
            )

            # 平台名要转成连接的枚举值（PG 枚举是小写：douyin / xhs / ...）
            conn_platform = {
                "xhs": "XHS", "xiaohongshu": "XHS",
                "douyin": "DOUYIN", "dy": "DOUYIN",
                "bili": "BILIBILI", "bilibili": "BILIBILI",
                "weibo": "WEIBO", "wb": "WEIBO",
                "twitter": "TWITTER", "x": "TWITTER",
            }.get(platform, platform.upper())

            _cid, raw = resolve_connection(conn_id or "", conn_platform)
            if not raw:
                logger.warning(
                    "[_resolve_cookie_for] %s 没取到 cookie —— "
                    "api 模式会失败（请检查「账号中心」是否保存了登录态）",
                    platform,
                )
                return ""

            # 连接的 cookie_content 是 **Netscape 格式**，
            # 必须转成 `k=v; k2=v2` 才能放进 HTTP 头
            # （直接塞会被 httpx 以 Illegal header value 拒绝）。
            #
            # ⚠️ **domain 参数要用 `netscape_to_header` 认识的名字**
            # （2026-09-29 踩过两次）：
            #
            #     netscape_to_header(raw, "xhs")      → 0 字符
            #     netscape_to_header(raw, "xiaohongshu") → 998 字符
            #
            #     netscape_to_header(raw, "twitter")  → 0 字符
            #     netscape_to_header(raw, "x.com")    → 1339 字符   ← X 的域是 .x.com
            #
            # 第一次我加了映射表但**漏了 `twitter` 本身**
            # （只加了 `x` → `twitter`，而 twitter 又映射不到真实域名）。
            #
            # 所以现在**逐个候选试**，而不是只查一次映射表 ——
            # 映射表漏项时还有兜底。
            cookie_domains = {
                "xhs": ("xiaohongshu", "xhs"),
                "xiaohongshu": ("xiaohongshu", "xhs"),
                "dy": ("douyin", "dy"),
                "douyin": ("douyin", "dy"),
                "wb": ("weibo", "wb"),
                "weibo": ("weibo", "wb"),
                "bili": ("bilibili", "bili"),
                "bilibili": ("bilibili", "bili"),
                # ⚠️ X 的 cookie 域是 **.x.com**（不是 twitter.com）
                "twitter": ("x.com", "x", "twitter.com", "twitter"),
                "x": ("x.com", "x", "twitter.com", "twitter"),
                "tw": ("x.com", "x", "twitter.com", "twitter"),
                "fanqie": ("fanqie",),
            }.get(platform, (platform,))

            cookie = ""
            for dom in cookie_domains:
                cookie = netscape_to_header(raw, dom) or ""
                if cookie:
                    break
            if not cookie:
                # 兜底：可能已经是 header 格式了
                cookie = raw if "=" in raw and "\t" not in raw else ""
            if cookie:
                logger.debug(
                    "[_resolve_cookie_for] %s -> %d 字符 cookie",
                    platform, len(cookie),
                )
            return cookie
        except Exception as exc:
            logger.warning(
                "[_resolve_cookie_for] 取 %s 的 cookie 失败：%s", platform, exc
            )
            return ""

    async def _search_via_platforms(
        self,
        platform: str,
        keyword: str,
        max_results: int = 20,
        search_type: str = "note",
        sort_by: str = "",
        page: int = 1,
        conn_id: str = "",
        **kwargs,
    ) -> list[CrawlerResult]:
        """通过新的 platforms 模块搜索"""
        try:
            from app.services.platforms import create_client, search as platform_search
            from app.services.platforms.types import SearchResult as PlatformSearchResult

            logger.info(f"[{self.__class__.__name__}] Searching {platform}: {keyword} (type={search_type}, sort={sort_by})")

            # 调用 platforms 模块的搜索功能
            #
            # mode 按平台选择：小红书与微博必须走 patchright。
            #
            # 实测（2026-09-26）小红书：搜索端点已迁移到 so.xiaohongshu.com/v2，
            # 且需要 X-s/X-t 签名（签名函数是混淆 JS、跨域调用 406），
            # 旧的 edith/v1 地址直接返回 code:300011。所以 API 模式对小红书已不可用。
            #
            # 实测（2026-09-27）微博：**所有 httpx 直连方案都返回 ok=-100**
            # （直连 / 换访客 Cookie / 补 _T_WM·MLOGIN·XSRF / 换 UA / 加
            # sec-fetch 头 全部失败）。根因是微博注册了 **Service Worker**
            # （bsk debug 捕获显示 from_service_worker=True），
            # 由它代理请求并注入 httpx 复现不了的上下文。
            # 而真实浏览器里**连登录都不需要**（ok=1, total=870）。
            # 所以微博也必须 patchright —— 但原因与小红书不同
            # （小红书要签名，微博要 SW 上下文）。
            #
            # 实测（2026-09-28 更新）推特：**已改为纯 HTTP 优先**。
            #
            # 之前归因错了 —— httpx 拿 404 **不是 queryId 失效，而是缺
            # `x-client-transaction-id` 请求头**（twscrape/Scweet 都有记录）。
            # 补上它 + `auth_token`/`ct0` 后，SearchTimeline 实测 200：
            #
            #     要 20 条 -> 20 条 (9.1s)    要 50 条 -> 50 条 (19.3s)
            #     cursor 翻页 4 页 85 条
            #     **全程不开浏览器**
            #
            # 所以推特**不再**放进 BROWSER_ONLY —— 走 api 模式（纯 HTTP），
            # 客户端内部在 HTTP 失败时才自己回退 DOM。
            #
            # 注意：这里必须让 mode=api。否则 BasePlatformClient 会在
            # `search()` 之前就为注入 cookie 而**启动浏览器**（实测看到
            # 9 个 chrome 进程白起），而我们的 HTTP 路径根本不需要它。
            #
            # 其他平台（B站/抖音/快手…）仍用 api。
            #
            # ⚠️ 实测（2026-09-29 更新）小红书：**已改为纯 HTTP**。
            #
            # 长期写着"小红书搜索端点已迁移到 so.xiaohongshu.com/v2、
            # 旧 edith/v1 返回 300011、Python 侧不可用" —— **这是错的**。
            # 300011 是"缺 X-s/X-t 签名被风控拒"，**不是端点废弃**。
            # 我们装上 `xhshow`（纯 Python 签名）后实测：
            #
            #     POST edith.xiaohongshu.com/api/sns/web/v1/search/notes
            #     → 200, success=True, data.items[20~21], 每项自带 xsec_token
            #     分页 page=1/2/3 三页不同；sort 三档都可用
            #     **单次 0.2~0.5 秒**（浏览器路径要 ~15 秒）
            #
            # 详情同理（`POST /api/sns/web/v1/feed`，~3 秒）。
            # 所以小红书**不再**放进 BROWSER_ONLY。
            #
            # 保留在 BROWSER_ONLY 的只有微博 —— 它需要 **Service Worker
            # 上下文**（实测 httpx 直连一律 ok=-100，与签名无关）。
            BROWSER_ONLY = ("weibo", "wb")
            mode = "patchright" if platform in BROWSER_ONLY else "api"
            logger.info(
                "[_search_via_platforms] platform=%s mode=%s keyword=%s",
                platform, mode, keyword,
            )

            # ⚠️ **api 模式必须显式传 cookie**（2026-09-29 修）
            #
            # 原来这里只传 `conn_id`，**没有 cookie**。
            # 小红书走 patchright 时没暴露问题（浏览器自己注入 cookie），
            # 但改成 api（纯 HTTP）后：
            #
            #     [xhs] HTTP client initialized (API mode)
            #     Error: [xhs] 搜索需要登录 Cookie     ← 永远搜不到东西
            #
            # 表现是"小红书搜索 0 条"，而且**所有关键词都是 0 条** ——
            # 这种"全空"要优先怀疑凭证没传，而不是关键词没内容。
            cookie = self._resolve_cookie_for(conn_id, platform)
            # ⚠️ 先剔除 kwargs 里可能已有的 cookie，否则
            # `search() got multiple values for keyword argument 'cookie'`
            # （实测踩过 —— 上层调用方有时会把 cookie 塞进 kwargs）。
            kwargs.pop("cookie", None)
            results = await platform_search(
                platform=platform,
                keyword=keyword,
                mode=mode,
                cookie=cookie,
                max_results=max_results,
                search_type=search_type,
                sort_by=sort_by,
                page=page,
                conn_id=conn_id,
                **kwargs,
            )

            if not results:
                logger.warning(f"[_search_via_platforms] No results from platforms module for {platform}")
                return []

            # 提取总条数（B站等平台会在第一个结果的 raw_data._total 中存放）
            total_from_platform = results[0].raw_data.get("_total") if results else None

            # 转换为 CrawlerResult
            crawler_results = []
            for idx, item in enumerate(results):
                try:
                    raw_data = dict(item.raw_data)
                    # 把总条数放到第一个结果的 raw_data 中，方便上层读取
                    if idx == 0 and total_from_platform:
                        raw_data["_total"] = total_from_platform

                    # ⚠️ `SearchResult` 没有 images / video 字段（那些在
                    # NoteDetail 里），所以平台把多图与视频直链放在 raw_data
                    # 的 `_images` / `_video_url`（微博等就是这么做的）。
                    # 这里取出来填进 CrawlerResult —— 否则前端拿不到图集，
                    # 「图文下载」也会退化成只有一张封面。
                    extra_images = list(raw_data.get("_images") or [])
                    video_direct = str(raw_data.get("_video_url") or "")

                    result = CrawlerResult(
                        id=item.id,
                        platform=item.platform,
                        type=item.type,
                        title=item.title,
                        desc=item.desc if item.desc else None,
                        cover=item.cover,
                        # ⚠️ **没有视频直链就留空，不能拿"原文链接"兜底**
                        # （2026-09-29 修）
                        #
                        # 原来是 `video_direct or item.url` —— 于是**图集也有
                        # video_url**（值是 `https://www.xiaohongshu.com/explore/...`）。
                        #
                        # 后果（用户反馈"小红书有图集的被识别为视频了"）：
                        # 前端靠"video_url 有没有值"判断是不是视频 →
                        # **图集被判成视频**，详情里渲染出一个 0:00 的空播放器，
                        # 而真正的图集被隐藏（因为"有视频时不显示封面"）。
                        #
                        # 而且注释里自己都写了"抖音此前就踩过：video_url 放详情页
                        # 会导致下载器取不到流" —— 那个坑和这个是同一个根因：
                        # **把"页面地址"和"媒体直链"混在一个字段里**。
                        #
                        # 想跳原文有独立的 `url` 字段，不需要 video_url 兜底。
                        video_url=video_direct,
                        images=extra_images,
                        author=item.author,
                        author_id=item.author_id,
                        likes=item.likes,
                        comments=item.comments,
                        shares=item.shares,
                        url=item.url,
                        create_time=item.create_time,
                        followers=item.followers,
                        videos=item.videos,
                        raw_data=raw_data,
                    )
                    crawler_results.append(result)
                except Exception as e:
                    logger.error(f"[_search_via_platforms] Error converting result: {e}")
                    continue

            logger.info(f"[_search_via_platforms] Found {len(crawler_results)} results for {platform}: {keyword}")
            return crawler_results

        except ImportError:
            logger.warning("[_search_via_platforms] platforms module not available")
            return []
        except PlatformUnavailableError:
            # 平台明确"当前环境不可用"（如抖音限制自动化环境的搜索接口）。
            # 必须穿透出去——吞成 return [] 会让用户看到"找到 0 条结果"，
            # 把"环境被限制"误报成"关键词没结果"。
            raise
        except LoginExpiredError:
            # ⚠️ **登录态失效要原样穿透**（2026-10-01 加）
            #
            # 实测：快手 cookie 过期后搜索抛
            #     [kuaishou] 未能获取 /rest/v/search/feed 的接口签名 ...
            # 它**不含**下面那组关键词（461/403/风控/…），
            # 所以原来会走到 `return []` → 用户看到"找到 0 条结果"，
            # 完全不知道是登录过期了。
            #
            # 这里用**类型判断**（不是字符串匹配）—— 平台自己最清楚
            # 哪个信号代表"要重新登录"，不该让上层靠猜关键词。
            # API 层据此映射成 **401**，前端提示"请重新登录"。
            raise
        except Exception as e:
            # ⚠️ **登录态/风控类错误也要穿透**（2026-09-29 修）
            #
            # 原来一律 `return []` —— 实测小红书被风控（HTTP 461）时：
            #
            #     日志：[_search_via_platforms] Error: [xhs] 搜索接口返回 HTTP 461
            #     响应：HTTP 200 {"success": true, "results": [],
            #                    "message": "找到 0 条结果"}
            #
            # **用户看到"没搜到"，完全不知道是被风控** —— 这是本仓库
            # 反复出现的老毛病（`ADDING_A_PLATFORM.md` 铁律第 2 条）。
            #
            # 而这里正是第一现场（外层 `search_videos` 的 catch 根本
            # 执行不到，因为异常在这里就被吞了 —— 我第一版修错了地方）。
            msg = str(e)
            if any(k in msg for k in (
                "461", "471", "406", "403", "401", "429",
                "300011", "300012",
                "未登录", "登录态", "Cookie", "cookie",
                "风控", "antispam", "CAPTCHA", "captcha",
            )):
                logger.error(
                    "[_search_via_platforms] %s 登录态/风控类错误（**不吞成空**）：%s",
                    platform, msg[:160],
                )
                raise
            logger.error(f"[_search_via_platforms] Error: {e}")
            return []

    async def _search_via_ytdlp(
        self,
        platform: str,
        keyword: str,
        max_results: int,
    ) -> list[CrawlerResult]:
        """通过 yt-dlp 搜索（降级方案）"""
        import yt_dlp

        # yt-dlp 搜索语法：ytsearchN:"keyword"
        search_url = f"ytsearch{max_results}:\"{keyword}\""

        # 根据平台调整搜索前缀
        platform_search_map = {
            # 国内平台
            "bili": f"ytsearch{max_results}:\"{keyword} site:bilibili.com\"",
            "dy": f"ytsearch{max_results}:\"{keyword} site:douyin.com\"",
            "ks": f"ytsearch{max_results}:\"{keyword} site:kuaishou.com\"",
            "wb": f"ytsearch{max_results}:\"{keyword} site:weibo.com\"",
            "xhs": f"ytsearch{max_results}:\"{keyword} site:xiaohongshu.com\"",
        }

        actual_url = platform_search_map.get(platform, search_url)

        def _fetch():
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "extract_flat": "in_playlist",  # 只提取列表，不下载
                "no_check_certificate": True,
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
                "default_search": "ytsearch",
                "format": "best",
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(actual_url, download=False)
                    if not info or "entries" not in info:
                        logger.warning(f"[_search_via_ytdlp] No results for {platform}: {keyword}")
                        return []

                    results = []
                    for entry in info["entries"][:max_results]:
                        if not entry:
                            continue
                        result = CrawlerResult(
                            id=entry.get("id", ""),
                            platform=platform,
                            title=entry.get("title", ""),
                            desc=entry.get("description", ""),
                            cover=entry.get("thumbnail", ""),
                            video_url=entry.get("url", "") or entry.get("webpage_url", ""),
                            author=entry.get("uploader", "") or entry.get("channel", ""),
                            author_id=entry.get("channel_id", ""),
                            likes=entry.get("like_count", 0) or 0,
                            comments=entry.get("comment_count", 0) or 0,
                            shares=entry.get("repost_count", 0) or 0,
                            url=entry.get("webpage_url", ""),
                            create_time=str(entry.get("timestamp", "")),
                            raw_data=entry,
                        )
                        results.append(result)
                    logger.info(f"[_search_via_ytdlp] Found {len(results)} results for {platform}: {keyword}")
                    return results
            except Exception as e:
                logger.error(f"[_search_via_ytdlp] Error searching {platform}: {e}")
                return []

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _fetch)

    async def search_notes(
        self,
        platform: str,
        keyword: str,
        max_results: int = 20,
        search_type: str = "note",  # "note" or "user"
        filters: dict = {},
    ) -> list[CrawlerResult]:
        """
        搜索笔记或用户
        search_type: "note" = 搜索笔记, "user" = 搜索用户
        filters: 可选筛选条件（排序、时间范围等）
        """
        # 使用 platforms 模块搜索
        try:
            return await self._search_via_platforms(platform, keyword, max_results)
        except Exception as e:
            logger.warning(f"[search_notes] platforms module failed: {e}, falling back to yt-dlp")

        # 降级方案：使用 yt-dlp 搜索
        return await self._search_via_ytdlp(platform, keyword, max_results)

    async def get_note_detail(
        self,
        platform: str,
        note_id: str,
        cookie: str = "",
        keyword: str = "",
        **kwargs_in,
    ) -> dict:
        """
        获取笔记详情（无水印）
        返回包含无水印图片/视频 URL 的字典

        ## 平台差异（实测）

        · **小红书必须走 patchright**（API 端点已失效），
          而且详情要"站内点击"打开 —— 所以要把**搜索关键词**传下去
          （用笔记 id 搜不到目标笔记，实测返回不相关结果）。
        · 抖音没有"按 id 反查详情"的已确认接口，其详情数据在搜索结果里
          就已完整（前端因此直接用结果渲染，不走这里）。
          若确实调到这里且缺少原始数据，会抛出可读错误而不是静默返回空。
        """
        try:
            from app.services.platforms import create_client

            # 小红书也走 api（**纯 HTTP + 签名**，2026-09-29 打通）
            #
            # 这里一度是 patchright（因为误判"API 端点已失效"）。
            # 实际端点一直活着，只是缺签名；加上 `xhshow` 后纯 HTTP 可用，
            # 而且比浏览器**更快、字段更全**（原图/多清晰度/话题/IP 属地）。
            mode = "api"
            client = create_client(platform, mode=mode, cookie=cookie)
            if not client:
                logger.error(f"[get_note_detail] Failed to create client for {platform}")
                return {}

            # 小红书：把 `xsec_token` 透传给详情（**必需**，缺失会 461）
            kwargs: dict = {}
            if platform in ("xhs", "xiaohongshu"):
                token = (kwargs_in or {}).get("xsec_token") or ""
                if token:
                    kwargs["xsec_token"] = token

            detail = await client.get_detail(note_id, **kwargs)

            if not detail:
                logger.warning(f"[get_note_detail] No detail found for {note_id}")
                return {}

            # 转换为字典
            #
            # ⚠️ 字段名要跟 `crawler.models.NoteDetail` 对齐：
            # 收藏数是 **`collect_count`**（不是 `collects`）。
            # 传错名字时 pydantic 会**静默忽略**该字段 → 前端拿到
            # `收藏=None`（实测踩过：接口明明返回了 collected_count=155）。
            return {
                "id": detail.id,
                "platform": detail.platform,
                "title": detail.title,
                "desc": detail.desc,
                "images": detail.images if hasattr(detail, 'images') else [],
                "video": detail.video if hasattr(detail, 'video') else "",
                "author": detail.author,
                "author_id": detail.author_id,
                "likes": detail.likes,
                "comments": detail.comments,
                "shares": detail.shares,
                "collect_count": getattr(detail, "collects", 0) or 0,
                "views": getattr(detail, "views", 0) or 0,
                # 发布时间 / 标签：API 路径能拿到（小红书 `time` / `tag_list`）
                "create_time": getattr(detail, "create_time", "") or "",
                "tags": getattr(detail, "tags", []) or [],
                # ⚠️ `raw_data` 要带出来 —— 前端依赖它拿 `xsec_token`
                # （再点别的操作时要用）。原来没带，前端拿到空对象。
                "raw_data": getattr(detail, "raw_data", {}) or {},
            }

        except Exception as e:
            logger.error(f"[get_note_detail] Error: {e}")
            return {}

    async def import_to_asset_library(
        self,
        results: list[CrawlerResult],
        owner_user_id: str | None = None,
    ) -> list[str]:
        """把采集结果导入素材库。

        `owner_user_id` **必须传**（普通登录用户场景）：
        素材库列表按 owner 过滤，owner 为 NULL 的记录登录用户看不到 ——
        实测表现为"导入返回成功但素材库一直空的"。
        仅 Agent 内部调用等无用户场景才允许为 None（legacy NULL）。
        """
        """
        将采集结果导入到 YLCraft 素材库
        返回导入的素材 ID 列表
        """
        from sqlalchemy import text

        from app.db.database import get_async_session
        from app.db.models.asset_hub import AssetType
        from app.services.asset_hub.node_service import AssetNodeService

        asset_ids = []
        async with get_async_session() as db_session:
            node_service = AssetNodeService(db_session)
            for result in results:
                try:
                    # 检查是否已存在
                    existing = await db_session.execute(
                        text(
                            """
                            SELECT id
                            FROM asset_nodes
                            WHERE metadata_json ->> 'source_url' = :source_url
                            LIMIT 1
                            """
                        ),
                        {"source_url": result.url},
                    )
                    existing_id = existing.scalar_one_or_none()
                    if existing_id:
                        # 已存在。但**多图图文要检查是不是该升级成集合**。
                        #
                        # 踩过的坑（2026-09-27）：用户在「去水印解析」页解析时，
                        # parse 会先建一条该 source_url 的单节点记录（类型是
                        # VIDEO/TEXT）。之后点「导入素材库」走 crawler/import，
                        # 这里的去重直接命中那条旧记录并 continue ——
                        # 于是**集合结构根本没建**，图集里的图一张都进不来，
                        # 素材库里只能看到一条标题。
                        #
                        # 现在：命中旧记录时，如果这条其实是多图图文、
                        # 而旧记录又不是集合，就把它**升级**为集合。
                        if is_multi_image_post(result):
                            upgraded = await self._upgrade_to_collection(
                                db_session, node_service, result,
                                str(existing_id), owner_user_id,
                            )
                            if upgraded:
                                asset_ids.append(str(upgraded))
                                continue
                        asset_ids.append(str(existing_id))
                        continue

                    # 多图图文 → 建成集合（容器 + 每张图一个子节点）。
                    # 否则一整套图片只会剩一张封面，用户拿不到原图。
                    if is_multi_image_post(result):
                        node = await self._import_image_collection(
                            node_service, result, owner_user_id
                        )
                        asset_ids.append(str(node.id))
                        continue

                    # 创建新素材节点。采集结果多为远端素材卡片，未必有本地文件。
                    node = await node_service.create(
                        name=result.title or "未命名素材",
                        asset_type=crawler_result_asset_type(result),
                        owner_user_id=owner_user_id,
                        thumbnail_url=result.cover or None,
                        metadata={
                            "source": "crawler",
                            "source_url": result.url,
                            "crawler": True,
                            "platform": result.platform,
                            "author": result.author,
                            "author_id": result.author_id,
                            "cover_url": result.cover,
                            "video_url": result.video_url,
                            "description": result.desc or "",
                            "external_id": result.id,
                            "create_time": result.create_time,
                            "likes": result.likes,
                            "comments": result.comments,
                            "shares": result.shares,
                            "followers": result.followers,
                            "videos": result.videos,
                            "image_count": len(result.images or []),
                            "images": list(result.images or []),
                            "is_collection": False,
                            "raw_data": result.raw_data,
                        },
                        tags=["crawler", result.platform],
                    )
                    asset_ids.append(str(node.id))
                except Exception as e:
                    logger.error(f"[import_to_asset_library] Failed to import {result.id}: {e}")

        return asset_ids

    async def _upgrade_to_collection(
        self,
        db_session,
        node_service,
        result: CrawlerResult,
        existing_node_id: str,
        owner_user_id: str | None = None,
    ):
        """把一条已存在的单节点记录**升级**成"集合 + 子图"。

        场景：用户在「去水印解析」页解析（parse 建了单节点），
        之后点「导入素材库」，去重命中旧记录 →
        如果这其实是多图图文，就把旧记录就地改成 COLLECTION，
        并补建子图节点。

        返回集合节点 id；失败返回 None（调用方回退到旧行为）。

        为什么"就地改类型"而不是"删了重建"：
          · 保留原 id，其它地方（画布引用、发布记录）不会失效
          · 用户看到的还是同一条素材，只是从"一张封面"变成完整图集
        """
        from app.db.models.asset_hub import AssetType
        from sqlalchemy import text as _sql_text

        images = [u for u in (result.images or []) if u]
        if not images:
            return None

        try:
            # 1) 把旧节点改成集合，并补上完整元数据
            #
            # 两个踩过的坑：
            #   × `CAST(:imgs AS jsonb)` 用 SQLAlchemy `text(":name")` 占位时，
            #     PostgreSQL 推断不出参数类型 →
            #     `IndeterminateDatatypeError: could not determine data type
            #      of parameter $3`
            #   × `AsyncSession` **没有** `exec_driver_sql`（那是同步 Session 的），
            #     用它报 `AttributeError`
            #   × `id` 列是 **UUID** 类型，把 `nid` 标成 TEXT 会报
            #     `operator does not exist: uuid = character varying`
            #
            # 正解：用 `text()` + `:name`，并用 `bindparams` 显式标注每个参数的
            # 类型——注意 `id` 必须标成 UUID 而不是 TEXT。
            from sqlalchemy import bindparam, types
            from sqlalchemy.dialects.postgresql import UUID as PG_UUID

            stmt = _sql_text(
                """
                UPDATE asset_nodes
                SET asset_type = :atype,
                    thumbnail_url = COALESCE(thumbnail_url, :thumb),
                    metadata_json = metadata_json
                        || jsonb_build_object(
                             'is_collection', true,
                             'image_count', CAST(:icount AS integer),
                             'images', CAST(:imgs AS jsonb),
                             'crawler', true
                           )
                WHERE id = :nid
                """
            ).bindparams(
                bindparam("imgs", type_=types.Text),
                bindparam("icount", type_=types.Integer),
                bindparam("thumb", type_=types.Text),
                bindparam("atype", type_=types.Text),
                bindparam("nid", type_=PG_UUID(as_uuid=False)),
            )

            await db_session.execute(
                stmt,
                {
                    "atype": AssetType.COLLECTION.value,
                    "thumb": result.cover or images[0],
                    "icount": len(images),
                    "imgs": json.dumps(images, ensure_ascii=False),
                    "nid": existing_node_id,
                },
            )
            # 顺手补上 owner：旧记录可能 owner 为 NULL（parse 阶段建的），
            # 不补的话用户导入后仍然看不到。
            if owner_user_id:
                await db_session.execute(
                    _sql_text(
                        "UPDATE asset_nodes SET owner_user_id = :owner "
                        "WHERE id = :nid AND owner_user_id IS NULL"
                    ).bindparams(
                        bindparam("owner", type_=types.Text),
                        bindparam("nid", type_=PG_UUID(as_uuid=False)),
                    ),
                    {"owner": owner_user_id, "nid": existing_node_id},
                )
            await db_session.commit()

            # 2) 补建子图（已存在的子节点不重复建）
            existing_children = await db_session.execute(
                _sql_text(
                    "SELECT metadata_json->>'remote_url' FROM asset_nodes "
                    "WHERE parent_id = :pid"
                ),
                {"pid": existing_node_id},
            )
            have = {r[0] for r in existing_children.all() if r[0]}

            added = 0
            for idx, url in enumerate(images, start=1):
                if url in have:
                    continue
                try:
                    await node_service.create(
                        name=f"{result.title or '图集'} - 图{idx}",
                        asset_type=AssetType.IMAGE,
                        parent_id=existing_node_id,
                        owner_user_id=owner_user_id,
                        thumbnail_url=url,
                        metadata={
                            "source": "crawler",
                            "crawler": True,
                            "platform": result.platform,
                            "external_id": result.id,
                            "remote_url": url,
                            "index": idx,
                            "parent_url": result.url,
                            "author": result.author,
                            "is_collection_child": True,
                        },
                        tags=["crawler", result.platform, "图集图片"],
                    )
                    added += 1
                except Exception as img_err:
                    logger.warning(
                        "[import_to_asset_library] 升级补图失败（第 %d 张）：%s",
                        idx, img_err,
                    )

            logger.info(
                "[import_to_asset_library] 已把 %s 升级为集合（补建 %d/%d 张图）",
                existing_node_id, added, len(images),
            )
            return existing_node_id
        except Exception as exc:
            await db_session.rollback()
            logger.warning(
                "[import_to_asset_library] 升级为集合失败（回退到旧行为）：%s: %s",
                type(exc).__name__, exc,
            )
            return None

    async def _import_image_collection(
        self,
        node_service,
        result: CrawlerResult,
        owner_user_id: str | None = None,
    ):
        """把多图图文导入成"集合 + 子图"两层结构。

        ## 为什么这样设计（2026-09-27）

        用户反馈"图文下载需要优化"。原来一条图文笔记只建**一个** IMAGE 节点，
        只存封面——图集里的其它原图全丢了。

        资产库本身已经支持这套结构（无需改表）：
          · `AssetType.COLLECTION` + `AssetNode.parent_id` → 父子层级
          · `AssetNodeService.list_children(parent_id)` → 直接列出集合里的图
          · 子节点各自带 `metadata_json.remote_url` → 指向远端原图

        对齐开源项目的常见做法（XHS-Downloader / douyin-downloader 等
        都是"作品 → 图片列表"两级：作品一条记录，图片各自一条）。

        选择"远端 URL 存 metadata"而不是"下载到本地再引用"：
          · 采集阶段不应产生大量本地文件（用户还没决定要哪张）
          · 用户点"下载"时再落盘，与现有下载流程一致
        子节点保留 remote_url，后续下载/导入都能直接用。

        没有用 RelationType.CONTAINS 建关系表——层级已经由 parent_id 表达，
        再加一张关系表是重复信息（AssetNodeService 也没有 add_relation 方法）。
        """
        from app.db.models.asset_hub import AssetType

        images = list(result.images or [])
        container = await node_service.create(
            name=result.title or f"{result.platform} 图集",
            asset_type=AssetType.COLLECTION,
            owner_user_id=owner_user_id,
            thumbnail_url=result.cover or (images[0] if images else None),
            metadata={
                "source": "crawler",
                "source_url": result.url,
                "crawler": True,
                "platform": result.platform,
                "author": result.author,
                "author_id": result.author_id,
                "description": result.desc or "",
                "external_id": result.id,
                "create_time": result.create_time,
                "likes": result.likes,
                "comments": result.comments,
                "shares": result.shares,
                "image_count": len(images),
                "images": images,
                "is_collection": True,
                "cover_url": result.cover,
                "raw_data": result.raw_data,
            },
            tags=["crawler", result.platform, "图集"],
        )

        # 每张图一个子节点，挂在集合下面
        for idx, url in enumerate(images, start=1):
            try:
                await node_service.create(
                    name=f"{result.title or '图集'} - 图{idx}",
                    asset_type=AssetType.IMAGE,
                    parent_id=str(container.id),
                    owner_user_id=owner_user_id,
                    thumbnail_url=url,
                    metadata={
                        "source": "crawler",
                        "crawler": True,
                        "platform": result.platform,
                        "external_id": result.id,
                        "remote_url": url,
                        "index": idx,
                        "parent_url": result.url,
                        "author": result.author,
                        "is_collection_child": True,
                    },
                    tags=["crawler", result.platform, "图集图片"],
                )
            except Exception as img_err:
                logger.warning(
                    "[import_to_asset_library] 图 %d 导入失败：%s", idx, img_err,
                )

        logger.info(
            "[import_to_asset_library] 图集导入完成：%s（%d 张）",
            container.id, len(images),
        )
        return container


# =============================================================================
# 全局服务实例
# =============================================================================

_crawler_service: Optional[CrawlerService] = None


def get_crawler_service() -> CrawlerService:
    global _crawler_service
    if _crawler_service is None:
        _crawler_service = CrawlerService()
    return _crawler_service
