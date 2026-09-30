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

### 现在的判据（**cookie 优先，全部实测确认**）

1. **cookie 判据**（唯一可靠的）
   —— 实测登录后 cookie 里有 **`userId`**（如 `5372574395`）：

       clientid / did / kpf / kpn / ktrace-context / kwfv1 /
       kwpsecproductname / kwscode / kwssectoken /
       kuaishou.server.webday7_ph / kuaishou.server.webday7_st / **userId**

   ⚠️ 注意实际名字是 **`kuaishou.server.webday7_st`**（带 `day7`），
   **不是** `kuaishou.server.web_st` —— 我第一版按印象写错了。
   所以这里用**后缀匹配**（`kuaishou.server.web` + `_st`），
   免得平台改 cookie 名（`webday7` / `web` 都见过）。

2. ~~站点接口~~ —— **实测不可用**：
   `/rest/wd/user/profile` 返回
   `{"result":2001,"error_msg":"[2001] antispam need captcha"}` ——
   **有风控，不能当登录判据**。

3. 判不出来 → **按未登录处理**（保守，不猜）。
"""

from __future__ import annotations

import logging

from app.services.cookies.base import PlatformDetector

logger = logging.getLogger("ylcraft.cookies.kuaishou")

# 登录后才有的 cookie（**实测确认**）
#
# `did` / `didv` 是**设备**标识，未登录也有；
# `userId` 与 `kuaishou.server.web*_st` 才是**登录**标志。
LOGIN_COOKIES_EXACT = ("userId",)

# 用**后缀**匹配会话 cookie —— 实测名字是 `kuaishou.server.webday7_st`，
# 不是 `kuaishou.server.web_st`（平台可能再改，所以不写死全名）
LOGIN_COOKIE_SUFFIX = "_st"
LOGIN_COOKIE_PREFIX = "kuaishou.server.web"

# ⚠️ 实测**不可用**的接口（保留记录，避免后人再试）
#
#     GET /rest/wd/user/profile
#     → {"result":2001,"error_msg":"[2001] antispam need captcha"}
#
# 有风控，**不能当登录判据**。
UNUSABLE_PROFILE_API = "https://www.kuaishou.com/rest/wd/user/profile"

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

    ## 判据：**cookie → 未登录**

    见模块 docstring：原来用模糊 CSS 选择器，
    而快手首页本来就有别人的头像/昵称，**未登录也会命中**。
    站点接口又被风控挡住，所以**只信 cookie**。
    """

    async def detect(self, page) -> bool:
        """检测用户是否已登录快手（只看 cookie）。"""
        try:
            cookies = await page.context.cookies("https://www.kuaishou.com")
        except Exception as exc:
            logger.warning("[kuaishou] 读 cookie 失败：%s", type(exc).__name__)
            # 读不到就按未登录 —— 宁可不给，也不要存废连接
            return False

        names = {c.get("name") for c in (cookies or [])}

        # 精确命中：userId
        hit = [n for n in LOGIN_COOKIES_EXACT if n in names]
        if hit:
            logger.info("[kuaishou] 检测到登录 cookie：%s", ", ".join(hit))
            return True

        # 后缀命中：kuaishou.server.web*_st（名字含 day7 之类）
        sess = [
            n for n in names
            if n.startswith(LOGIN_COOKIE_PREFIX) and n.endswith(LOGIN_COOKIE_SUFFIX)
        ]
        if sess:
            logger.info("[kuaishou] 检测到会话 cookie：%s", ", ".join(sess))
            return True

        # 判不出来 → **按未登录处理**（保守，不猜）
        #
        # 宁可不给，也不要存一个"看着登录了但没凭证"的废连接 ——
        # 那会导致之后所有搜索都失败，且极难定位。
        logger.info("[kuaishou] 未检测到登录 cookie（只有设备标识）")
        return False

    async def extract_account_info(self, page) -> dict:
        """提取快手账号信息。

        ⚠️ **只从 cookie 取** —— 实测：
          · DOM 上的昵称/头像是**别人的**（信息流作者）
          · `/rest/wd/user/profile` 被风控挡（`antispam need captcha`）

        所以 `userId` 从 cookie 取，昵称/头像**留空**（不编造）。
        需要昵称的话，用 `userId` 去请求公开的**用户主页接口**。
        """
        info = {
            "account_id": None,
            "account_name": None,
            "account_avatar": None,
            "account_url": None,
        }

        try:
            cookies = await page.context.cookies("https://www.kuaishou.com")
            for c in cookies or []:
                if c.get("name") == "userId":
                    uid = str(c.get("value") or "")
                    info["account_id"] = uid
                    if uid:
                        # 个人页真实路径带 ID：/profile/{userId}
                        info["account_url"] = f"https://www.kuaishou.com/profile/{uid}"
                    break
        except Exception as exc:
            logger.debug("[kuaishou] 提取账号信息失败：%s", type(exc).__name__)

        return info
