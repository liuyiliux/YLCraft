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

    # ⚠️ 2026-09-26 实测：**不能**用 profile/self 判断登录态。
    # 抖音对自动化会风控该接口，返回
    #   {"status_code":0,"status_msg":"blocked","user":null}
    # status_code 是 0 但 user 为 null；直接照 status_code!=0 判断会误报。
    # 改用浏览器打开页面看 DOM（与 DouyinDetector 保持一致）。
    try:
        from app.services.browser.patchright_runtime import get_patchright_runtime
        from app.services.platforms.login_health import netscape_to_header

        # 存的是 Netscape 格式，浏览器要的是 `k=v; k2=v2`。
        # 实测直接喂原文会报 `Invalid cookie fields`（add_cookies 解析失败）。
        cookie_header = netscape_to_header(cookie, "douyin")

        runtime = get_patchright_runtime()
        try:
            result = await runtime.fetch_page(
                "https://www.douyin.com/",
                headers={"Cookie": cookie_header},
                timeout_ms=60000,
                wait_until="domcontentloaded",
                headless=False,  # 无头会触发验证码页（实测），必须用有头
                settle_ms=6000,
            )
        finally:
            await runtime.close()

        html = result.html or ""
        title = ""
        import re

        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        if m:
            title = m.group(1).strip()

        captcha = "验证码" in title or "captcha" in title.lower()
        has_avatar = bool(re.search(r'class="[^"]*avatar', html))
        # 页面本身能正常渲染（有推荐流内容）也说明不是被封
        has_feed = ("推荐" in html) or ("精选" in html)

        if captcha:
            checks["login"] = health_item(
                "login", "登录态", False,
                "被抖音拦截到验证码页（自动化检测）。请在 YLCraft 弹出的窗口里手动过验证码后重试。",
                {"title": title},
            )
        else:
            checks["login"] = health_item(
                "login", "登录态", has_avatar,
                f"页面正常（{title or '抖音'}）且出现用户头像" if has_avatar
                else f"页面可访问（{title or '抖音'}）但未检出头像，可能是游客态",
                {"title": title, "has_avatar": has_avatar},
            )
        checks["page"] = health_item(
            "page", "页面可访问性", has_feed or bool(title),
            f"页面标题：{title or '（空）'}", {"title": title},
        )
        # 搜索：抖音对自动化会 blocked 搜索接口，这里只报告能否访问页面，
        # 不假装能搜（避免"体检通过但实际搜不到"）。
        checks["search"] = health_item(
            "search", "搜索", has_avatar and not captcha,
            "可尝试搜索（登录态正常）" if (has_avatar and not captcha)
            else "登录态异常或遇验证码，搜索可能被风控拦截（status_msg=blocked）",
        )
    except Exception as exc:
        msg = str(exc)[:120]
        checks["login"] = health_item("login", "登录态", False, f"探测失败：{msg}")
        checks["search"] = health_item("search", "搜索", False, f"无法确认搜索能力：{msg}")

    ready = all(c["ok"] for c in checks.values())
    return {"success": True, "data": {"platform": "douyin", "checks": checks, "ready": ready}}
