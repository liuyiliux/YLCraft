"""
YLCraft — 小红书平台适配器

登录检测 + 账号信息提取
"""

from __future__ import annotations

from app.services.cookie_acquisition.base import PlatformDetector


class XhsDetector(PlatformDetector):
    """小红书登录检测"""

    async def detect(self, page) -> bool:
        """检测用户是否已登录小红书"""
        # 方式1：URL 检测
        if "/explore" in page.url or "/user/profile" in page.url:
            return True
        # 方式2：元素检测 - 查找用户头像/用户信息
        try:
            # 小红书登录后顶部会显示用户头像
            avatar = await page.query_selector(".user-info .avatar")
            if avatar:
                return True
            # 新版 UI
            avatar2 = await page.query_selector('[class*="user"] img')
            if avatar2:
                return True
        except Exception:
            pass
        return False

    async def extract_account_info(self, page) -> dict:
        """提取小红书账号信息"""
        info = {
            "account_id": None,
            "account_name": None,
            "account_avatar": None,
            "account_url": None,
        }
        try:
            # 尝试从页面获取用户名
            name_el = await page.query_selector('[class*="nickname"], [class*="username"]')
            if name_el:
                info["account_name"] = await name_el.inner_text()
        except Exception:
            pass
        return info
