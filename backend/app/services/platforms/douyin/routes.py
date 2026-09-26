"""
YLCraft — 抖音平台路由

搜索主入口在 /api/v1/crawler/search-enhanced（platform=douyin），
本文件提供抖音专属的轻量端点（客户端健康检查）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.user_auth import AuthenticatedPrincipal, get_authenticated_principal
from app.services.platforms.types import ClientConfig, ClientMode

router = APIRouter()


def _get_conn_cookie_sync(conn_id: str) -> str:
    """取连接的 cookie（同步，仅读一行；调用方用 to_thread 包住）。"""
    from app.db.database import SessionLocal
    from app.db.models.platform_connection import PlatformConnection

    s = SessionLocal()
    try:
        conn = s.get(PlatformConnection, conn_id)
        return conn.cookie_content if conn else ""
    finally:
        s.close()


@router.get("/health", summary="抖音客户端健康检查")
async def douyin_health(
    principal: AuthenticatedPrincipal | None = Depends(get_authenticated_principal),
):
    """验证抖音客户端已注册。"""
    from app.services.platforms import create_client

    client = create_client("douyin", mode="api", cookie="probe=1")
    if client is None:
        raise HTTPException(status_code=503, detail="抖音客户端未注册")
    return {"success": True, "client": "DouyinClient", "registered": True}


@router.post("/search", summary="抖音搜索（直连）")
async def douyin_search(
    keyword: str,
    conn_id: str = "",
    count: int = 10,
    offset: int = 0,
    principal: AuthenticatedPrincipal = Depends(get_authenticated_principal),
):
    """抖音综合搜索。

    与 /api/v1/crawler/search-enhanced?platform=douyin 等价，但直接返回
    抖音结构（含 cursor/has_more 分页信息），便于前端翻页。
    """
    import asyncio

    from app.services.platforms.douyin.client import DouyinClient

    if not conn_id:
        raise HTTPException(status_code=400, detail="需要 conn_id（抖音搜索必须用已保存的登录 Cookie）")

    cookie = await asyncio.to_thread(_get_conn_cookie_sync, conn_id)
    if not cookie:
        raise HTTPException(status_code=404, detail="连接不存在或无 Cookie")

    client = DouyinClient(ClientConfig(platform="douyin", mode=ClientMode.API, cookie=cookie))
    async with client:
        page = await client.search_page(keyword=keyword, offset=offset, count=max(1, min(count, 20)))

    return {
        "success": True,
        "data": {
            "items": [r.__dict__ | {"raw_data": {}} for r in page["items"]],
            "cursor": page["cursor"],
            "has_more": page["has_more"],
            "offset": page["offset"],
            "count": page["count"],
        },
    }
