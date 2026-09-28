"""YLCraft — X（原 Twitter）平台适配器。

登录检测 + 账号信息提取。

## 检测依据（实测 2026-09-28）

**不能用 `document.cookie` 判断登录态** —— `auth_token` 是 httpOnly，
`document.cookie` 看不到它。据此判断会得出"未登录"的**错误结论**
（实测踩过这个误判）。

可靠判据是**只有登录后才出现的界面元素**（实测在已登录的 x.com 上确认）：

    [data-testid="SideNav_NewTweet_Button"]          左侧「发帖」按钮
    [data-testid="SideNav_AccountSwitcher_Button"]   左下「账号菜单」

未登录时这两个都不存在，且 `[data-testid="loginButton"]` 会出现
（页面还会被重定向到 /i/jf/onboarding/web）。

## 命名说明

平台现在叫 **X**（原 Twitter）。显示名统一用 `X`，
但**标识符保留 `twitter`**（`PlatformType.TWITTER`、连接表 platform 字段、
已有数据都是 `twitter`），避免破坏既有数据。同时注册 `x` / `tw` 别名。
"""

from __future__ import annotations

from app.services.cookies.base import PlatformDetector


class XDetector(PlatformDetector):
    """X（原 Twitter）登录检测。"""

    # 只有登录后才出现的元素
    _LOGGED_IN_SELECTORS = (
        '[data-testid="SideNav_NewTweet_Button"]',
        '[data-testid="SideNav_AccountSwitcher_Button"]',
    )
    # 未登录时的标志
    _LOGGED_OUT_SELECTORS = (
        '[data-testid="loginButton"]',
        '[data-testid="signupButton"]',
    )

    async def detect(self, page) -> bool:
        """检测是否已登录 X。

        ⚠️ 判据是**界面元素**，不是 cookie（见模块 docstring）。
        """
        try:
            for sel in self._LOGGED_IN_SELECTORS:
                if await page.query_selector(sel):
                    return True
            # 明确看到登录/注册按钮 → 肯定没登录
            for sel in self._LOGGED_OUT_SELECTORS:
                if await page.query_selector(sel):
                    return False
        except Exception:
            pass
        return False

    async def extract_account_info(self, page) -> dict:
        """提取 X 账号信息。

        账号菜单按钮的 `aria-label` 形如 `账号菜单`，
        handle 在 `/用户名` 链接里。取不到就留 None（**不编造**）。
        """
        info = {
            "account_id": None,
            "account_name": None,
            "account_avatar": None,
            "account_url": None,
        }
        try:
            # 头像：账号菜单按钮里的 img
            avatar = await page.query_selector(
                '[data-testid="SideNav_AccountSwitcher_Button"] img'
            )
            if avatar:
                info["account_avatar"] = await avatar.get_attribute("src")

            # 用户名：账号菜单里的 User-Name（含 @handle）
            name_el = await page.query_selector(
                '[data-testid="SideNav_AccountSwitcher_Button"] '
                '[data-testid="User-Name"]'
            )
            if name_el:
                text = (await name_el.inner_text()) or ""
                lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                if lines:
                    info["account_name"] = lines[0]
                handle = next((ln for ln in lines if ln.startswith("@")), "")
                if handle:
                    info["account_url"] = f"https://x.com/{handle.lstrip('@')}"
                    info["account_id"] = handle.lstrip("@")
        except Exception:
            pass
        return info
