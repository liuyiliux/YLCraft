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

import asyncio
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
        # ⚠️ profile 被残留 chrome 占用时，启动会抛 TargetClosedError
        # （消息里带 `--user-data-dir=<该 profile>`）。
        #
        # 实测踩过（2026-09-28）：后端被 kill 时浏览器子进程没跟着退，
        # 残留 9 个 chrome 占着 profile，之后**所有**该平台的搜索都失败
        # （报 TargetClosedError），表现为"突然搜不到了"，
        # 但重启后端也没用 —— 因为占用的进程还在。
        #
        # 所以这里：识别到占用 → 只杀**指向本 profile 的** chrome →
        # 重试一次。绝不动用户自己的浏览器窗口（按命令行精确匹配）。
        if _is_profile_locked(exc, directory):
            killed = _kill_profile_holders(directory)
            logger.warning(
                "[persistent] profile %s 被占用（清理了 %d 个残留进程），重试一次",
                directory, killed,
            )
            if killed:
                await asyncio.sleep(2)
                try:
                    return await playwright.chromium.launch_persistent_context(**options)
                except Exception as retry_exc:
                    logger.error(
                        "[persistent] 清理后仍启动失败：%s: %s",
                        type(retry_exc).__name__, retry_exc,
                    )
                    raise
        logger.warning(
            "[persistent] 启动失败（%s: %s），回退到非持久化",
            type(exc).__name__,
            exc,
        )
        raise


def _is_profile_locked(exc: Exception, directory: Path) -> bool:
    """判断异常是否因为该 profile 被别的进程占用。"""
    text = str(exc)
    if "Target page, context or browser has been closed" in text:
        # TargetClosedError 也可能来自其它原因，但配合 user-data-dir
        # 出现时基本就是占用（实测如此）
        return str(directory) in text or "launch_persistent_context" in text
    # Chrome 自己的锁提示
    for marker in ("SingletonLock", "ProcessSingleton",
                   "user data directory is already in use",
                   "cannot create default profile directory"):
        if marker.lower() in text.lower():
            return True
    return False


def _kill_profile_holders(directory: Path) -> int:
    """杀掉命令行里指向**该 profile 目录**的 chrome 进程。

    只匹配 `--user-data-dir=<本目录>`，**不会**动用户自己开的浏览器
    （那些命令行里没有 YLCraft 的 profile 路径）。
    """
    if os.name != "nt":
        return 0
    target = str(directory).replace("/", "\\").lower()
    killed = 0
    try:
        import subprocess

        # WMIC 已在新版 Windows 移除，用 PowerShell 的 CIM 更稳
        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name = 'chrome.exe'\" | "
            "Where-Object { $_.CommandLine -and "
            f"$_.CommandLine.ToLower().Contains('{target}') }} | "
            "ForEach-Object { $_.ProcessId }"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=30,
        )
        for line in (out.stdout or "").splitlines():
            line = line.strip()
            if line.isdigit():
                subprocess.run(
                    ["taskkill", "/PID", line, "/F", "/T"],
                    capture_output=True, timeout=15,
                )
                killed += 1
    except Exception as exc:  # 清理失败不能影响主流程
        logger.warning("[persistent] 清理残留进程失败：%s", exc)
    return killed
