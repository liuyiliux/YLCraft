"""
YLCraft — B站平台适配器

登录检测 + 账号信息提取
"""

from __future__ import annotations

from app.services.cookie_acquisition.base import PlatformDetector


class BilibiliDetector(PlatformDetector):
    """B站登录检测"""

    async def detect(self, page) -> bool:
        """检测用户是否已登录B站"""
        try:
            # B站登录后右上角出现用户头像
            avatar = await page.query_selector(".header-avatar-wrap, .bili-avatar")
            if avatar:
                return True
            # 检测用户名
            user_el = await page.query_selector(".header-user-name, .user-con")
            if user_el:
                return True
        except Exception:
            pass
        return False

    async def extract_account_info(self, page) -> dict:
        """提取B站账号信息"""
        info = {
            "account_id": None,
            "account_name": None,
            "account_avatar": None,
            "account_url": None,
        }
        try:
            name_el = await page.query_selector(".header-user-name, .user-con .name")
            if name_el:
                info["account_name"] = await name_el.inner_text()
        except Exception:
            pass
        return info
