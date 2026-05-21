"""
YLCraft — 快手平台适配器

登录检测 + 账号信息提取
"""

from __future__ import annotations

from app.services.cookies.base import PlatformDetector


class KuaishouDetector(PlatformDetector):
    """快手登录检测"""

    async def detect(self, page) -> bool:
        """检测用户是否已登录快手"""
        try:
            # 快手登录后出现用户头像
            avatar = await page.query_selector('[class*="avatar"], [class*="user-info"] img')
            if avatar:
                return True
            # 检测侧边栏用户信息
            user_el = await page.query_selector('[class*="username"], [class*="nickname"]')
            if user_el:
                return True
        except Exception:
            pass
        return False

    async def extract_account_info(self, page) -> dict:
        """提取快手账号信息"""
        info = {
            "account_id": None,
            "account_name": None,
            "account_avatar": None,
            "account_url": None,
        }
        try:
            name_el = await page.query_selector('[class*="nickname"], [class*="username"]')
            if name_el:
                info["account_name"] = await name_el.inner_text()
        except Exception:
            pass
        return info
