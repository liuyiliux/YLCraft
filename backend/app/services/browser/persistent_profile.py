"""
YLCraft — 持久化浏览器 profile（让"登录一次，长期有效"成立）

## 为什么需要（2026-09-26 实测）

取 Cookie 走的是 `chromium.launch()` —— **非持久化**，每次都是全新空 profile。
后果：用户每取一次 Cookie 都要重新扫码；窗口一关、会话一超时，登录就白做了。
实测中用户扫码后 cookie 里确实出现了 sessionid，但因为窗口被关掉，
下一次启动又是未登录状态，于是"抖音登录一直有问题"。

持久化 profile 后：登录一次写进磁盘，之后任何会话都能直接复用。

## 隔离要求

profile 目录必须**按平台分开**，不能所有平台共用一个：
一是各站 cookie 互不干扰，二是避免把 A 站的登录态带给 B 站。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ylcraft.browser.persistent")

# profile 根目录（backend/data/browser_profiles，已 gitignore）
def profiles_root() -> Path:
    """返回 profile 根目录（不存在则创建）。"""
    backend_dir = Path(__file__).resolve().parent.parent.parent.parent
    root = backend_dir / "data" / "browser_profiles"
    root.mkdir(parents=True, exist_ok=True)
    return root


def profile_dir_for(platform: str) -> Path:
    """按平台返回独立 profile 目录。"""
    safe = "".join(ch for ch in (platform or "default") if ch.isalnum() or ch in "-_")
    path = profiles_root() / (safe or "default")
    path.mkdir(parents=True, exist_ok=True)
    return path


def persistent_enabled() -> bool:
    """是否启用持久化 profile。

    默认开启（这正是修复"每次都要重扫"的关键）。
    需要临时关闭时设 YLCRAFT_BROWSER_PERSISTENT=0。
    """
    return os.getenv("YLCRAFT_BROWSER_PERSISTENT", "1").lower() not in ("0", "false", "no")


async def launch_persistent(
    playwright,
    platform: str,
    *,
    headless: bool = False,
    locale: str = "zh-CN",
    viewport: Optional[dict] = None,
    args: Optional[list] = None,
):
    """启动持久化上下文（profile 落到磁盘，登录态可跨会话复用）。

    Returns:
        BrowserContext（持久化模式下没有独立的 Browser 对象，直接用 context）
    """
    directory = profile_dir_for(platform)
    logger.info("[persistent] 启动持久化 profile platform=%s dir=%s", platform, directory)

    launch_args = list(args or []) + [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]

    options = {
        "user_data_dir": str(directory),
        "headless": headless,
        "locale": locale,
        "args": launch_args,
        "viewport": viewport or {"width": 1440, "height": 900},
        # 减少自动化特征；不设 user_agent，沿用持久 profile 自带的
        "ignore_default_args": ["--enable-automation"],
    }

    try:
        return await playwright.chromium.launch_persistent_context(**options)
    except Exception as exc:
        logger.warning(
            "[persistent] 启动失败（%s: %s），回退到非持久化",
            type(exc).__name__,
            exc,
        )
        raise
