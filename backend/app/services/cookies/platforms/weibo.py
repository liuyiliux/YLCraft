"""
YLCraft — 微博平台适配器

登录检测 + 账号信息提取
"""

from __future__ import annotations

from app.services.cookies.base import PlatformDetector


class WeiboDetector(PlatformDetector):
    """微博登录检测"""

    async def detect(self, page) -> bool:
        """检测用户是否已登录微博"""
        try:
            # 微博登录后顶部出现用户头像
            avatar = await page.query_selector('[class*="avatar"], [class*="userpic"] img')
            if avatar:
                return True
            # 检测用户名
            user_el = await page.query_selector('[class*="username"], [class*="nick"]')
            if user_el:
                return True
        except Exception:
            pass
        return False

    async def extract_account_info(self, page) -> dict:
        """提取微博账号信息"""
        info = {
            "account_id": None,
            "account_name": None,
            "account_avatar": None,
            "account_url": None,
        }
        try:
            name_el = await page.query_selector('[class*="username"], [class*="nick"]')
            if name_el:
                info["account_name"] = await name_el.inner_text()
        except Exception:
            pass
        return info
