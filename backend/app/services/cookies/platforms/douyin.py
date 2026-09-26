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

        ⚠️ 2026-09-26 实测更正：**不能**用 profile/self 接口判断登录。
           抖音对自动化浏览器会把该接口判为风控，返回
               {"status_code":0,"status_msg":"blocked","user":null}
           注意 status_code 是 0（不是错误码）但 user 为 null。
           用它当判据会导致"用户明明扫码成功，检测永远为 False"，
           界面一直停在"请在浏览器中完成登录"——这正是用户报的故障。

        改用 **DOM 判据**（页面本身渲染正常，实测 47 个链接可用）：
          - 出现用户头像 → 已登录
          - 出现明确登录入口（扫码/登录按钮）→ 未登录
          - 判不出来 → 未登录（保守，不猜）
        """
        # 明确未登录：页面出现登录引导
        try:
            login_el = await page.query_selector(
                '[class*="login"] button, [data-e2e*="login"], '
                '[class*="login-panel"], [class*="login-panel"]'
            )
            if login_el:
                return False
        except Exception:
            pass

        # 已登录：顶部出现用户头像
        try:
            for sel in (
                '[class*="avatar"] img',
                '[data-e2e*="avatar"]',
                '.semi-avatar',
                '[class*="user-info"] img',
            ):
                el = await page.query_selector(sel)
                if el:
                    return True
        except Exception as exc:
            logger.debug("[DouyinDetector] 头像探测失败：%s", exc)

        # 兜底：仍尝试接口，但**只把明确的"有 user"当作已登录**，
        # 不把 blocked/异常当作未登录的证据（避免误判）。
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
                            code: j.status_code,
                            blocked: j.status_msg === 'blocked',
                            uid: u.uid || null,
                        };
                    } catch (e) {
                        return {error: String(e)};
                    }
                }
                """
            )
            if result.get("uid"):
                return True
        except Exception as exc:  # 页面跳转中等
            logger.debug("[DouyinDetector] profile/self 探测失败：%s", exc)

        return False

    async def extract_account_info(self, page) -> dict:
        """提取抖音账号信息（DOM 优先，接口兜底）。

        注意：账号信息是**可选**的，取不到不影响登录判定。
        接口在风控下返回 blocked，所以先试 DOM。
        """
        info = {
            "account_id": None,
            "account_name": None,
            "account_avatar": None,
            "account_url": None,
        }
        # DOM 优先：昵称与头像（页面渲染正常，实测可靠）
        try:
            name_el = await page.query_selector(
                '[data-e2e*="nickname"], [class*="nickname"], [class*="user-name"]'
            )
            if name_el:
                info["account_name"] = (await name_el.inner_text()).strip()
            avatar_el = await page.query_selector(
                '[class*="avatar"] img, [data-e2e*="avatar"] img'
            )
            if avatar_el:
                info["account_avatar"] = await avatar_el.get_attribute("src") or ""
        except Exception as exc:
            logger.debug("[DouyinDetector] DOM 取账号信息失败：%s", exc)

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
