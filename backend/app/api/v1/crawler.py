"""
YLCraft — 素材采集 API
集成 MediaCrawler 核心功能

GET  /api/v1/crawler/platforms    — 获取支持的平台列表
GET  /api/v1/crawler/options     — 获取配置选项
POST /api/v1/crawler/search      — 搜索视频/图文素材
POST /api/v1/crawler/import      — 将采集结果导入素材库
GET  /api/v1/crawler/tasks/{id} — 查询采集任务状态（异步）
POST /api/v1/crawler/search-enhanced — 增强搜索（支持笔记/用户）
GET  /api/v1/crawler/note-detail  — 获取笔记详情（无水印）
POST /api/v1/crawler/fetch-no-watermark — 批量获取无水印资源
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict

from app.core.resource_auth import principal_owner_user_id
from app.core.user_auth import (
    AuthenticatedPrincipal,
    get_authenticated_principal_optional,
)
from app.services.crawler import (
    CrawlerService,
    CrawlerResult,
    SearchRequest,
    CrawlerTaskResponse,
    get_crawler_service,
)
from app.services.crawler.models import NoteDetail, SearchFilter, SearchEnhancedRequest, NoteDetailResponse, FetchNoWatermarkRequest

# ⚠️ 模块级导入（不要放进函数里）——
# 之前 `users.py` 就因为只在 `_client_for` 作用域里 import，
# 运行时抛 NameError。这里统一放模块顶部。
from app.services.platforms.types import (
    ContentNotFoundError,
    LoginExpiredError,
    NetworkError,
    PlatformError,
    RiskControlError,
)
# 翻页模型（前端据此选分页器 / 加载更多）—— 声明在 platforms/<平台>/meta.py
from app.services.platforms.meta import pagination_info
# 平台侧拒绝（风控/UA/空 body）—— 详情路由要把它映射成 429（可重试），
# 而不是被 service 层吞成 {} → 404"笔记不存在"（2026-10-01）
from app.services.platforms.douyin.client import PlatformUnavailableError

router = APIRouter()
logger = logging.getLogger("ylcraft.api.crawler")


# =============================================================================
# 辅助函数
# =============================================================================

def _get_conn_cookie(conn_id: str) -> str:
    """从 conn_id 获取 Cookie（**已规范化**，可直接放进 HTTP `Cookie` 头）。

    ## ⚠️ 2026-09-29 修正：原来这个函数**返回空**

    老实现：

        service = PlatformConnectionService()
        return service.get_raw_cookie(conn_id) or ""

    `PlatformConnectionService` 内部用**它自己的 session** 查库，
    在 API 请求上下文里**查不到连接** → 返回 `None` → 这里得到空串。

    **后果是全线静默失败**：所有依赖 cookie 的路径（小红书搜索、
    详情 …）都报"需要登录 Cookie"，看起来像"登录态丢了"，
    实际是**取 cookie 的代码坏了**（实测：`_get_conn_cookie` 返回 0 字符）。

    改用 `resolve_connection` —— 项目里**已验证可用**的取 cookie 路径
    （它用 `SessionLocal()`，还自带"conn_id 失效时回退到该平台最近连接"
    的兜底），再用 `netscape_to_header` 转成 HTTP 头格式
    （`cookie_content` 是 Netscape 格式，直接塞会被 httpx 以
    `Illegal header value` 拒绝）。
    """
    if not conn_id:
        return ""
    try:
        from app.services.platforms.login_health import (
            netscape_to_header,
            resolve_connection,
        )

        # ⚠️ `resolve_connection` 的兜底（"conn_id 失效时回退到该平台
        # 最近连接"）**只有在传了 platform 时才生效**（实测：
        # `resolve_connection(old_id, "")` 返回空）。所以这里先按 conn_id
        # 查出**它属于哪个平台**，再用该平台做兜底。
        platform_hint = _platform_of_connection(conn_id)

        _cid, raw = resolve_connection(conn_id, platform_hint)
        if not raw:
            logger.warning(
                "[_get_conn_cookie] conn=%s 取不到内容 —— 依赖 cookie 的"
                "请求会失败（请检查「账号中心」是否保存了登录态）",
                conn_id[:8],
            )
            return ""

        # Netscape → `k=v; k2=v2`。domain 用平台的 cookie 别名
        # （实测：传 `xhs` 返回 0 字符，必须传 `xiaohongshu`）。
        cookie_domain = {
            "xhs": "xiaohongshu", "xiaohongshu": "xiaohongshu",
            "douyin": "douyin", "bili": "bilibili",
            "weibo": "weibo", "twitter": "twitter",
        }.get(platform_hint, platform_hint)

        cookie = netscape_to_header(raw, cookie_domain) or ""
        if not cookie:
            # 兜底：内容可能本来就是 header 格式
            cookie = raw if "=" in raw and "\t" not in raw else ""
        return cookie
    except Exception as e:
        logger.warning(f"Failed to get cookie from connection {conn_id}: {e}")
    return ""


def _platform_of_connection(conn_id: str) -> str:
    """查连接属于哪个平台（小写枚举值，如 `xhs` / `douyin`）。

    查不到返回空串 —— 调用方会退化为"只按 conn_id 查"。

    为什么需要：`resolve_connection` 的"回退到该平台最近连接"兜底
    **必须传 platform 才生效**，否则 conn_id 一失效就取不到 cookie
    （实测：用户重新登录后连接 ID 会变，旧 ID 就查不到了）。
    """
    try:
        from sqlmodel import select

        from app.db.database import SessionLocal
        from app.db.models.platform_connection import PlatformConnection

        session = SessionLocal()
        try:
            row = session.get(PlatformConnection, conn_id)
            if row is None:
                return ""
            p = row.platform
            # 枚举 → 小写值（PG 枚举值是小写）
            return str(getattr(p, "value", p) or "").lower()
        finally:
            session.close()
    except Exception as exc:
        logger.debug("[_platform_of_connection] %s 查询失败：%s", conn_id[:8], exc)
        return ""


# =============================================================================
# Response Models
# =============================================================================

# 内存任务存储（生产环境应使用 Redis）
_crawler_tasks: dict[str, dict] = {}


# =============================================================================
# 平台配置
# =============================================================================

PLATFORMS = [
    {"value": "xhs",   "label": "小红书",   "icon": "book",        "color": "#fe2c55"},
    {"value": "dy",    "label": "抖音",     "icon": "video",       "color": "#000000"},
    {"value": "ks",    "label": "快手",     "icon": "play-circle", "color": "#ff5000"},
    {"value": "bili",  "label": "B站",     "icon": "tv",          "color": "#00aeec"},
    {"value": "wb",    "label": "微博",     "icon": "message",     "color": "#ff8200"},
    # ⚠️ zhihu 已移除（2026-10-01 用户要求）
    {"value": "wechat_mp", "label": "微信公众号", "icon": "wechat", "color": "#07C160"},
]

CRAWLER_TYPES = [
    {"value": "search",   "label": "关键词搜索"},
    {"value": "detail",   "label": "指定内容ID"},
    {"value": "creator",  "label": "创作者主页"},
]


# =============================================================================
# 请求/响应模型
# =============================================================================

class SearchResponse(BaseModel):
    """搜索响应"""
    success: bool
    results: list[CrawlerResult] = []
    # `total` 是**本次返回的条数**（不一定是平台总数 —— 有的平台不给）
    total: int = 0
    # 平台是否明确表示"还有下一页"。
    # 前端据此显示"还有更多"，而不是把 `total` 当总数说成"共 N 条"。
    has_more: bool = False
    message: str = ""
    using: str = ""  # 使用的搜索引擎
    # ⚠️ 翻页模型（2026-10-03 加）
    #
    #     {"model": "paged",  "single_page_max": 0}    前端用页码分页器
    #     {"model": "single", "single_page_max": 18}   前端用「加载更多」
    #
    # 为什么要透出：不是所有平台都能翻页。抖音实测 `offset>0` 服务端返空，
    # 点"第 2 页"必然失败 —— 前端必须知道该换成"加载更多"。
    #
    # 声明在 `platforms/<平台>/meta.py`（单一事实来源），
    # 实测依据见 `platforms/meta.py` 里 `pagination` 字段的注释。
    pagination: dict = Field(default_factory=dict)
    # ⚠️ **游标翻页**（Telegram 的 dialogs / saved 用，不用页码）
    #
    # 语义：原样回传为 `filters.offset_id`，后端就会取"比它更旧的"。
    # 取值是**本次结果的最后一条** —— 传第一条会把它自己也包含进来
    # （实测重叠 4 条；传最后一条 → 重叠 0）。
    # 为空 = 没有更多了，或该平台用页码翻页（不看这个字段）。
    next_cursor: str = ""


class ImportRequest(BaseModel):
    """导入请求"""
    results: list[dict] = Field(..., description="要导入的采集结果列表")


class ImportResponse(BaseModel):
    """导入响应"""
    success: bool
    imported_count: int = 0
    asset_ids: list[str] = []
    message: str = ""


# =============================================================================
# 增强搜索模型
# =============================================================================

class SearchEnhancedRequest(BaseModel):
    """增强搜索请求"""
    platform: str = Field(..., description="平台: xhs/dy/ks/bili/wb")
    keyword: str = Field(..., description="搜索关键词")
    search_type: str = Field("note", description="搜索类型: note/user/article/global_article/bangumi/movie/live")
    max_results: int = Field(20, description="每页结果数", ge=1, le=100)
    sort_by: str = Field("", description="排序方式")
    order_sort: int = Field(0, description="排序方向：0=高到低，1=低到高（仅bili用户搜索有效）")
    filters: dict = Field(default_factory=dict, description="筛选条件")
    page: int = Field(1, description="页码", ge=1)
    conn_id: str = Field("", description="可选的平台连接 ID；仅用于在服务端取得该连接的登录态")


class NoteDetailResponse(BaseModel):
    """笔记详情响应"""
    success: bool
    data: Optional[NoteDetail] = None
    message: str = ""


class FetchNoWatermarkRequest(BaseModel):
    """批量获取无水印资源请求"""
    platform: str = Field(..., description="平台: xhs/dy/ks")
    note_ids: list[str] = Field(..., description="笔记ID列表")


# =============================================================================
# API 端点
# =============================================================================

@router.get("/platforms", summary="获取支持的平台列表")
async def get_platforms():
    """返回所有支持的平台"""
    return {"platforms": PLATFORMS}


@router.get("/options", summary="获取采集配置选项")
async def get_options():
    """返回采集类型和配置选项"""
    return {
        "crawler_types": CRAWLER_TYPES,
        "platforms": PLATFORMS,
    }


@router.post("/search", summary="搜索视频/图文素材", response_model=SearchResponse)
async def search_materials(req: SearchRequest):
    """
    搜索素材
    优先使用 MediaCrawler，失败则降级到 yt-dlp

    ⚠️ 必须带登录态（2026-09-27 修）：
    这个端点**原本不传 conn_id / cookie**，于是平台搜索拿不到 Cookie，
    抖音返回 status_code=2483（游客态）→ **结果恒为 0**。

    表现是"找到 0 条结果"，看起来像关键词没内容 ——
    而同一时刻 `search_enhanced`（会传 cookie）能正常返回，
    所以很容易误判成"这个端点坏了"或"抖音又风控了"。

    画布的 platform_search 节点走的就是这个端点，
    因此画布搜抖音一直为空，直到这里补上登录态。

    ⚠️ **未实现平台要报 501，不能静默返回空**（2026-10-01 修）

    `search_enhanced` 早就有这个守卫（2026-09-29 加），但**这个端点漏了**。
    实测（2026-10-01）：

        POST /api/v1/crawler/search-enhanced  {"platform":"youtube",...}
        → HTTP 501  ✅ 「平台 'youtube' 尚未实现采集（不是「没搜到」）」

        POST /api/v1/crawler/search           {"platform":"youtube",...}
        → HTTP 200  ❌ {"success":true,"results":[],"message":"找到 0 条结果"}

    后果和当年快手那个 bug 一模一样：**画布 / 博主中心的"作品搜索"**
    选到未实现平台时，用户看到的是"没搜到"，而不是"这个平台没实现"。
    这正是 `docs/platform/ADDING_A_PLATFORM.md` 铁律第 2 条禁止的假阴性。

    所以这里用**同一个注册表**判断，保证两个端点行为一致
    （不要维护第二份"支持列表"——两份名单必然会漂移）。
    """
    logger.info(
        "[search] platform=%s keyword=%s max=%s conn=%s",
        req.platform, req.keyword, req.max_results, bool(req.conn_id),
    )

    # 未实现的平台显式报 501（与 `search_enhanced` 同一判据）
    from app.services.platforms import supported_platforms

    if req.platform not in supported_platforms():
        raise HTTPException(
            status_code=501,
            detail=(
                f"平台 {req.platform!r} 尚未实现采集（不是「没搜到」）。"
                f"当前可用：{', '.join(sorted(supported_platforms()))}。"
                "如需新增该平台，见 docs/platform/ADDING_A_PLATFORM.md。"
            ),
        )

    try:
        service = get_crawler_service()
        results = await service.search_videos(
            platform=req.platform,
            keyword=req.keyword,
            max_results=req.max_results,
            conn_id=req.conn_id,
            cookie=_get_conn_cookie(req.conn_id) if req.conn_id else "",
        )

        return SearchResponse(
            success=True,
            results=results,
            total=len(results),
            message=f"找到 {len(results)} 条结果",
            using="MediaCrawler" if getattr(service, "use_mediacrawler", False) else "platforms",
        )
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except LoginExpiredError as e:
        # ⚠️ **登录态失效 → 401**（2026-10-01 补，与 `search_enhanced` 对齐）
        #
        # 这个端点（画布 platform_search 节点 + 博主中心"作品搜索"）
        # 原来没有这个分支，快手登录过期时返回
        # `HTTP 500 "搜索失败: ..."` —— 服务端没坏，是登录过期了。
        # 用户看到"搜索失败"不会想到"该重新登录"。
        logger.warning("[search] %s 登录态失效：%s", req.platform, str(e)[:140])
        raise HTTPException(
            status_code=401,
            detail=(
                f"{e}\n\n"
                "这是**登录态失效**（不是「没搜到」，也不是服务端故障）。"
                "请到「账号中心」重新获取该平台登录态后重试。"
            ),
        )
    except Exception as e:
        logger.error(f"[search] Error: {e}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@router.post("/import", summary="导入到素材库", response_model=ImportResponse)
async def import_to_assets(
    req: ImportRequest,
    principal: AuthenticatedPrincipal | None = Depends(
        get_authenticated_principal_optional
    ),
):
    """
    将采集结果导入到 YLCraft 素材库

    **必须带上 owner_user_id**（2026-09-27 修）：
    素材库列表按登录用户过滤（`owner_user_id`）。原来这里不传 owner，
    导入的记录 owner 为 NULL —— 结果就是**导入成功但用户在界面上看不到**，
    实测表现为"素材库一直是空的"。legacy NULL 记录只在
    `apply_owner_filter` 关闭时才可见，普通登录用户看不到。
    """
    owner_user_id = principal_owner_user_id(principal)
    logger.info(
        f"[import] Importing {len(req.results)} results to asset library "
        f"(owner={owner_user_id})"
    )

    try:
        # 转换 dict 到 CrawlerResult
        from app.services.crawler import CrawlerResult
        results = [CrawlerResult(**r) for r in req.results]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"数据格式错误: {str(e)}")

    try:
        service = get_crawler_service()
        asset_ids = await service.import_to_asset_library(
            results, owner_user_id=owner_user_id,
        )

        return ImportResponse(
            success=True,
            imported_count=len(asset_ids),
            asset_ids=asset_ids,
            message=f"成功导入 {len(asset_ids)} 条素材到素材库",
        )
    except Exception as e:
        logger.error(f"[import] Error: {e}")
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


@router.get("/tasks/{task_id}", summary="查询采集任务状态")
async def get_task_status(task_id: str):
    """查询异步采集任务状态"""
    task_data = _crawler_tasks.get(task_id)
    if not task_data:
        raise HTTPException(status_code=404, detail="任务不存在")

    return task_data


# =============================================================================
# 新增：增强搜索 & 笔记详情端点
# =============================================================================


@router.post("/search-enhanced", summary="增强搜索（支持笔记/用户）", response_model=SearchResponse)
async def search_enhanced(req: SearchEnhancedRequest):
    """
    增强搜索：支持搜索笔记和用户
    - search_type: "note" = 搜索笔记, "user" = 搜索用户, "article" = 搜索专栏
    - sort_by: 排序方式（各平台自定义）
    - filters: 可选筛选条件
    """
    logger.info(
        "[search_enhanced] platform=%s keyword=%s type=%s sort=%s authenticated=%s",
        req.platform, req.keyword, req.search_type, req.sort_by, bool(req.conn_id),
    )

    # ===== 微信公众号特殊处理 =====
    if req.platform == "wechat_mp":
        return await _search_wechat_mp(req)

    service = get_crawler_service()

    # ⚠️ **平台没实现要显式报错，不能静默返回空**（2026-09-29）
    #
    # 实测：前端搜索页的下拉里有「快手」可点，但后端**没有快手客户端**。
    # 原来的行为是：
    #
    #     日志：Unsupported platform: kuaishou. Available: [...]
    #     响应：HTTP 200 {"success": true, "results": [],
    #                    "message": "找到 0 条结果"}
    #
    # **用户看到的是"没搜到"**，完全不知道是"这个平台还没实现" ——
    # 假阴性，排查时最费时间（本仓库的 `ADDING_A_PLATFORM.md` 把它列为铁律）。
    #
    # 判据：用 `platforms` 模块的注册表判断，而不是维护第二份名单。
    from app.services.platforms import supported_platforms

    if req.platform not in supported_platforms():
        raise HTTPException(
            status_code=501,
            detail=(
                f"平台 {req.platform!r} 尚未实现采集（不是「没搜到」）。"
                f"当前可用：{', '.join(sorted(supported_platforms()))}。"
                "如需新增该平台，见 docs/platform/ADDING_A_PLATFORM.md。"
            ),
        )

    # ===== 普通搜索模式 =====
    try:
        _t0 = time.time()
        using = "platforms"
        results = await service.search_videos(
            platform=req.platform,
            keyword=req.keyword,
            max_results=req.max_results,
            search_type=req.search_type,
            sort_by=req.sort_by,
            order_sort=req.order_sort,
            page=req.page,
            filters=req.filters,
            conn_id=req.conn_id,
            cookie=_get_conn_cookie(req.conn_id) if req.conn_id else "",
        )

        if not results:
            logger.warning(f"[search_enhanced] No results via platforms module for {req.platform}")

        # 从第一个结果的 raw_data 中提取平台返回的真实总条数
        #
        # ⚠️ 注意 `total` 的语义是**"本次返回的条数"**，不一定是"平台总数"：
        # 有些平台（如小红书）**不给真实 total**，只给 `has_more`。
        # 此时 total = 本页条数，前端不该把它显示成"共 N 条"
        # （用户会以为只有这么多，但翻页明明还有）。
        # 所以额外透出 `has_more`，让前端能表达"还有更多"。
        total = len(results)
        has_more = False
        # ⚠️ **游标翻页的数据源**（2026-10-03）
        #
        # `dialogs`（我的频道）/ `saved`（我的收藏）**不用页码翻页** ——
        # 它们是"我的东西"，MTProto 用游标 `offset_id`（"取比它更旧的"）。
        # 所以要把**可继续翻的起点**告诉前端：取**最后一条**的 cursor_id。
        # （传第一条会把它自己也包含回来，实测重叠 4 条。）
        next_cursor = ""
        if results:
            rd = results[0].raw_data or {}
            if rd.get("_total"):
                total = rd["_total"]
            has_more = bool(rd.get("_has_more"))
            if req.platform == "telegram" and req.search_type in ("saved", "dialogs", "channels", "my"):
                cands = [r.raw_data.get("cursor_id") for r in results if r.raw_data.get("cursor_id")]
                if cands:
                    next_cursor = str(cands[-1])

        # 记一条健康度事件（**best-effort**，失败不影响搜索）
        #
        # ⚠️ 2026-10-01 加：`platform_event_logs` 原本只记 LLM/图片等
        # AI 场景，**没有平台采集记录** → `/platforms/{p}/stats` 无数据可算。
        # 这里开始记录，历史统计才有来源。
        try:
            from app.api.v1.platform_stats import record_platform_event

            await record_platform_event(
                req.platform,
                f"search_{req.search_type or 'note'}",
                success=True,
                duration_ms=int((time.time() - _t0) * 1000),
                conn_id=req.conn_id or "",
                extra={"count": len(results), "keyword_len": len(req.keyword or "")},
            )
        except Exception:
            pass

        return SearchResponse(
            success=True,
            results=results,
            total=total,
            has_more=has_more,
            message=f"找到 {total} 条结果",
            using=using,
            pagination=pagination_info(req.platform),
            next_cursor=next_cursor,
        )
    except Exception as e:
        # ⚠️ **登录态/风控类错误要给可读状态码，不是笼统的 500**（2026-09-29）
        #
        # 实测：小红书被风控时接口返回 461，原来会被
        # `search_videos` 吞掉并降级 → 响应变成
        # `{"success": true, "results": [], "message": "找到 0 条结果"}`
        # —— 用户完全不知道是被风控了。
        #
        # 现在 service 层不再吞（见 `CrawlerService.search_videos`），
        # 这里再把"平台侧拒绝"映射成 **429**（稍后重试/去登录），
        # 而不是 500（服务端故障）—— 语义不同，前端提示也不同。
        msg = str(e)

        # 记一条**失败**事件（best-effort）—— 统计里的成功率靠它
        try:
            from app.api.v1.platform_stats import record_platform_event

            await record_platform_event(
                req.platform,
                f"search_{req.search_type or 'note'}",
                success=False,
                duration_ms=int((time.time() - _t0) * 1000),
                error=f"{type(e).__name__}: {msg}",
                conn_id=req.conn_id or "",
            )
        except Exception:
            pass

        # ⚠️ **登录态失效要单独映射成 401**（2026-10-01 补）
        #
        # 实测：快手 cookie 过期后搜索返回
        #
        #     [kuaishou] 未能获取 /rest/v/search/feed 的接口签名
        #     → HTTP 500 "搜索失败: ..."
        #
        # **500 是错的** —— 服务端没坏，是登录态过期了。
        # 用户看到"搜索失败"只会以为是 bug，不会想到"该重新登录了"。
        #
        # 这个异常在 `get_self_profile`（账号中心）早就映射成 401 了，
        # 但**搜索路径漏了** —— 同一类"守卫只加在一个入口"的毛病。
        # 注意顺序：必须放在下面的 429 判断**之前**
        # （快手的报错文本里带 `/rest/v/...`，但 429 那组关键词
        #   是 461/403/401/风控/antispam，不会误命中；不过显式优先更安全）。
        # ⚠️ **按异常类型映射状态码**（2026-10-01 重构，替代字符串匹配）
        #
        # 原来这里也是关键词匹配（`any(k in msg for k in ("461", "风控", ...))`）
        # —— 与 service 层同样的问题：改文案就静默失效。
        # 现在看异常类型 + 它自己声明的 `retryable` 语义。
        #
        # 映射表：
        #   NotImplementedError  → 501（功能没做，不是服务端故障）
        #   LoginExpiredError    → 401（重新登录，用户能自己解决）
        #   RiskControlError     → 429（风控，等一会儿 / 换 IP）
        #   ContentNotFoundError → 404（内容不存在）
        #   NetworkError         → 503（网络问题，稍后重试）

        # ⚠️ **`NotImplementedError` → 501**（2026-10-02 补）
        #
        # ⚠️⚠️ 又一次「守卫只加在一个入口」：
        # `search_materials`（本文件 L335）**早就有**这个映射，
        # 但 `search_enhanced` **漏了** —— 于是番茄这种
        # "client 里 raise NotImplementedError"的平台会穿透到
        # 最后的 `except Exception` → **HTTP 500**「搜索失败: 番茄搜索暂未实现」。
        #
        # 500 在语义上是"服务端故障"，用户会以为要重试/报 bug，
        # 而真相是"这个平台没做搜索"（应该是 501）。
        if isinstance(e, NotImplementedError):
            logger.info(
                "[search_enhanced] %s 未实现该能力：%s", req.platform, msg[:140]
            )
            raise HTTPException(
                status_code=501,
                detail=(
                    f"{msg}\n\n"
                    "这是**该平台没有这个能力**（不是「没搜到」，也不是服务端故障）。"
                ),
            )

        if isinstance(e, LoginExpiredError):
            logger.warning(
                "[search_enhanced] %s 登录态失效：%s", req.platform, msg[:140]
            )
            raise HTTPException(
                status_code=401,
                detail=(
                    f"{msg}\n\n"
                    "这是**登录态失效**（不是「没搜到」，也不是服务端故障）。"
                    "请到「账号中心」重新获取该平台登录态后重试。"
                ),
            )
        if isinstance(e, ContentNotFoundError):
            raise HTTPException(
                status_code=404,
                detail=f"{msg}\n\n（内容不存在或已被删除，不是「没搜到」。）",
            )
        if isinstance(e, RiskControlError):
            logger.warning("[search_enhanced] %s 平台侧拒绝：%s", req.platform, msg[:140])
            raise HTTPException(
                status_code=429,
                detail=(
                    f"{msg}\n\n"
                    "这是**平台侧拒绝**（触发风控或人机验证），不是「没搜到」。可尝试：\n"
                    "  1. 稍等一会儿再试（风控常是临时性的）\n"
                    "  2. 到「账号中心」重新获取该平台登录态\n"
                    "  3. 用搜索框旁的「去官网搜」在浏览器里手动搜索"
                ),
            )
        if isinstance(e, NetworkError):
            logger.warning("[search_enhanced] %s 网络问题：%s", req.platform, msg[:140])
            raise HTTPException(
                status_code=503,
                detail=(
                    f"{msg}\n\n"
                    "这是**网络问题**（不是「没搜到」）。请检查网络/代理后重试。"
                ),
            )
        if isinstance(e, PlatformError):
            # ⚠️ 兜底但**不掩盖**：已知语义的类型都已在上面单独处理
            # （LoginExpired→401 / NotImplemented→501 / ContentNotFound→404
            #   / RiskControl→429 / Network→503）。
            # 走到这里的都是"平台侧明确说了原因、但没给 HTTP 语义"的情况
            # （如 Telegram 的频道不存在 / 未开放网页端），它们**不是服务端故障**，
            # 所以给 400（请求本身有问题）+ 平台给的原因，
            # **不能落到 500** —— 那会让用户以为是应用崩了。
            logger.warning(
                "[search_enhanced] %s 平台侧失败（非风控/非登录/非网络）：%s",
                req.platform, msg[:140],
            )
            raise HTTPException(
                status_code=400,
                detail=f"{msg}\n\n（这是**平台侧无法完成该操作**（不是「没搜到」，也不是服务端故障）。）",
            )
        logger.error(f"[search_enhanced] Error: {e}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@router.get("/note-detail", summary="获取笔记详情（无水印）", response_model=NoteDetailResponse)
async def get_note_detail(platform: str, note_id: str, conn_id: str = "",
                          keyword: str = "", xsec_token: str = ""):
    """
    获取笔记详情（无水印图片 & 视频）
    - platform: 平台（xhs/dy/ks/bili/wechat_mp）
    - note_id: 笔记ID
    - conn_id: 可选，使用指定连接的 Cookie
    - keyword: 可选，搜索关键词（**没有 token 时**的兜底路径用）
    - xsec_token: 可选，**小红书详情必需**。

      ⚠️ 实测：小红书详情**直接访问带 `xsec_token` 的链接即可**，
      没有 token 才会跳回首页。所以前端把搜索结果里的 token 传过来，
      后端直接拼 `explore/{id}?xsec_token=...` 打开 —— 比"搜索→点击"
      快得多，也不会因为"笔记不在当前搜索结果里"而失败。
    """
    logger.info(
        f"[get_note_detail] platform={platform} note_id={note_id} "
        f"keyword={keyword!r} has_token={bool(xsec_token)}"
    )

    # 微信公众号特殊处理：公众号账号没有"笔记详情"概念，返回空结果
    # 前端会直接使用搜索结果中的数据显示详情
    if platform == "wechat_mp":
        return NoteDetailResponse(
            success=True,
            data={
                "id": note_id,
                "platform": "wechat_mp",
                "title": "",
                "desc": "",
                "images": [],
                "video": "",
                "video_cover": "",
                "video_duration": 0,
                "author": "",
                "author_id": "",
                "author_avatar": "",
                "like_count": 0,
                "comment_count": 0,
                "share_count": 0,
                "view_count": 0,
                "create_time": "",
                "tags": [],
                "raw_data": {},
            },
            message="微信公众号详情由前端直接展示",
        )

    # 获取 Cookie
    #
    # ⚠️ 用 `_get_conn_cookie`（它是同步的、已规范化、且是**本文件既有的
    # 正确实现**）。这里原本是自己抄了一份 async 取 cookie 的逻辑，
    # 结果调错了 service 方法 → 拿到空 cookie →
    # 小红书详情直接报"需要登录 Cookie"（实测踩过）。
    cookie = _get_conn_cookie(conn_id) if conn_id else ""

    try:
        service = get_crawler_service()
        detail = await service.get_note_detail(
            platform, note_id, cookie, keyword=keyword, xsec_token=xsec_token
        )

        if not detail:
            raise HTTPException(status_code=404, detail="笔记不存在或获取失败")

        # 转换 dict 到 NoteDetail 模型
        from app.services.crawler.models import NoteDetail
        note_detail = NoteDetail(**detail)

        return NoteDetailResponse(
            success=True,
            data=note_detail,
            message="获取成功",
        )
    except HTTPException:
        raise
    except LoginExpiredError as e:
        # ⚠️ 登录态失效 → **401**（与搜索端点一致，2026-10-01）
        # 原来落到底下 `except Exception` → 500，
        # 或被 service 层吞成 {} → **404 "笔记不存在"**（更糟）。
        logger.warning("[get_note_detail] %s 登录态失效：%s", platform, str(e)[:140])
        raise HTTPException(
            status_code=401,
            detail=(
                f"{e}\n\n"
                "这是**登录态失效**（不是「笔记不存在」）。"
                "请到「账号中心」重新获取该平台登录态后重试。"
            ),
        )
    except PlatformUnavailableError as e:
        # ⚠️ 平台侧拒绝（风控/UA/空 body）→ **429**（可重试），
        # 不是 404"不存在"也不是 500"服务端故障"。
        logger.warning("[get_note_detail] %s 平台侧拒绝：%s", platform, str(e)[:140])
        raise HTTPException(
            status_code=429,
            detail=(
                f"{e}\n\n"
                "这是**平台侧拒绝**（通常可稍后重试解决），"
                "不是「笔记不存在」。可尝试：\n"
                "  1. 稍等一会儿再试\n"
                "  2. 到「账号中心」重新获取该平台登录态"
            ),
        )
    except Exception as e:
        logger.error(f"[get_note_detail] Error: {e}")
        raise HTTPException(status_code=500, detail=f"获取笔记详情失败: {str(e)}")


@router.post("/fetch-no-watermark", summary="批量获取无水印资源")
async def fetch_no_watermark(req: FetchNoWatermarkRequest):
    """
    批量获取无水印图片/视频
    输入：平台 + 笔记ID列表
    输出：下载链接列表
    """
    logger.info(f"[fetch_no_watermark] platform={req.platform} note_count={len(req.note_ids)}")

    try:
        service = get_crawler_service()
        results = []

        for note_id in req.note_ids:
            try:
                detail = await service.get_note_detail(req.platform, note_id, "")
                if detail:
                    results.append({
                        "note_id": note_id,
                        "images": detail.get("images", []),
                        "video": detail.get("video", ""),
                        "title": detail.get("title", ""),
                    })
            except Exception as e:
                logger.error(f"[fetch_no_watermark] Failed for {note_id}: {e}")
                continue

        return {
            "success": True,
            "results": results,
            "total": len(results),
            "message": f"成功获取 {len(results)} 条笔记的无水印资源",
        }
    except Exception as e:
        logger.error(f"[fetch_no_watermark] Error: {e}")
        raise HTTPException(status_code=500, detail=f"批量获取失败: {str(e)}")


# =============================================================================
# 微信公众号搜索（专用处理）
# =============================================================================

async def _search_wechat_mp(req: SearchEnhancedRequest) -> SearchResponse:
    """
    微信公众号搜索：根据 search_type 不同执行不同操作
    - "account": 搜索公众号
    - "article": 拉取文章列表（需在 filters 中传 fake_id）
    - "global_article": 按关键词搜索全网公众号文章
    """
    from app.services.wechat_mp import get_wechat_mp_service
    from app.db.models.platform_connection import PlatformConnection, PlatformType
    from app.services.platform_connection.service import PlatformConnectionService

    service = get_wechat_mp_service()

    # 从请求中获取 conn_id
    conn_id = req.filters.get("conn_id", "") if req.filters else ""

    # 从数据库获取连接的 Cookie / Token。
    # cookie_content 是 Netscape 文件格式，不能直接放进 HTTP Cookie header；
    # 这里统一通过 PlatformConnectionService 提取原始 "k=v; ..." 格式。
    cookie = ""
    token = ""
    db_session = None
    try:
        from app.db.database import SessionLocal

        db_session = SessionLocal()
        conn_service = PlatformConnectionService(db_session)
        conn: PlatformConnection | None = None
        if conn_id:
            conn = conn_service.get(conn_id)
        else:
            conn = conn_service.get_active(PlatformType.WECHAT_MP)
            conn_id = conn.id if conn else ""

        if conn:
            cookie = conn_service.get_raw_cookie(conn.id) or ""
            credentials = conn.get_credentials()
            token = (
                str(credentials.get("token") or "")
                or str(conn.account_id or "")
            )
            logger.info(
                "[_search_wechat_mp] using conn=%s, cookie=%s, token=%s",
                conn.id,
                "yes" if cookie else "no",
                "yes" if token else "no",
            )
    except Exception as e:
        logger.warning(f"[_search_wechat_mp] 获取凭证失败: {e}")
    finally:
        if db_session is not None:
            db_session.close()

    if not cookie or not token:
        raise HTTPException(
            status_code=400,
            detail="微信公众号连接缺少 Cookie 或 token，请先在账号中心完成扫码登录",
        )

    if req.search_type == "account":
        # 搜索公众号
        result = await service.search_accounts(
            conn_id=conn_id,
            keyword=req.keyword,
            cookie=cookie,
            token=token,
            page=req.page,
            page_size=req.max_results,
        )
        # 检查是否有错误（如会话失效）
        if result.get("error"):
            error_code = result.get("error_code")
            if error_code == 200003:
                raise HTTPException(
                    status_code=401,
                    detail="微信公众平台会话已失效，请重新登录",
                )
            raise HTTPException(
                status_code=500,
                detail=result["error"],
            )
        accounts = result.get("list", [])

        # 转换为 CrawlerResult 格式
        from app.services.crawler.service import CrawlerResult
        results = []
        for acc in accounts:
            results.append(CrawlerResult(
                id=acc.get("fake_id", ""),
                platform="wechat_mp",
                title=acc.get("nickname", ""),
                desc=acc.get("signature", ""),
                cover=acc.get("round_head_img", ""),
                author=acc.get("nickname", ""),
                author_id=acc.get("fake_id", ""),
                url=f"https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz={acc.get('fake_id', '')}",
                # 公众号账号本身没有"发布时间"，用空字符串
                create_time="",
                # 公众号没有粉丝数/文章数
                followers=0,
                videos=0,
                raw_data=acc,
            ))
        return SearchResponse(
            success=True,
            results=results,
            total=result.get("total", 0),
            message=f"找到 {result.get('total', 0)} 个公众号",
            using="wechat_mp_api",
        )

    elif req.search_type == "global_article":
        result = await service.search_global_articles(
            conn_id=conn_id,
            keyword=req.keyword,
            cookie=cookie,
            token=token,
            page=req.page,
            page_size=req.max_results,
        )

        if result.get("error"):
            error_code = result.get("error_code")
            if error_code == 200003:
                raise HTTPException(
                    status_code=401,
                    detail="微信公众平台会话已失效，请重新登录",
                )
            raise HTTPException(status_code=500, detail=f"搜索全网文章失败: {result.get('error')}")

        articles = result.get("list", [])
        from app.services.crawler.service import CrawlerResult
        results = []
        for art in articles:
            raw_data = dict(art)
            raw_data["conn_id"] = conn_id
            results.append(CrawlerResult(
                id=art.get("aid") or art.get("link", ""),
                platform="wechat_mp",
                title=art.get("title", ""),
                desc=art.get("digest", ""),
                cover=art.get("cover", ""),
                author=art.get("nickname") or art.get("author", ""),
                author_id="",
                url=art.get("link", ""),
                create_time="",
                raw_data=raw_data,
            ))
        return SearchResponse(
            success=True,
            results=results,
            total=result.get("total", 0),
            message=f"找到 {len(articles)} 篇相关文章（共约 {result.get('total', 0)} 篇）",
            using="wechat_mp_copyright_search",
        )

    elif req.search_type == "article":
        # 拉取文章列表
        fake_id = req.filters.get("fake_id", "") if req.filters else ""
        if not fake_id:
            return SearchResponse(
                success=True,
                results=[],
                total=0,
                message="请先搜索公众号，再从公众号详情中查看文章列表",
                using="wechat_mp_api",
            )

        result = await service.get_articles(
            conn_id=conn_id,
            fake_id=fake_id,
            cookie=cookie,
            token=token,
            begin=(req.page - 1) * req.max_results,
            count=min(req.max_results, 5),
        )

        if result.get("error"):
            raise HTTPException(status_code=500, detail=f"拉取文章列表失败: {result.get('error')}")

        articles = result.get("list", [])
        from app.services.crawler.service import CrawlerResult
        results = []
        for art in articles:
            results.append(CrawlerResult(
                id=art.get("aid", ""),
                platform="wechat_mp",
                title=art.get("title", ""),
                desc=art.get("digest", ""),
                cover=art.get("cover", ""),
                author="",
                author_id="",
                url=art.get("link", ""),
                create_time=datetime.fromtimestamp(art.get("create_time", 0)).isoformat() if art.get("create_time") else "",
                raw_data=art,
            ))
        return SearchResponse(
            success=True,
            results=results,
            total=result.get("total_count", 0),
            message=f"已获取 {len(articles)} 篇文章（共约 {result.get('total_count', 0)} 篇）",
            using="wechat_mp_api",
        )

    else:
        raise HTTPException(status_code=400, detail=f"微信公众号不支持 search_type={req.search_type}，请使用 account、article 或 global_article")
