"""
YLCraft — 抖音平台适配器

登录检测 + 账号信息提取
"""

from __future__ import annotations

from app.services.cookie_acquisition.base import PlatformDetector


class DouyinDetector(PlatformDetector):
    """抖音登录检测"""

    async def detect(self, page) -> bool:
        """检测用户是否已登录抖音"""
        # 方式1：URL 检测
        if "/recommend" in page.url or "/follow" in page.url:
            return True
        # 方式2：元素检测
        try:
            # 抖音登录后导航栏变化
            nav = await page.query_selector(".home-nav")
            if nav:
                return True
            # 检测用户头像
            avatar = await page.query_selector('[class*="avatar"] img, [class*="user"] img')
            if avatar:
                return True
        except Exception:
            pass
        return False

    async def extract_account_info(self, page) -> dict:
        """提取抖音账号信息"""
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
