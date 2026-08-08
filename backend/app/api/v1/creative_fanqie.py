"""
YLCraft — 创作项目 → 番茄小说 发布路由

挂载前缀：/api/v1/creative-projects
与现有创作项目接口同族，但本文件使用异步会话（涉及 httpx 网络调用）。

端点：
  - POST /{project_id}/publish-to-fanqie   批量/单章保存到番茄草稿
  - POST /{project_id}/fanqie/binding      设置项目番茄绑定
  - GET  /{project_id}/fanqie/binding      读取项目番茄绑定
  - GET  /{project_id}/fanqie/publish-preflight  发布前本地校验
  - GET  /{project_id}/fanqie/publish-status  查询发布记录
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.database import get_async_session_dependency
from app.services.platforms.fanqie.publish_service import FanqiePublishService
from app.services.platforms.fanqie.utils import (
    CookieExpiredError,
    FanqieError,
    ParamError,
    RiskControlError,
)

router = APIRouter()


# =============================================================================
# 请求模型
# =============================================================================

class FanqieChapterItem(BaseModel):
    content_id: str
    item_id: str = Field(min_length=1)
    chapter_number: Optional[int] = None
    title: Optional[str] = None


class PublishToFanqieRequest(BaseModel):
    conn_id: Optional[str] = None
    book_id: Optional[str] = None
    volume_id: Optional[str] = None
    volume_name: Optional[str] = None
    action: Literal["draft"] = "draft"
    chapters: List[FanqieChapterItem] = Field(default_factory=list)


class FanqieBindingRequest(BaseModel):
    conn_id: str
    book_id: str
    volume_id: str
    volume_name: str = ""


# =============================================================================
# 依赖
# =============================================================================

async def get_service(session: AsyncSession = Depends(get_async_session_dependency)) -> FanqiePublishService:
    return FanqiePublishService(session)


def _fanqie_error_to_http(e: Exception) -> HTTPException:
    if isinstance(e, CookieExpiredError):
        return HTTPException(status_code=401, detail=f"番茄登录态失效，请重新登录并刷新 cookie：{e}")
    if isinstance(e, ParamError):
        return HTTPException(status_code=400, detail=f"番茄参数错误（book_id/item_id 等）：{e}")
    if isinstance(e, RiskControlError):
        return HTTPException(status_code=403, detail=f"番茄触发风控/审核：{e}")
    if isinstance(e, FanqieError):
        return HTTPException(status_code=502, detail=f"番茄接口返回失败：{e}")
    return HTTPException(status_code=400, detail=str(e))


# =============================================================================
# 端点
# =============================================================================

@router.post("/{project_id}/publish-to-fanqie", summary="保存章节到番茄草稿")
async def publish_to_fanqie(
    project_id: str,
    req: PublishToFanqieRequest,
    svc: FanqiePublishService = Depends(get_service),
):
    """将创作项目的一章或多章正文推送到番茄作家后台（存草稿）。

    conn_id / book_id / volume_id / volume_name 可省略，省略时回退到项目的番茄绑定。
    """
    if not req.chapters:
        raise HTTPException(status_code=400, detail="chapters 不能为空")

    # 回退到项目绑定
    binding = await svc.get_binding(project_id)
    conn_id = req.conn_id or binding.get("conn_id")
    book_id = req.book_id or binding.get("book_id")
    volume_id = req.volume_id or binding.get("volume_id")
    volume_name = req.volume_name or binding.get("volume_name", "")

    missing = [name for name, val in (("conn_id", conn_id), ("book_id", book_id), ("volume_id", volume_id)) if not val]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"缺少必填参数且项目未设置绑定：{', '.join(missing)}（请先设置项目番茄绑定）",
        )

    items = [c.model_dump() for c in req.chapters]
    try:
        results = await svc.publish_chapters_bulk(
            project_id=project_id,
            conn_id=conn_id,
            book_id=book_id,
            volume_id=volume_id,
            volume_name=volume_name,
            items=items,
            action=req.action,
        )
    except (CookieExpiredError, ParamError, RiskControlError, FanqieError, ValueError) as e:
        raise _fanqie_error_to_http(e) from e

    success = sum(1 for r in results if r.get("success"))
    return {
        "success": True,
        "data": {
            "total": len(results),
            "success": success,
            "failed": len(results) - success,
            "results": results,
        },
    }


@router.post("/{project_id}/fanqie/binding", summary="设置项目番茄绑定")
async def set_fanqie_binding(
    project_id: str,
    req: FanqieBindingRequest,
    svc: FanqiePublishService = Depends(get_service),
):
    try:
        binding = await svc.set_binding(
            project_id,
            conn_id=req.conn_id,
            book_id=req.book_id,
            volume_id=req.volume_id,
            volume_name=req.volume_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"success": True, "data": binding}


@router.get("/{project_id}/fanqie/binding", summary="读取项目番茄绑定")
async def get_fanqie_binding(
    project_id: str,
    svc: FanqiePublishService = Depends(get_service),
):
    binding = await svc.get_binding(project_id)
    return {"success": True, "data": binding}


@router.get("/{project_id}/fanqie/publish-preflight", summary="预检番茄章节发布")
async def preview_fanqie_publish(
    project_id: str,
    content_id: str = Query(...),
    item_id: str = Query(default=""),
    conn_id: str = Query(default=""),
    book_id: str = Query(default=""),
    volume_id: str = Query(default=""),
    volume_name: str = Query(default=""),
    svc: FanqiePublishService = Depends(get_service),
):
    """Return local readiness for one selected Fanqie draft target.

    The endpoint deliberately does not validate the cookie remotely. That
    avoids accidental platform traffic while a user is still editing a target.
    """
    preview = await svc.preview_chapter(
        project_id=project_id,
        content_id=content_id,
        item_id=item_id,
        conn_id=conn_id,
        book_id=book_id,
        volume_id=volume_id,
        volume_name=volume_name,
    )
    return {"success": True, "data": preview}


@router.get("/{project_id}/fanqie/publish-status", summary="查询番茄发布记录")
async def get_fanqie_publish_status(
    project_id: str,
    chapter_number: Optional[int] = Query(default=None),
    svc: FanqiePublishService = Depends(get_service),
):
    records = await svc.get_publish_status(project_id, chapter_number=chapter_number)
    return {"success": True, "data": records}
