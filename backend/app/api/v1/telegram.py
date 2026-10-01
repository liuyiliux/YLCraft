"""YLCraft — Telegram 专用路由（登录 + 频道能力）。

## 为什么单独一个路由文件

Telegram 的登录是**多步状态机**（api_id/api_hash → 手机号 → 验证码 →
可选两步验证密码），与其它平台的"抓一次 cookie"完全不同。
塞进 `platforms.py` 的通用连接流程会把那套逻辑搞乱。

## 路由一览

    GET  /telegram/status          登录状态（含"凭证是否已配置"）
    POST /telegram/auth/send-code  发验证码（第一步）
    POST /telegram/auth/sign-in    提交验证码 / 两步验证密码（第二步）
    POST /telegram/auth/logout     退出登录（删会话）
    GET  /telegram/channels        我加入的频道（需登录）
    GET  /telegram/channel         某频道的公开信息 + 消息（免登录）

⚠️ **绝不返回 api_hash / session 内容给前端** —— 只返回"有没有配"。
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger("ylcraft.api.telegram")

router = APIRouter(prefix="/telegram", tags=["Telegram"])


# =============================================================================
# 请求 / 响应模型
# =============================================================================

class SendCodeRequest(BaseModel):
    api_id: str = Field(..., description="my.telegram.org 申请的 App api_id（数字）")
    api_hash: str = Field(..., description="my.telegram.org 申请的 App api_hash")
    phone: str = Field(..., description="手机号，国际格式，如 +8613800138000")


class SignInRequest(BaseModel):
    code: str = Field(..., description="Telegram 发到 App 里的验证码")
    password: str = Field("", description="两步验证密码（账号开启时才需要）")


class TelegramStatus(BaseModel):
    has_credentials: bool = False
    has_session: bool = False
    logged_in: bool = False
    username: str = ""
    display_name: str = ""
    user_id: int = 0
    api_id: str = ""
    needs_password: bool = False
    error: str = ""


# =============================================================================
# 状态
# =============================================================================

@router.get("/status", response_model=TelegramStatus, summary="Telegram 登录状态")
async def telegram_status():
    """查询 Telegram 登录状态。

    ⚠️ **未登录是正常状态**（公开频道不需要登录），
    所以这里永远返回 200，用 `logged_in` 字段表达。
    """
    from app.services.platforms.telegram import mtproto

    try:
        st = await mtproto.get_status()
        return TelegramStatus(**{k: v for k, v in st.items() if k in TelegramStatus.model_fields})
    except Exception as exc:
        logger.warning("[telegram] 查询状态失败：%s", exc)
        return TelegramStatus(error=f"{type(exc).__name__}: {str(exc)[:150]}")


# =============================================================================
# 登录流程
# =============================================================================

@router.post("/auth/send-code", summary="发送 Telegram 验证码")
async def send_code(req: SendCodeRequest):
    """第一步：用 api_id/api_hash + 手机号请求验证码。

    验证码会发到**你已登录的 Telegram 客户端**（App/桌面端），
    不是短信（除非你没装 App）。
    """
    from app.services.platforms.telegram import mtproto

    try:
        return await mtproto.send_code(req.api_id.strip(), req.api_hash.strip(), req.phone.strip())
    except RuntimeError as exc:
        # 可读的业务错误 → 400（不是 500）
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("[telegram] send-code 异常：%s", exc)
        raise HTTPException(status_code=500, detail=f"发送验证码失败: {str(exc)[:200]}")


@router.post("/auth/sign-in", summary="提交验证码完成登录")
async def sign_in(req: SignInRequest):
    """第二步：提交验证码；账号开了两步验证时再提交一次密码。"""
    from app.services.platforms.telegram import mtproto

    try:
        return await mtproto.sign_in(req.code.strip(), req.password or "")
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("[telegram] sign-in 异常：%s", exc)
        raise HTTPException(status_code=500, detail=f"登录失败: {str(exc)[:200]}")


@router.post("/auth/logout", summary="退出 Telegram 登录")
async def logout():
    """退出登录（通知服务端 + 删除本地会话文件）。"""
    from app.services.platforms.telegram import mtproto

    try:
        return await mtproto.logout()
    except Exception as exc:
        logger.error("[telegram] logout 异常：%s", exc)
        raise HTTPException(status_code=500, detail=f"退出失败: {str(exc)[:200]}")


# =============================================================================
# 频道能力
# =============================================================================

@router.get("/channels", summary="我加入的频道（需登录）")
async def my_channels(limit: int = Query(100, ge=1, le=500)):
    """列出当前登录账号加入的**频道/群组**（跳过私聊）。

    ⚠️ 需要登录 —— 未登录时返回 **401**（不是空列表），
    因为"没登录"和"没加入任何频道"是两回事。
    """
    from app.services.platforms.telegram.mtproto import get_authorized_client
    from app.services.platforms.telegram.mtproto_data import list_dialogs

    client = None
    try:
        client = await get_authorized_client()
        chans = await list_dialogs(client, limit=limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except Exception as exc:
        logger.error("[telegram] channels 异常：%s", exc)
        raise HTTPException(status_code=500, detail=f"获取频道列表失败: {str(exc)[:200]}")
    finally:
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass

    return {
        "success": True,
        "total": len(chans),
        "channels": [
            {
                "id": c.id,
                "username": c.username,
                "title": c.title,
                "subscribers": c.subscribers,
                "is_channel": c.raw_data.get("is_channel", False),
                "is_group": c.raw_data.get("is_group", False),
                "url": f"https://t.me/{c.username}" if c.username else "",
            }
            for c in chans
        ],
    }


@router.get("/channel", summary="公开频道信息 + 消息（免登录）")
async def public_channel(
    channel: str = Query(..., description="频道 username 或链接，如 durov"),
    limit: int = Query(20, ge=1, le=100),
    keyword: str = Query("", description="频道内关键词（可空）"),
):
    """抓公开频道（`t.me/s`，**免登录**）。

    ⚠️ 这是 A 方案 —— 私有频道拿不到，请用 `/channels`（需登录）。
    """
    from app.services.platforms.telegram.web_preview import (
        TelegramPublicClient,
        TelegramPublicError,
    )

    c = TelegramPublicClient()
    try:
        info, msgs = await c.get_channel(channel, limit=limit, query=keyword)
    except TelegramPublicError as exc:
        # 频道不存在/私有/结构变化 —— 都是**可操作**的业务错误
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "success": True,
        "channel": {
            "title": info.title,
            "username": info.username,
            "subscribers": info.subscribers,
            "description": info.description,
            "avatar": info.avatar,
        },
        "total": len(msgs),
        "messages": [
            {
                "id": m.id,
                "channel": m.channel,
                "text": m.text,
                "html": m.html,
                "date": m.date,
                "views": m.views,
                "images": m.images,
                "video": m.video,
                "video_cover": m.video_cover,
                "duration": m.duration,
                "forward_from": m.forward_from,
                "type": m.content_type,
                "url": m.page_url(),
            }
            for m in msgs
        ],
    }
