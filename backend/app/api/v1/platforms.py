"""
YLCraft — 平台连接器 API（统一凭证架构）

GET    /api/v1/platforms                           — 列出所有平台连接
GET    /api/v1/platforms/supported                  — 获取支持的平台列表
GET    /api/v1/platforms/{id}                       — 获取单个连接详情
POST   /api/v1/platforms                           — 创建新连接
PUT    /api/v1/platforms/{id}                       — 更新连接
DELETE /api/v1/platforms/{id}                      — 删除连接
POST   /api/v1/platforms/{id}/test                 — 测试连接有效性
POST   /api/v1/platforms/{id}/use                  — 标记为已使用
GET    /api/v1/platforms/{id}/cookie-content       — 获取 Netscape 格式 Cookie
POST   /api/v1/platforms/{id}/cookie-content       — 保存 Netscape 格式 Cookie
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session

from app.db.database import get_session
from app.db.models.platform_connection import (
    PlatformConnectionCreate,
    PlatformConnectionUpdate,
    PlatformConnectionResponse,
    PlatformType,
    AuthType,
    ConnectionStatus,
    AcquisitionMethod,
)
from app.services.platform_connection.service import PlatformConnectionService

logger = logging.getLogger("ylcraft.api.platforms")

router = APIRouter(prefix="", tags=["Platform Connections"])

# =============================================================================
# 支持的平台列表
# =============================================================================

SUPPORTED_PLATFORMS = [
    {"value": "xhs",        "label": "小红书",   "icon": "book",        "color": "#fe2c55",  "auth_types": ["cookie"]},
    {"value": "douyin",     "label": "抖音",     "icon": "video",       "color": "#000000",  "auth_types": ["cookie"]},
    {"value": "kuaishou",   "label": "快手",     "icon": "play-circle", "color": "#ff5000",  "auth_types": ["cookie"]},
    {"value": "bilibili",   "label": "B站",      "icon": "tv",          "color": "#00aeec",  "auth_types": ["cookie"]},
    {"value": "weibo",      "label": "微博",     "icon": "message",     "color": "#ff8200",  "auth_types": ["cookie"]},
    # ⚠️ zhihu 已移除（2026-10-01 用户要求）
    {"value": "wechat_mp",  "label": "微信公众号", "icon": "wechat",     "color": "#07C160",  "auth_types": ["qrcode"]},
    {"value": "fanqie",     "label": "番茄小说",   "icon": "book",       "color": "#ff5a5f",  "auth_types": ["cookie"], "view": True, "publish": True, "credential": "cookie"},
    # YouTube 免登录（yt-dlp 取公开数据），没有"凭证"这回事，
    # 标 `none` 让账号中心不再要求抓 cookie（2026-10-01）
    {"value": "youtube",    "label": "YouTube",   "icon": "youtube",     "color": "#ff0000",  "auth_types": ["none"]},
    # ⚠️ **TikTok 已移除**（2026-10-02 审计发现是**假支持**）
    #
    # 原来这里列了 TikTok，用户能在账号中心看到它、点进去、粘贴 cookie、
    # 保存连接 —— 一切正常。但**后端根本没有 TikTok 采集客户端**
    # （`create_client('tiktok')` 报 Unsupported platform，
    #   `supported_platforms()` 里也没有它；搜索页的平台下拉也没有）。
    #
    # 结果：用户建了连接后**没有任何入口能用它** —— 纯浪费用户时间。
    # 仓库铁律：**假选项比没有更糟**。
    #
    # 以后真要做 TikTok：写 `platforms/tiktok/client.py` +
    # `meta.py` 声明 capabilities，再把这一行加回来。
    # 平台已改名 X（原 Twitter）。label 用现名，**value 保持 `twitter`**
    # —— PlatformType.TWITTER、连接表 platform 字段、既有数据都是
    # `twitter`，改 value 会破坏既有数据。
    {"value": "twitter",    "label": "X",          "icon": "twitter",    "color": "#1da1f2",  "auth_types": ["cookie"]},
    # ⚠️ Telegram 的认证方式**不是 cookie**，是 MTProto 登录
    # （api_id/api_hash + 手机号验证码，可能还有两步验证密码）。
    # 标成 `cookie` 会让账号中心走错流程（去抓浏览器 cookie，永远失败）。
    # 用 `telegram` 认证类型，前端据此跳到专用登录页（2026-10-01）。
    # ⚠️ 但**公开频道不需要登录**（`t.me/s`，含频道内 `?q=` 搜索），
    # 所以这个凭证是"可选"的 —— 只为全局搜索/我的频道/私有频道。
    {"value": "telegram",   "label": "Telegram",  "icon": "send",        "color": "#0088cc",  "auth_types": ["telegram"]},
    {"value": "openai",     "label": "OpenAI",    "icon": "api",         "color": "#10a37f",  "auth_types": ["api_key"]},
    {"value": "anthropic",  "label": "Anthropic", "icon": "api",         "color": "#d4a0e7",  "auth_types": ["api_key"]},
    {"value": "minimax",    "label": "MiniMax",   "icon": "api",         "color": "#00d4ff",  "auth_types": ["api_key"]},
]

AUTH_TYPES = [
    {"value": "cookie",   "label": "Cookie 认证"},
    {"value": "api_key",  "label": "API Key"},
    {"value": "oauth2",   "label": "OAuth2.0"},
    {"value": "password", "label": "账号密码"},
    {"value": "qrcode",   "label": "扫码登录"},
    {"value": "none",     "label": "无需认证"},
    # Telegram MTProto：api_id/api_hash + 手机号验证码（+可选两步验证）
    {"value": "telegram", "label": "Telegram 账号登录"},
]

ACQUISITION_METHODS = [
    {"value": "manual",     "label": "手动粘贴"},
    {"value": "playwright", "label": "浏览器自动化"},
    {"value": "qrcode",    "label": "扫码登录"},
]


# =============================================================================
# 依赖注入
# =============================================================================

def get_platform_service(session: Session = Depends(get_session)) -> PlatformConnectionService:
    return PlatformConnectionService(session)


# =============================================================================
# API 端点
# =============================================================================

@router.get("/supported", summary="获取支持的平台列表")
async def get_supported_platforms():
    """返回所有支持的平台、认证类型、获取方式"""
    # 检查 Playwright 是否可用
    playwright_available = False
    try:
        from app.services.cookies.patchright_manager import get_patchright_manager
        playwright_available = get_patchright_manager().is_available()
    except Exception:
        pass

    return {
        "platforms": SUPPORTED_PLATFORMS,
        "auth_types": AUTH_TYPES,
        "acquisition_methods": ACQUISITION_METHODS,
        "playwright_available": playwright_available,
        "statuses": [
            {"value": "active",  "label": "有效"},
            {"value": "expired", "label": "已过期"},
            {"value": "failed",  "label": "连接失败"},
            {"value": "unknown", "label": "未测试"},
        ],
    }


@router.get("", summary="列出所有平台连接")
async def list_connections(
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """列出所有平台连接（不返回凭证内容）"""
    conns = service.list_all()
    return {
        "success": True,
        "connections": [PlatformConnectionResponse.from_db(c) for c in conns],
        "total": len(conns),
    }


@router.get("/{conn_id}", summary="获取连接详情")
async def get_connection(
    conn_id: str,
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """获取单个连接详情（不返回凭证内容）"""
    conn = service.get(conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")
    return {
        "success": True,
        "connection": PlatformConnectionResponse.from_db(conn),
    }


@router.post("", summary="创建平台连接")
async def create_connection(
    data: PlatformConnectionCreate,
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """创建新的平台连接"""
    try:
        conn = service.create(data)
        return {
            "success": True,
            "connection": PlatformConnectionResponse.from_db(conn),
            "message": f"平台连接 {conn.name} 创建成功",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.put("/{conn_id}", summary="更新平台连接")
async def update_connection(
    conn_id: str,
    data: PlatformConnectionUpdate,
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """更新平台连接"""
    conn = service.update(conn_id, data)
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")
    return {
        "success": True,
        "connection": PlatformConnectionResponse.from_db(conn),
        "message": "更新成功",
    }


@router.delete("/{conn_id}", summary="删除平台连接")
async def delete_connection(
    conn_id: str,
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """删除平台连接"""
    ok = service.delete(conn_id)
    if not ok:
        raise HTTPException(status_code=404, detail="连接不存在")
    return {
        "success": True,
        "message": "删除成功",
    }


@router.post("/{conn_id}/disable", summary="停用连接（风控冷却等）")
async def disable_connection(
    conn_id: str,
    reason: str = Query("", description="停用原因（留档，如「小红书被风控」）"),
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """**用户主动停用**一个连接。

    ## 与"删除"的区别

      · 删除 → 凭证没了，恢复要重新登录
      · 停用 → **凭证保留**，随时能启用回来

    典型场景：**平台风控期**（如小红书 461）想停一阵，避免
    反复触发（重试会升级为更长的封禁）。

    ## 停用后会发生什么

      · `resolve_connection` **不再返回**这条连接的凭证
        —— 包括"conn_id 失效回退到最新连接"那条兜底路径也会跳过它
      · 体检/搜索会提示"该连接已停用"，而不是默默继续用

    ⚠️ 这与 `status=expired/failed` **语义不同**：
    那两个是**系统判定**凭证坏了，这个是**用户主动关**。
    所以停用的连接**不该**被当成"需要重新登录"去提示用户。
    """
    conn = service.get(conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")

    from app.db.models.platform_connection import (
        ConnectionStatus,
        PlatformConnectionUpdate,
    )

    service.update(conn_id, PlatformConnectionUpdate(status=ConnectionStatus.DISABLED))
    if reason:
        # ⚠️ 停用原因记在 `description`（备注），不是 `error_message` ——
        # `PlatformConnectionUpdate` **没有** error_message 字段，
        # 而且语义上也不该混：error_message 是"系统报的错误"，
        # 停用原因是"**用户自己写的备注**"。
        prev = (conn.description or "").strip()
        service.update(
            conn_id,
            PlatformConnectionUpdate(
                description=f"{prev}\n[停用] {reason}".strip() if prev else f"[停用] {reason}"
            ),
        )
    logger.info("[platforms] 连接 %s 已停用（原因：%s）", conn_id, reason or "-")
    return {
        "success": True,
        "message": "已停用 —— 搜索/体检会跳过该连接，凭证仍保留",
        "conn_id": conn_id,
        "status": ConnectionStatus.DISABLED.value,
    }


@router.post("/{conn_id}/enable", summary="启用连接（恢复使用）")
async def enable_connection(
    conn_id: str,
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """**重新启用**一个被停用的连接。

    停用只是"不参与搜索"，凭证一直保留 ——
    所以恢复**不需要重新登录**（除非凭证本身也过期了，
    那种情况体检会告诉你要重新登录）。
    """
    conn = service.get(conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")

    from app.db.models.platform_connection import (
        ConnectionStatus,
        PlatformConnectionUpdate,
    )

    # 恢复成 `unknown` 而不是 `active`：
    # 我们**没有验证**过它现在是否有效，不能替用户断言"有效"
    # （那是体检的职责）。用 unknown 表示"待验证"。
    service.update(conn_id, PlatformConnectionUpdate(status=ConnectionStatus.UNKNOWN))
    logger.info("[platforms] 连接 %s 已启用", conn_id)
    return {
        "success": True,
        "message": "已启用 —— 建议跑一次「体检」确认登录态是否仍然有效",
        "conn_id": conn_id,
        "status": ConnectionStatus.UNKNOWN.value,
    }


@router.post("/{conn_id}/test", summary="测试连接有效性")
async def test_connection(
    conn_id: str,
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """测试连接是否有效"""
    result = await service.test_connection(conn_id)
    return {
        "success": result["success"],
        "message": result["message"],
        "connection_id": conn_id,
    }


@router.post("/{conn_id}/use", summary="标记为已使用")
async def mark_used(
    conn_id: str,
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """标记连接已使用（更新 last_used）"""
    service.mark_used(conn_id)
    return {
        "success": True,
        "message": "已更新使用时间",
    }


# =============================================================================
# Cookie Content 端点
# =============================================================================

class CookieContentResponse(BaseModel):
    """Cookie 内容响应"""
    connection_id: str
    platform: str
    content: str = ""
    configured: bool = False
    size: int = 0


class CookieContentSaveRequest(BaseModel):
    """Cookie 内容保存请求"""
    content: str


class PlatformPublishRequest(BaseModel):
    """A platform-neutral envelope with an explicit platform target."""

    title: str
    body: str = ""
    content_type: str = "article"
    target: dict[str, str] = {}
    dry_run: bool = False


@router.post("/{conn_id}/publish", summary="通过指定平台连接发布内容")
async def publish_content(
    conn_id: str,
    req: PlatformPublishRequest,
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """Publish through a configured connection.

    Fanqie is chapter based, so an article must name the remote book, volume,
    and already-created chapter item. ``dry_run`` validates that contract
    without sending a remote write request.
    """
    conn = service.get(conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="平台连接不存在")
    platform = conn.platform.value if hasattr(conn.platform, "value") else str(conn.platform)
    if platform != PlatformType.FANQIE.value:
        raise HTTPException(status_code=422, detail=f"通用发布暂不支持平台: {platform}")
    if req.content_type != "article":
        raise HTTPException(status_code=422, detail="番茄仅支持 article 类型章节正文")
    if not conn.cookie_content:
        raise HTTPException(status_code=400, detail="番茄连接未配置 cookie")
    if not req.title.strip() or not req.body.strip():
        raise HTTPException(status_code=400, detail="标题和正文不能为空")

    target = req.target or {}
    missing = [key for key in ("book_id", "volume_id", "item_id") if not str(target.get(key, "")).strip()]
    if missing:
        raise HTTPException(status_code=400, detail=f"番茄发布缺少目标参数: {', '.join(missing)}")
    if req.dry_run:
        return {
            "success": True,
            "dry_run": True,
            "platform": platform,
            "target": {key: target.get(key, "") for key in ("book_id", "volume_id", "volume_name", "item_id")},
        }

    from app.services.platforms.fanqie.client import FanqieClient
    from app.services.platforms.fanqie.utils import FanqieError, markdown_to_fanqie_html
    from app.services.platforms.types import ClientConfig, ClientMode

    try:
        async with FanqieClient(ClientConfig(platform="fanqie", mode=ClientMode.API, cookie=conn.cookie_content)) as client:
            result = await client.save_draft(
                book_id=target["book_id"],
                volume_id=target["volume_id"],
                volume_name=target.get("volume_name", ""),
                item_id=target["item_id"],
                title=req.title.strip(),
                content_html=markdown_to_fanqie_html(req.body),
            )
    except FanqieError as exc:
        raise HTTPException(status_code=502, detail=f"番茄发布失败: {exc}") from exc

    service.mark_used(conn_id)
    return {"success": True, "platform": platform, "data": result}


@router.get("/{conn_id}/cookie-content", summary="获取 Netscape 格式 Cookie")
async def get_cookie_content(
    conn_id: str,
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """获取连接的 Netscape 格式 Cookie 内容（视频解析用）"""
    conn = service.get(conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")

    cookie_content = service.get_cookie_content(conn_id)
    if cookie_content:
        return CookieContentResponse(
            connection_id=conn_id,
            platform=conn.platform.value if hasattr(conn.platform, 'value') else str(conn.platform),
            content=cookie_content,
            configured=True,
            size=len(cookie_content),
        )
    return CookieContentResponse(
        connection_id=conn_id,
        platform=conn.platform.value if hasattr(conn.platform, 'value') else str(conn.platform),
        configured=False,
    )


@router.post("/{conn_id}/cookie-content", summary="保存 Netscape 格式 Cookie")
async def save_cookie_content(
    conn_id: str,
    req: CookieContentSaveRequest,
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """保存 Netscape 格式 Cookie 到连接（替代原 /cookies/{platform}）"""
    if not req.content or len(req.content.strip()) < 10:
        raise HTTPException(status_code=400, detail="Cookie 内容太短，请检查是否正确")

    # 使用 CookieManager 的公共方法进行格式转换
    try:
        from app.services.video.parser import get_cookie_manager
        mgr = get_cookie_manager()
        conn = service.get(conn_id)
        if not conn:
            raise HTTPException(status_code=404, detail="连接不存在")

        platform = conn.platform.value if hasattr(conn.platform, 'value') else str(conn.platform)
        # 使用公共方法 normalize_cookie 转换为 Netscape 格式
        netscape_content = mgr.normalize_cookie(platform, req.content)
        
        ok = service.save_cookie_content(conn_id, netscape_content)
        if ok:
            return {
                "success": True,
                "message": "Cookie 已保存",
                "connection_id": conn_id,
            }
        raise HTTPException(status_code=500, detail="保存失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PlatformsAPI] save_cookie_content failed: {e}")
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


# =============================================================================
# 辅助函数（供其他模块调用）
# =============================================================================

def get_active_connection(session: Session, platform: str) -> Optional[dict]:
    """
    获取指定平台的活跃连接凭证
    供搜索/下载/发布等功能调用
    """
    service = PlatformConnectionService(session)
    conn = service.get_active(platform)
    if not conn:
        return None
    return {
        "id": conn.id,
        "platform": conn.platform,
        "name": conn.name,
        "auth_type": conn.auth_type,
        "credentials": conn.get_credentials(),
        "cookie_content": conn.cookie_content,
        "status": conn.status,
    }
