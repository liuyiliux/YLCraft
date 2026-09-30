"""
YLCraft — 快手平台适配器

登录检测 + 账号信息提取

## ⚠️ 原来的实现有两个真问题（2026-09-29 实测修正）

用户反馈：

    "打开的网址不是登录的 我点击登录是弹窗的 扫码完没判断获取到"

### 问题 1：登录 URL 指向信息流首页

见 `cookies/base.py` —— 原来 `PLATFORM_LOGIN_URLS["kuaishou"]` 是
`https://www.kuaishou.com`（推荐流），用户看到的是信息流，不是登录页。
已改为 `/profile`（未登录会引导登录）。

### 问题 2：检测器用**模糊 CSS 选择器**，把"别人的头像"当成登录标志

原实现：

    avatar = await page.query_selector('[class*="avatar"], [class*="user-info"] img')
    user_el = await page.query_selector('[class*="username"], [class*="nickname"]')

**快手的信息流首页本身就有大量头像和昵称**（作者名、推荐视频的 UP 名），
所以"页面里有头像"**根本不代表已登录** —— 未登录时照样命中。

这与 `docs/platform/ADDING_A_PLATFORM.md` 的硬规矩冲突：

> 登录检测必须问站点自己的接口，不能看 URL、也不能只看 CSS 类名。
> ……**判不出来一律按"未登录"处理**，不要乐观假设。

### 现在的判据（**cookie → 接口 → 按未登录**）

1. **cookie 判据**（最可靠、最便宜）：快手登录后会有
   `kuaishou.server.web_st`（会话令牌）。未登录只有 `did`/`didv`（设备标识）。
2. **站点接口兜底**：`/rest/wd/user/profile` 需登录态才返回 `result == 1`。
3. 都拿不到 → **按未登录处理**（保守，不猜）。
"""

from __future__ import annotations

import json
import logging

from app.services.cookies.base import PlatformDetector

logger = logging.getLogger("ylcraft.cookies.kuaishou")

# 登录后才会出现的 cookie（会话令牌）
#
# 实测：未登录访问快手也有 `did` / `didv`（**设备**标识），
# 但**不会有** `kuaishou.server.web_st`（**登录会话**）。
LOGIN_COOKIES = (
    "kuaishou.server.web_st",
    "kuaishou.server.web_ph",
    "userId",
)

# 站点自己的"我是谁"接口（未登录时 result != 1）
USER_PROFILE_API = "https://www.kuaishou.com/rest/wd/user/profile"

# 在页面上下文里 fetch（带上 cookie），返回原始 JSON 字符串
_JS_FETCH = """
async (url) => {
  try {
    const r = await fetch(url, { credentials: 'include' });
    return await r.text();
  } catch (e) {
    return JSON.stringify({ _error: String(e).slice(0, 60) });
  }
}
"""


class KuaishouDetector(PlatformDetector):
    """快手登录检测。

    ## 判据顺序：**cookie → 接口 → 未登录**

    见模块 docstring：原来用模糊 CSS 选择器，
    而快手首页本来就有别人的头像/昵称，**未登录也会命中**。
    """

    async def detect(self, page) -> bool:
        """检测用户是否已登录快手。"""
        # ---- ① cookie 判据（最可靠，且不需要网络）----
        try:
            cookies = await page.context.cookies("https://www.kuaishou.com")
            names = {c.get("name") for c in (cookies or [])}
            hit = [n for n in LOGIN_COOKIES if n in names]
            if hit:
                logger.info("[kuaishou] 检测到登录 cookie：%s", ", ".join(hit))
                return True
        except Exception as exc:
            logger.debug("[kuaishou] 读 cookie 失败：%s", type(exc).__name__)

        # ---- ② 问站点自己的接口 ----
        try:
            raw = await page.evaluate(_JS_FETCH, USER_PROFILE_API)
            data = json.loads(raw) if isinstance(raw, str) else (raw or {})
            if data.get("result") == 1:
                logger.info("[kuaishou] 接口确认已登录（result=1）")
                return True
            logger.info("[kuaishou] 接口返回 result=%s（未登录或需登录态）",
                        data.get("result"))
        except Exception as exc:
            logger.debug("[kuaishou] 接口检测失败：%s", type(exc).__name__)

        # ---- ③ 判不出来 → **按未登录处理**（保守，不猜）----
        #
        # 宁可不给，也不要存一个"看着登录了但没凭证"的废连接 ——
        # 那会导致之后所有搜索都失败，且极难定位。
        return False

    async def extract_account_info(self, page) -> dict:
        """提取快手账号信息（仅已登录时有意义）。"""
        info = {
            "account_id": None,
            "account_name": None,
            "account_avatar": None,
            "account_url": None,
        }

        # userId 直接从 cookie 拿（比读 DOM 可靠 —— DOM 上是别人的昵称）
        try:
            cookies = await page.context.cookies("https://www.kuaishou.com")
            for c in cookies or []:
                if c.get("name") == "userId":
                    info["account_id"] = c.get("value")
                    break
        except Exception:
            pass

        # 昵称/头像走接口
        try:
            raw = await page.evaluate(_JS_FETCH, USER_PROFILE_API)
            data = json.loads(raw) if isinstance(raw, str) else (raw or {})
            user = data.get("data") or {}
            nested = user.get("user") if isinstance(user.get("user"), dict) else {}
            name = user.get("userName") or user.get("name") or nested.get("name")
            avatar = user.get("headUrl") or user.get("avatar") or nested.get("headUrl")
            if name:
                info["account_name"] = str(name)
            if avatar:
                info["account_avatar"] = str(avatar)
        except Exception as exc:
            logger.debug("[kuaishou] 提取账号信息失败：%s", type(exc).__name__)

        return info
