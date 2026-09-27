"""用户搜索 / 资料 / 作品列表 的 HTTP 路由（抖音 + 小红书共用形状）。

## 为什么两个平台合成一个路由文件

两边能力与返回结构**完全一致**（都是 UserProfile + SearchResult），
前端可以共用同一个面板，只是 platform 参数不同。

## 实测（2026-09-27）

    抖音：搜索「李子柒」→ 5657万粉；资料 → 4830万粉/获赞2.55亿/作品774
    小红书：搜索「美食」→ 吕小厨爱美食 140.9万粉；资料/作品均通

## 为什么不做成"平台各自的路由"

B站已有 `/api/v1/bilibili/up/profile` 与 `/up/videos`（历史原因）。
新平台若也各写一套，前端要为每个平台写一份面板。
这里统一成 `/api/v1/users/*?platform=xxx`，B站保持原样（不破坏既有调用）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.platforms.login_health import (
    netscape_to_header,
    resolve_connection,
)

logger = logging.getLogger("ylcraft.api.users")

router = APIRouter()

# 支持"用户搜索/资料/作品列表"的平台及其连接平台名
#
# 抖音/小红书已实测；B站用既有 /bilibili/up/* 路由，不在这里重复。
SUPPORTED = {
    "douyin": {"conn_platform": "DOUYIN", "cookie_domain": "douyin"},
    "xiaohongshu": {"conn_platform": "XHS", "cookie_domain": "xiaohongshu"},
    # 别名，容忍前端传 xhs
    "xhs": {"conn_platform": "XHS", "cookie_domain": "xiaohongshu"},
}


class UserItem(BaseModel):
    """统一用户结构。"""
    id: str = ""
    name: str = ""
    avatar: str = ""
    platform: str = ""
    followers: int = 0
    following: int = 0
    total_likes: int = 0
    total_videos: int = 0
    desc: str = ""
    verified: bool = False
    # 各平台特有：抖音的 sec_uid（查作品列表要用）、小红书的 xsec_token
    sec_uid: str = ""
    xsec_token: str = ""
    raw_data: Dict[str, Any] = {}


class UserSearchResponse(BaseModel):
    success: bool
    data: List[UserItem] = []
    message: str = ""


class UserProfileResponse(BaseModel):
    success: bool
    data: Optional[UserItem] = None
    message: str = ""


class UserVideoItem(BaseModel):
    id: str = ""
    title: str = ""
    cover: str = ""
    url: str = ""
    type: str = ""
    likes: int = 0


class UserVideosResponse(BaseModel):
    success: bool
    data: List[UserVideoItem] = []
    message: str = ""


def _resolve(platform: str) -> Dict[str, str]:
    cfg = SUPPORTED.get((platform or "").strip().lower())
    if not cfg:
        raise HTTPException(
            status_code=400,
            detail=(
                f"平台 {platform!r} 不支持用户查询。"
                f"当前支持：{', '.join(sorted(SUPPORTED))}。"
                "（B站请用 /api/v1/bilibili/up/* 系列接口）"
            ),
        )
    return cfg


def _to_item(p) -> UserItem:
    raw = p.raw_data or {}
    return UserItem(
        id=p.id,
        name=p.name,
        avatar=p.avatar,
        platform=p.platform,
        followers=p.followers,
        following=p.following,
        total_likes=p.total_likes,
        total_videos=p.total_videos,
        desc=p.desc,
        verified=p.verified,
        # 抖音：查作品列表必须用 sec_uid
        sec_uid=raw.get("sec_uid") or "",
        # 小红书：部分接口需要 xsec_token
        xsec_token=raw.get("xsec_token") or "",
        raw_data=raw,
    )


async def _client_for(platform: str):
    """按连接取 cookie，建平台客户端。"""
    cfg = _resolve(platform)
    _conn_id, raw = resolve_connection("", cfg["conn_platform"])
    if not raw:
        raise HTTPException(
            status_code=400,
            detail=(
                f"没有可用的{platform}连接。请先在「账号中心」获取并保存"
                "该平台的登录态，再使用用户查询。"
            ),
        )
    from app.services.platforms import create_client

    cookie = netscape_to_header(raw, cfg["cookie_domain"])
    # 小红书用户接口需要签名（走 API 模式）；抖音同样走 API
    client = create_client(platform if platform != "xhs" else "xiaohongshu",
                           mode="api", cookie=cookie)
    if client is None:
        raise HTTPException(status_code=500, detail=f"{platform} 客户端未注册")
    return client


@router.get(
    "/search",
    response_model=UserSearchResponse,
    summary="搜索用户（抖音/小红书）",
)
async def search_users(
    platform: str = Query(..., description="平台：douyin / xiaohongshu"),
    keyword: str = Query(..., description="搜索关键词"),
    max_results: int = Query(20, ge=1, le=50),
):
    """按关键词搜用户。

    实测：抖音「李子柒」→ 5657万粉博主；小红书「美食」→ 140.9万粉博主。
    """
    client = await _client_for(platform)
    try:
        async with client:
            users = await client.search_users(keyword, max_results=max_results)
        return UserSearchResponse(
            success=True, data=[_to_item(u) for u in users],
            message=f"找到 {len(users)} 个用户",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[users/search] %s %r 失败: %s", platform, keyword, exc)
        raise HTTPException(status_code=500, detail=f"搜索用户失败: {exc}")


@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="获取自己账号的资料（抖音/小红书）",
)
async def get_self_profile(
    platform: str = Query(..., description="平台：douyin / xiaohongshu"),
):
    """查**当前连接账号自己**的资料（「我的数据」用）。

    与 `/users/profile` 的区别：不需要传 user_id / sec_uid，
    直接用连接里的登录态。

    实测：
        抖音   逸流AI | 粉丝122 关注3 获赞2735 作品22
        小红书 逸流AI | 粉丝195 关注2 获赞2930 作品73
    """
    client = await _client_for(platform)
    if not hasattr(client, "get_self_profile"):
        raise HTTPException(
            status_code=400,
            detail=f"{platform} 不支持查询自己的资料",
        )
    try:
        async with client:
            profile = await client.get_self_profile()
        if profile is None:
            return UserProfileResponse(
                success=False, data=None,
                message="未能获取自己的资料 —— 登录态可能已失效，请重新获取 Cookie",
            )
        return UserProfileResponse(success=True, data=_to_item(profile), message="获取成功")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[users/me] %s 失败: %s", platform, exc)
        raise HTTPException(status_code=500, detail=f"获取我的资料失败: {exc}")


@router.get(
    "/profile",
    response_model=UserProfileResponse,
    summary="获取用户资料（抖音/小红书）",
)
async def get_user_profile(
    platform: str = Query(..., description="平台：douyin / xiaohongshu"),
    user_id: str = Query("", description="用户 ID（小红书用数字 id）"),
    sec_uid: str = Query("", description="抖音专用：sec_uid（**抖音必须用它**）"),
):
    """取用户资料。

    ⚠️ **抖音必须传 `sec_uid`**（不是数字 uid）——实测用数字 uid 得到空页面。
    `sec_uid` 从 `/users/search` 的返回里拿。
    """
    client = await _client_for(platform)
    target = sec_uid if (sec_uid and platform.lower() == "douyin") else user_id
    if not target:
        raise HTTPException(
            status_code=400,
            detail="缺少用户标识：抖音请传 sec_uid，小红书请传 user_id",
        )
    try:
        async with client:
            profile = await client.get_user_profile(target)
        if profile is None:
            return UserProfileResponse(
                success=False, data=None, message="用户不存在或资料不可见"
            )
        return UserProfileResponse(success=True, data=_to_item(profile), message="获取成功")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[users/profile] %s %s 失败: %s", platform, target[:16], exc)
        raise HTTPException(status_code=500, detail=f"获取用户资料失败: {exc}")


@router.get(
    "/videos",
    response_model=UserVideosResponse,
    summary="获取用户作品列表（抖音/小红书）",
)
async def get_user_videos(
    platform: str = Query(..., description="平台：douyin / xiaohongshu"),
    user_id: str = Query("", description="用户 ID（小红书用数字 id）"),
    sec_uid: str = Query("", description="抖音专用：sec_uid（**抖音必须用它**）"),
    max_results: int = Query(20, ge=1, le=50),
):
    """取用户作品列表（含图文与视频，带分页）。"""
    client = await _client_for(platform)
    target = sec_uid if (sec_uid and platform.lower() == "douyin") else user_id
    if not target:
        raise HTTPException(
            status_code=400,
            detail="缺少用户标识：抖音请传 sec_uid，小红书请传 user_id",
        )
    try:
        async with client:
            items = await client.get_user_videos(target, max_results=max_results)
        return UserVideosResponse(
            success=True,
            data=[
                UserVideoItem(
                    id=v.id, title=v.title, cover=v.cover, url=v.url,
                    type=v.type, likes=v.likes,
                )
                for v in items
            ],
            message=f"获取到 {len(items)} 个作品",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[users/videos] %s %s 失败: %s", platform, target[:16], exc)
        raise HTTPException(status_code=500, detail=f"获取作品列表失败: {exc}")
