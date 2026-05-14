"""
YLCraft — Cookie 自动获取 API

Playwright 浏览器自动化获取：
  POST  /api/v1/platforms/acquire/playwright/start          — 启动浏览器会话
  WS    /api/v1/platforms/acquire/playwright/{sid}/ws      — WebSocket 状态推送
  POST  /api/v1/platforms/acquire/playwright/{sid}/cancel  — 取消会话
  GET   /api/v1/platforms/acquire/playwright/sessions       — 列出活跃会话

QrCode 二维码扫码获取：
  POST  /api/v1/platforms/acquire/qrcode/generate          — 生成登录二维码
  WS    /api/v1/platforms/acquire/qrcode/{sid}/ws           — WebSocket 等待扫码结果
  GET   /api/v1/platforms/acquire/qrcode/{sid}/status       — 轮询扫码状态
  POST  /api/v1/platforms/acquire/qrcode/{sid}/refresh      — 刷新过期二维码
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.services.cookie_acquisition.base import (
    AcquisitionStatus,
    get_status_message,
)
from app.services.cookie_acquisition.playwright_manager import get_playwright_manager
from app.services.cookie_acquisition.qrcode_manager import get_qrcode_manager
from app.services.cookie_acquisition.platforms import (
    get_supported_playwright_platforms,
    get_supported_qrcode_platforms,
)

logger = logging.getLogger("ylcraft.api.cookie_acquisition")

router = APIRouter(prefix="/acquire", tags=["Cookie Acquisition"])


# =============================================================================
# Request / Response 模型
# =============================================================================

class PlaywrightStartRequest(BaseModel):
    """Playwright 启动请求"""
    platform: str
    headless: bool = False
    connector_name: str = ""
    stealth: bool = True


class PlaywrightStartResponse(BaseModel):
    """Playwright 启动响应"""
    success: bool
    session_id: str = ""
    message: str = ""


class QrcodeGenerateRequest(BaseModel):
    """QrCode 生成请求"""
    platform: str
    connector_name: str = ""


class QrcodeGenerateResponse(BaseModel):
    """QrCode 生成响应"""
    success: bool
    session_id: str = ""
    qr_image_base64: str = ""
    expires_in: int = 120
    message: str = ""


class SessionStatusResponse(BaseModel):
    """会话状态响应"""
    session_id: str
    platform: str
    method: str
    status: str
    message: str
    error_message: Optional[str] = None
    connector_id: Optional[str] = None


# =============================================================================
# Playwright API
# =============================================================================

@router.post("/playwright/start", summary="启动浏览器获取 Cookie")
async def playwright_start(req: PlaywrightStartRequest):
    """启动 Playwright 浏览器会话，用户在浏览器中登录后自动提取 Cookie"""
    manager = get_playwright_manager()

    if not manager.is_available():
        return PlaywrightStartResponse(
            success=False,
            message="Playwright 未安装。请运行: pip install playwright && playwright install chromium",
        )

    # 检查平台是否支持
    supported = get_supported_playwright_platforms()
    if req.platform not in supported:
        return PlaywrightStartResponse(
            success=False,
            message=f"平台 {req.platform} 暂不支持 Playwright 获取，支持: {', '.join(supported)}",
        )

    try:
        session_id = await manager.start_session(
            platform=req.platform,
            headless=req.headless,
            stealth=req.stealth,
            connector_name=req.connector_name,
        )

        session = manager.get_session(session_id)
        status_msg = get_status_message(session.status) if session else "启动中"

        return PlaywrightStartResponse(
            success=True,
            session_id=session_id,
            message=status_msg,
        )
    except Exception as e:
        logger.error(f"[CookieAcquisitionAPI] playwright_start failed: {e}")
        return PlaywrightStartResponse(
            success=False,
            message=str(e),
        )


@router.get("/playwright/sessions", summary="列出活跃的 Playwright 会话")
async def playwright_list_sessions():
    """列出所有活跃的 Playwright 会话"""
    manager = get_playwright_manager()
    sessions = manager.list_sessions()
    return {
        "success": True,
        "sessions": [
            {
                "session_id": s.session_id,
                "platform": s.platform,
                "status": s.status.value,
                "message": get_status_message(s.status),
                "page_url": s.page_url,
                "created_at": s.created_at.isoformat(),
            }
            for s in sessions
        ],
        "total": len(sessions),
    }


@router.post("/playwright/{session_id}/cancel", summary="取消 Playwright 会话")
async def playwright_cancel(session_id: str):
    """取消正在进行的 Playwright 会话"""
    manager = get_playwright_manager()
    ok = await manager.cancel_session(session_id)
    if ok:
        return {"success": True, "message": "会话已取消"}
    return {"success": False, "message": "会话不存在或已结束"}


@router.websocket("/playwright/{session_id}/ws")
async def playwright_ws(websocket: WebSocket, session_id: str):
    """Playwright 获取状态 WebSocket 推送"""
    await websocket.accept()

    manager = get_playwright_manager()
    session = manager.get_session(session_id)
    if not session:
        await websocket.send_json({
            "type": "error",
            "message": "会话不存在",
        })
        await websocket.close()
        return

    try:
        last_status = None
        while not session.is_terminal:
            if session.status != last_status:
                await websocket.send_json({
                    "type": "status_update",
                    "session_id": session_id,
                    "status": session.status.value,
                    "message": get_status_message(session.status),
                    "data": {
                        "page_url": session.page_url,
                        "cookies_count": len(session.cookies_array or []),
                    }
                })
                last_status = session.status

            await asyncio.sleep(0.5)

        # 发送终态
        await websocket.send_json({
            "type": "completed",
            "session_id": session_id,
            "status": session.status.value,
            "connector_id": session.connector_id,
            "message": get_status_message(session.status),
            "error_message": session.error_message,
        })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"[CookieAcquisitionAPI] playwright_ws error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })
        except Exception:
            pass


# =============================================================================
# QrCode API
# =============================================================================

@router.post("/qrcode/generate", summary="生成登录二维码")
async def qrcode_generate(req: QrcodeGenerateRequest):
    """生成平台登录二维码"""
    manager = get_qrcode_manager()

    # 检查平台是否支持
    supported = get_supported_qrcode_platforms()
    if req.platform not in supported:
        return QrcodeGenerateResponse(
            success=False,
            message=f"平台 {req.platform} 暂不支持二维码登录，支持: {', '.join(supported) if supported else '暂无'}",
        )

    try:
        session_id = await manager.generate_qrcode(
            platform=req.platform,
            connector_name=req.connector_name,
        )

        session = manager.get_session(session_id)
        if not session or session.status == AcquisitionStatus.FAILED:
            error_msg = session.error_message if session else "生成失败"
            return QrcodeGenerateResponse(
                success=False,
                message=error_msg,
            )

        return QrcodeGenerateResponse(
            success=True,
            session_id=session_id,
            qr_image_base64=session.qr_image_base64 or "",
            expires_in=120,
            message="请使用手机 App 扫描二维码",
        )
    except Exception as e:
        logger.error(f"[CookieAcquisitionAPI] qrcode_generate failed: {e}")
        return QrcodeGenerateResponse(
            success=False,
            message=str(e),
        )


@router.get("/qrcode/{session_id}/status", summary="轮询扫码状态")
async def qrcode_status(session_id: str):
    """轮询二维码扫码状态（备选方案，推荐使用 WebSocket）"""
    manager = get_qrcode_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    return SessionStatusResponse(
        session_id=session_id,
        platform=session.platform,
        method=session.method,
        status=session.status.value,
        message=get_status_message(session.status),
        error_message=session.error_message,
        connector_id=session.connector_id,
    )


@router.post("/qrcode/{session_id}/refresh", summary="刷新过期二维码")
async def qrcode_refresh(session_id: str):
    """刷新过期的二维码"""
    manager = get_qrcode_manager()
    ok = await manager.refresh_qrcode(session_id)
    if ok:
        session = manager.get_session(session_id)
        return {
            "success": True,
            "session_id": session_id,
            "qr_image_base64": session.qr_image_base64 if session else "",
            "message": "二维码已刷新",
        }
    return {"success": False, "message": "刷新失败"}


@router.websocket("/qrcode/{session_id}/ws")
async def qrcode_ws(websocket: WebSocket, session_id: str):
    """QrCode 扫码状态 WebSocket 推送"""
    await websocket.accept()

    manager = get_qrcode_manager()
    session = manager.get_session(session_id)
    if not session:
        await websocket.send_json({
            "type": "error",
            "message": "会话不存在",
        })
        await websocket.close()
        return

    try:
        last_status = None
        while not session.is_terminal:
            if session.status != last_status:
                await websocket.send_json({
                    "type": "status_update",
                    "session_id": session_id,
                    "status": session.status.value,
                    "message": get_status_message(session.status),
                    "data": {
                        "qr_image_base64": session.qr_image_base64,
                    }
                })
                last_status = session.status

            await asyncio.sleep(0.5)

        # 发送终态
        await websocket.send_json({
            "type": "completed",
            "session_id": session_id,
            "status": session.status.value,
            "connector_id": session.connector_id,
            "message": get_status_message(session.status),
            "error_message": session.error_message,
        })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"[CookieAcquisitionAPI] qrcode_ws error: {e}")
