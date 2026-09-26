"""
YLCraft — 抖音平台适配器

登录检测 + 账号信息提取

2026-09-26 实测更正：
  原先的 detect() 用 `if "/recommend" in page.url: return True` 判断登录。
  这是**错的**——/recommend 是未登录也能访问的公开推荐页，会把游客误判成已登录，
  从而保存一个没有登录凭证的废连接。

  现在改为问抖音自己的接口：
    GET /aweme/v1/web/user/profile/self/
      未登录 → {"status_code": 8}
      已登录 → {"status_code": 0, "user": {...}}
  实测（未登录、headless）返回 status_code=8，判据可靠；
  不再依赖易变且可能不存在的 CSS 类名。
"""

from __future__ import annotations

import logging

from app.services.cookies.base import PlatformDetector

logger = logging.getLogger("ylcraft.cookies.douyin")

# 抖音「当前登录用户」接口（实测确认）
PROFILE_SELF = "https://www.douyin.com/aweme/v1/web/user/profile/self/"

# 未登录时该接口的 status_code（实测值）
NOT_LOGGED_IN_CODE = 8


class DouyinDetector(PlatformDetector):
    """抖音登录检测"""

    async def detect(self, page) -> bool:
        """检测用户是否已登录抖音。

        主判据：调抖音自己的 profile/self 接口看 status_code。
        辅助判据：DOM 出现用户头像（接口异常时兜底）。
        任一路径都不把「URL 含有某个字符串」当作已登录。
        """
        # 方式1（主）：问站点自己的接口
        try:
            result = await page.evaluate(
                """
                async () => {
                    try {
                        const r = await fetch(
                            'https://www.douyin.com/aweme/v1/web/user/profile/self/',
                            {credentials: 'include'}
                        );
                        const j = await r.json();
                        return {code: j.status_code, hasUser: !!(j && j.user && j.user.uid)};
                    } catch (e) {
                        return {code: null, error: String(e)};
                    }
                }
                """
            )
            code = result.get("code")
            if code == 0 and result.get("hasUser"):
                return True
            if code == NOT_LOGGED_IN_CODE:
                return False
        except Exception as exc:  # 页面跳转中等，落到兜底
            logger.debug("[DouyinDetector] profile/self 探测失败：%s", exc)

        # 方式2（兜底）：DOM 出现头像才算登录；没有明确的登录元素不算
        try:
            avatar = await page.query_selector(
                '[class*="avatar"] img, [data-e2e*="avatar"], .semi-avatar'
            )
            if avatar:
                return True
            # 出现登录引导 = 明确未登录
            login_entry = await page.query_selector('[class*="login"]')
            if login_entry:
                return False
        except Exception:
            pass
        return False

    async def extract_account_info(self, page) -> dict:
        """提取抖音账号信息（优先用接口，DOM 兜底）。"""
        info = {
            "account_id": None,
            "account_name": None,
            "account_avatar": None,
            "account_url": None,
        }
        try:
            result = await page.evaluate(
                """
                async () => {
                    try {
                        const r = await fetch(
                            'https://www.douyin.com/aweme/v1/web/user/profile/self/',
                            {credentials: 'include'}
                        );
                        const j = await r.json();
                        const u = (j && j.user) || {};
                        return {
                            uid: u.uid ? String(u.uid) : '',
                            sec_uid: u.sec_uid || '',
                            nickname: u.nickname || '',
                            avatar: (u.avatar_thumb && u.avatar_thumb.url_list
                                     && u.avatar_thumb.url_list[0]) || '',
                        };
                    } catch (e) {
                        return {};
                    }
                }
                """
            )
            if result.get("uid"):
                info["account_id"] = result["uid"]
                info["account_name"] = result.get("nickname") or ""
                info["account_avatar"] = result.get("avatar") or ""
                sec = result.get("sec_uid") or ""
                if sec:
                    info["account_url"] = f"https://www.douyin.com/user/{sec}"
        except Exception as exc:
            logger.debug("[DouyinDetector] 接口取账号信息失败：%s", exc)

        # DOM 兜底
        if not info["account_name"]:
            try:
                el = await page.query_selector('[class*="nickname"], [data-e2e*="nickname"]')
                if el:
                    info["account_name"] = (await el.inner_text()).strip()
            except Exception:
                pass
        return info
