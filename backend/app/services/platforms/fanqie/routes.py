"""
番茄小说作家后台 API 路由

挂载前缀：/api/v1/fanqie

与 B站（`services/platforms/bilibili/routes.py`）对齐：平台专属逻辑放在这里，
凭证统一走 `PlatformConnection`（cookie_content）。

端点：
  - GET /my/books                      我的书籍列表（✅ 已验证：book_list/v0/）
  - GET /book/{book_id}/stats          单本书数据统计（✅ 已验证：book_common_v1/v0/）
  - GET /hot-list                      热门故事 / 开书灵感（✅ 已验证：douyin_hot_list/v0/）
  - GET /my/profile                    作家资料（⏳ 占位，待 Phase 3 抓包）
  - GET /book/{book_id}/chapters       章节列表（⏳ 占位，待 Phase 3 抓包）
  - GET /earnings                      收益分析（⏳ 占位，待 Phase 3 抓包）

安全护栏：
  - 所有调用均为只读 GET，绝不改动用户线上数据。
  - 作家昵称/头像等需在「作家资料」接口抓包后（Phase 3）补全。
  - 建书 / 建卷 / 建章节不在 YLCraft 内完成，item_id 须用户在 Web 端建好。
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.database import get_async_session_dependency
from app.db.models.platform_connection import PlatformConnection
from app.services.platforms.fanqie.client import FanqieClient
from app.services.platforms.fanqie.utils import (
    CookieExpiredError,
    FanqieError,
    ParamError,
    RiskControlError,
)
from app.services.platforms.types import ClientConfig, ClientMode

logger = logging.getLogger("ylcraft.api.fanqie")

router = APIRouter()


# =============================================================================
# 依赖与辅助
# =============================================================================

async def get_session(session: AsyncSession = Depends(get_async_session_dependency)) -> AsyncSession:
    return session


def _fanqie_error_to_http(e: Exception) -> HTTPException:
    if isinstance(e, CookieExpiredError):
        return HTTPException(status_code=401, detail=f"番茄登录态失效，请重新登录并刷新 cookie：{e}")
    if isinstance(e, ParamError):
        return HTTPException(status_code=400, detail=f"番茄参数错误（book_id 等）：{e}")
    if isinstance(e, RiskControlError):
        return HTTPException(status_code=403, detail=f"番茄触发风控/审核：{e}")
    if isinstance(e, FanqieError):
        return HTTPException(status_code=502, detail=f"番茄接口返回失败：{e}")
    return HTTPException(status_code=400, detail=str(e))


async def _get_client(session: AsyncSession, conn_id: str) -> FanqieClient:
    """
    按连接 ID 构建 FanqieClient（cookie 取自 PlatformConnection.cookie_content）。
    连接不存在或未配置 cookie 时返回 404。
    """
    conn = await session.get(PlatformConnection, conn_id)
    if not conn or not conn.cookie_content:
        raise HTTPException(status_code=404, detail="番茄凭证不存在或未配置 cookie（请先在平台连接中保存 cookie）")
    config = ClientConfig(platform="fanqie", mode=ClientMode.API, cookie=conn.cookie_content)
    return FanqieClient(config)


# =============================================================================
# 已验证端点（只读，真实调用）
# =============================================================================

@router.get("/my/books", summary="我的书籍列表（番茄作家后台）")
async def my_books(
    conn_id: str = Query(..., description="番茄平台连接 ID"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """返回作家后台「我的书籍」列表（已验证只读接口）。"""
    client = await _get_client(session, conn_id)
    try:
        async with client:
            data = await client.get_my_books(page=page, size=size)
        return {"success": True, "data": data}
    except Exception as e:  # noqa: BLE001
        raise _fanqie_error_to_http(e) from e


@router.get("/book/{book_id}/stats", summary="单本书数据统计")
async def book_stats(
    book_id: str,
    conn_id: str = Query(..., description="番茄平台连接 ID"),
    stats_type: int = Query(
        1,
        description="统计 Tab：1=基础数据（阅读/追更/完读率等）；质量分析/流量构成等其它值待 Phase 3 抓包确认",
    ),
    session: AsyncSession = Depends(get_session),
):
    """返回单本书的阅读/在读/评分等统计（已验证只读接口 book_common_v1/v0）。"""
    client = await _get_client(session, conn_id)
    try:
        async with client:
            data = await client.get_book_stats(book_id, stats_type=stats_type)
        return {"success": True, "data": data}
    except Exception as e:  # noqa: BLE001
        raise _fanqie_error_to_http(e) from e


@router.get("/hot-list", summary="热门故事 / 开书灵感")
async def hot_list(
    conn_id: str = Query(..., description="番茄平台连接 ID"),
    hot_type: int = Query(0, description="类型，默认 0"),
    session: AsyncSession = Depends(get_session),
):
    """返回热门故事 / 开书灵感列表（已验证只读接口）。"""
    client = await _get_client(session, conn_id)
    try:
        async with client:
            data = await client.get_hot_list(hot_type=hot_type)
        return {"success": True, "data": data}
    except Exception as e:  # noqa: BLE001
        raise _fanqie_error_to_http(e) from e


# =============================================================================
# 占位端点（待 Phase 3 抓包补齐）
# =============================================================================

@router.get("/my/profile", summary="作家资料（占位，待 Phase 3）")
async def my_profile(
    conn_id: str = Query(..., description="番茄平台连接 ID"),
    session: AsyncSession = Depends(get_session),
):
    """
    作家资料（昵称 / 头像 / 总阅读 / 总粉丝等）。

    ⏳ 尚未抓包对应接口，先返回「未抓包」提示，避免返回假数据误导用户。
     Phase 3 将补齐 `get_my_profile(writer_id)` 并替换本占位。
    """
    return {
        "success": False,
        "not_captured": True,
        "message": "作家资料接口尚未抓包（Phase 3）。当前可用：/my/books、/book/{id}/stats、/hot-list。",
    }


@router.get("/book/{book_id}/chapters", summary="章节列表（占位，待 Phase 3）")
async def book_chapters(
    book_id: str,
    conn_id: str = Query(..., description="番茄平台连接 ID"),
):
    """
    书籍章节列表（用于自动映射 item_id）。

    ⏳ 尚未抓包对应接口，先返回「未抓包」提示。
    注：建书 / 建卷 / 建章节请在番茄 Web 端完成，item_id 由你填入 YLCraft 发布面板。
    """
    return {
        "success": False,
        "not_captured": True,
        "message": "章节列表接口尚未抓包（Phase 3）。建书/建卷/建章节请在番茄 Web 端完成，item_id 由你填入。",
    }


@router.get("/earnings", summary="收益分析（占位，待 Phase 3）")
async def earnings(
    conn_id: str = Query(..., description="番茄平台连接 ID"),
):
    """
    收益分析（分成 / 打赏 / 稿酬等）。

    ⏳ 尚未抓包对应接口，先返回「未抓包」提示。
    """
    return {
        "success": False,
        "not_captured": True,
        "message": "收益分析接口尚未抓包（Phase 3）。",
    }
