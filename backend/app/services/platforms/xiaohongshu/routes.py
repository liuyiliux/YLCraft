"""
YLCraft — 小红书平台路由

搜索必须走浏览器（端点迁移到 so.xiaohongshu.com/v2 且需要 X-s/X-t 签名，
签名函数是混淆 JS、跨域调用 406），所以这里只提供登录态体检，
对齐 B站 `/api/v1/bilibili/login-health`。
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Query

from app.services.platforms.login_health import (
    cookie_names,
    get_raw_cookie,
    health_item,
    netscape_to_header,
)

logger = logging.getLogger("ylcraft.platforms.xiaohongshu.health")

router = APIRouter()

EXPLORE_URL = "https://www.xiaohongshu.com/explore"


@router.get("/login-health", summary="小红书登录态体检")
async def xhs_login_health(conn_id: str = Query("", description="平台连接 ID")):
    """检查小红书连接保存的 Cookie 是否仍然可用。

    实测判据：未登录时访问 /explore 一定会被重定向到 /login；
    已登录则停在 /explore 并渲染出用户头像。
    """
    checks: Dict[str, Dict[str, Any]] = {}
    cookie = get_raw_cookie(conn_id) if conn_id else ""
    names = cookie_names(cookie)

    checks["cookie"] = health_item(
        "cookie", "Cookie", bool(cookie),
        f"已获取 Cookie（{len(names)} 项，长度 {len(cookie)}）" if cookie
        else "没有 Cookie，请先保存小红书连接",
        {"count": len(names), "length": len(cookie)},
    )

    has_session = "web_session" in names
    checks["web_session"] = health_item(
        "web_session", "登录票据", has_session,
        "Cookie 含 web_session" if has_session else "Cookie 缺少 web_session，无法登录",
    )

    # 实测教训：游客态也有 web_session，但很短且没有 id_token。
    # 曾因此把游客 cookie 存成连接，界面显示正常、搜索却一直失败。
    has_id_token = "id_token" in names
    checks["id_token"] = health_item(
        "id_token", "身份令牌", has_id_token,
        "Cookie 含 id_token" if has_id_token
        else "Cookie 缺少 id_token —— 很可能是**游客态**，请重新获取小红书 Cookie",
    )

    if not cookie:
        checks["login"] = health_item("login", "登录态", False, "没有 Cookie，无法确认登录态")
        checks["search"] = health_item("search", "搜索", False, "没有 Cookie，无法确认搜索能力")
        return {"success": True, "data": {"platform": "xhs", "checks": checks, "ready": False}}

    header = netscape_to_header(cookie, "xiaohongshu")
    try:
        from app.services.browser.patchright_runtime import get_patchright_runtime

        runtime = get_patchright_runtime()
        try:
            result = await runtime.fetch_page(
                EXPLORE_URL,
                headers={"Cookie": header},
                timeout_ms=60000,
                wait_until="domcontentloaded",
                headless=True,
                settle_ms=5000,
            )
        finally:
            await runtime.close()

        final_url = result.url or ""
        # 实测未登录会跳到 /login 或 /website-login/error
        redirected = ("/login" in final_url) or ("-login" in final_url)
        checks["login"] = health_item(
            "login", "登录态", not redirected,
            "已登录（未被重定向到登录页）" if not redirected
            else "被重定向到登录页：Cookie 已失效或是游客态，请重新获取小红书 Cookie",
            {"final_url": final_url[:120]},
        )
        checks["search"] = health_item(
            "search", "搜索", not redirected,
            "搜索可用（浏览器打开搜索页读取结果）" if not redirected
            else "登录态无效，搜索会失败；请重新获取小红书 Cookie",
        )
    except Exception as exc:
        msg = str(exc)[:120]
        checks["login"] = health_item("login", "登录态", False, f"探测失败：{msg}")
        checks["search"] = health_item("search", "搜索", False, f"无法确认搜索能力：{msg}")

    ready = all(c["ok"] for c in checks.values())
    return {"success": True, "data": {"platform": "xhs", "checks": checks, "ready": ready}}
