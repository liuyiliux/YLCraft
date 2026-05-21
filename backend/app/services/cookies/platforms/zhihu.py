"""
YLCraft — 知乎平台适配器

登录检测 + 账号信息提取
"""

from __future__ import annotations

from app.services.cookies.base import PlatformDetector


class ZhihuDetector(PlatformDetector):
    """知乎登录检测"""

    async def detect(self, page) -> bool:
        """检测用户是否已登录知乎"""
        try:
            # 知乎登录后顶部出现用户头像
            avatar = await page.query_selector(".AppHeader-userAvatar, [class*='Avatar'] img")
            if avatar:
                return True
            # 检测用户菜单
            user_el = await page.query_selector('[class*="AppHeader-userInfo"], [class*="SignContainer"]')
            # 如果 SignContainer 不在了，说明已登录
            sign = await page.query_selector('[class*="SignContainer"]')
            if not sign:
                # 检查是否有用户头像来确认
                header_avatar = await page.query_selector('.AppHeader-userAvatar')
                if header_avatar:
                    return True
        except Exception:
            pass
        return False

    async def extract_account_info(self, page) -> dict:
        """提取知乎账号信息"""
        info = {
            "account_id": None,
            "account_name": None,
            "account_avatar": None,
            "account_url": None,
        }
        try:
            name_el = await page.query_selector('[class*="AppHeader-profileName"], [class*="username"]')
            if name_el:
                info["account_name"] = await name_el.inner_text()
        except Exception:
            pass
        return info
