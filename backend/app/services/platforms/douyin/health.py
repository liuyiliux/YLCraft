"""
YLCraft — 抖音登录态体检

对齐 B站 `/api/v1/bilibili/login-health`：一键检查连接里保存的 Cookie
是否还真的能用，并给出可读原因。

为什么需要（用户实测反馈，2026-09-26）：
  抖音原先只有一个「选择连接」下拉、**没有体检**，用户存完 Cookie
  完全不知道还能不能用。

判据（实测确认）：
  GET /aweme/v1/web/user/profile/self/
    已登录 → {"status_code": 0, "user": {"uid": ..., "nickname": ...}}
    未登录 → {"status_code": 8, "status_msg": "用户未登录", "user": null}
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Query

from app.services.platforms.login_health import (
    cookie_names,
    get_raw_cookie,
    health_item,
)

logger = logging.getLogger("ylcraft.platforms.douyin.health")

router = APIRouter()

# 抖音登录票据名（sessionid 系列是 httpOnly 核心票据）
SESSION_COOKIE_NAMES = ("sessionid", "sessionid_ss", "sid_tt")


@router.get("/login-health", summary="抖音登录态体检")
async def douyin_login_health(conn_id: str = Query("", description="平台连接 ID")):
    """检查抖音连接保存的 Cookie 是否仍然可用。"""
    from app.services.platforms import create_client
    from app.services.platforms.douyin.apis import PROFILE_SELF

    checks: Dict[str, Dict[str, Any]] = {}
    cookie = get_raw_cookie(conn_id) if conn_id else ""
    names = cookie_names(cookie)

    checks["cookie"] = health_item(
        "cookie", "Cookie", bool(cookie),
        f"已获取 Cookie（{len(names)} 项，长度 {len(cookie)}）" if cookie
        else "没有 Cookie，请先保存抖音连接",
        {"count": len(names), "length": len(cookie)},
    )

    has_session = any(n in names for n in SESSION_COOKIE_NAMES)
    checks["sessionid"] = health_item(
        "sessionid", "登录票据", has_session,
        "Cookie 含 sessionid（登录票据）" if has_session
        else "Cookie 缺少 sessionid —— 这通常是**游客态**，搜索会返回 status_code=2483",
    )

    if not cookie:
        checks["login"] = health_item("login", "登录态", False, "没有 Cookie，无法确认登录态")
        checks["search"] = health_item("search", "搜索", False, "没有 Cookie，无法确认搜索能力")
        return {"success": True, "data": {"platform": "douyin", "checks": checks, "ready": False}}

    try:
        client = create_client("douyin", mode="api", cookie=cookie)
        async with client:
            data = await client._call(PROFILE_SELF)
        user = data.get("user") or {}
        uid = user.get("uid")
        is_login = bool(uid)
        checks["login"] = health_item(
            "login", "登录态", is_login,
            f"已识别登录用户：{user.get('nickname') or uid}" if is_login
            else "抖音未识别为已登录（Cookie 可能已失效，请重新获取）",
            {"uid": uid, "nickname": user.get("nickname")},
        )
        checks["search"] = health_item(
            "search", "搜索", is_login,
            "搜索接口可用（/aweme/v1/web/general/search/single/）" if is_login
            else "登录态无效，搜索会失败；请重新获取抖音 Cookie",
        )
    except Exception as exc:
        msg = str(exc)[:120]
        checks["login"] = health_item("login", "登录态", False, f"登录态接口请求失败：{msg}")
        checks["search"] = health_item("search", "搜索", False, f"无法确认搜索能力：{msg}")

    ready = all(c["ok"] for c in checks.values())
    return {"success": True, "data": {"platform": "douyin", "checks": checks, "ready": ready}}
