"""
YLCraft — 番茄小说平台适配器

登录检测 + 账号信息提取。

判定依据（比 DOM 探测可靠）：番茄作家后台的 `account/info/v0/` 接口
在登录态下返回 `code:0` 且带 `author_name`；未登录会返回登录页重定向或
非 0 业务码。因此这里**优先用接口判定**，避免番茄前端改版把 DOM 选择器打散。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.services.cookies.base import PlatformDetector

logger = logging.getLogger("ylcraft.cookies.platforms.fanqie")

#: 作家资料接口。与 `services/platforms/fanqie/apis.py` 的 ACCOUNT_INFO 保持一致；
#: 这里单独写常量是为了避免 cookies 层反向依赖 platforms 业务层。
_ACCOUNT_INFO_URL = (
    "https://fanqienovel.com/api/author/account/info/v0/"
    "?aid=2503&app_name=muye_novel"
)


class FanqieDetector(PlatformDetector):
    """番茄小说（作家后台）登录检测"""

    async def detect(self, page) -> bool:
        """检测用户是否已登录番茄作家后台。

        先看 URL：被踢到登录页直接判未登录。再用 `account/info` 接口确认，
        接口不可用时回退到 DOM 探测。
        """
        try:
            url = (page.url or "").lower()
            if "login" in url or "passport" in url:
                return False
        except Exception:
            pass

        # 首选：接口判定（登录态下 code=0 且有 author_name）
        try:
            result = await page.evaluate(
                """async (url) => {
                    try {
                        const r = await fetch(url, { credentials: 'include' });
                        const d = await r.json();
                        return { code: d && d.code, name: (d && d.data && d.data.author_name) || '' };
                    } catch (e) { return { code: null, name: '' }; }
                }""",
                _ACCOUNT_INFO_URL,
            )
            if isinstance(result, dict) and result.get("code") == 0 and result.get("name"):
                return True
        except Exception:
            pass

        # 回退：DOM 探测（进入作家专区后顶部会显示作家名）
        try:
            el = await page.query_selector(
                '[class*="author-name"], [class*="writer-name"], [class*="user-name"]'
            )
            if el:
                return True
        except Exception:
            pass

        return False

    async def extract_account_info(self, page) -> Dict[str, Any]:
        """提取番茄作家账号信息（作家名 / 头像 / 作家 ID）。

        ⚠️ 只取展示所需的非敏感字段。**不提取** `phone_number`、
        `identity_name_mask`、`identity_code_mask` 等个人敏感信息。
        """
        info: Dict[str, Any] = {
            "account_id": None,
            "account_name": None,
            "account_avatar": None,
            "account_url": None,
        }
        try:
            result = await page.evaluate(
                """async (url) => {
                    try {
                        const r = await fetch(url, { credentials: 'include' });
                        const d = await r.json();
                        const data = (d && d.data) || {};
                        return {
                            name: data.author_name || '',
                            avatar: data.avatar_url || '',
                            level: data.author_level_id || null,
                        };
                    } catch (e) { return null; }
                }""",
                _ACCOUNT_INFO_URL,
            )
            if isinstance(result, dict):
                if result.get("name"):
                    info["account_name"] = result["name"]
                if result.get("avatar"):
                    info["account_avatar"] = result["avatar"]
        except Exception as exc:
            logger.debug("fanqie extract_account_info via api failed: %s", exc)

        if not info["account_name"]:
            # 回退：DOM 里找作家名
            try:
                el = await page.query_selector(
                    '[class*="author-name"], [class*="writer-name"], [class*="user-name"]'
                )
                if el:
                    info["account_name"] = (await el.inner_text()).strip()
            except Exception:
                pass

        return info
