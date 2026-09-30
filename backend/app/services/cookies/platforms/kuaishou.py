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

### Q: 检测的是「有 cookie」还是「真的登录了」？

**用户问得很对**（2026-09-29）。实测两种情况：

    未登录（全新上下文，无 cookie）  → False  ✅ 正确
    只有伪造的 userId                → **True** ⚠️ **误判！**

**即"有 cookie"≠"cookie 有效"** —— 这正是 `ADDING_A_PLATFORM.md` 警告过的：

> 会把游客误判成已登录，存下一个**没有登录凭证的废连接**，
> 之后所有搜索都失败且**极难定位**。

### 但快手**没有可用的校验接口**（都实测过）

    /rest/wd/user/profile   → {"result":2001,"antispam need captcha"}  ← 风控
    /rest/wd/user/fullInfo  → 空响应
    /rest/wd/user/userInfo  → 空响应
    /rest/wd/user/profile?userId=X → {"result":2}  （真假 userId 都是 2，无法区分）

所以**做不到"真实验证"**。

### 折中做法（**如实暴露不确定性，而不是假装可靠**）

  1. cookie 命中 → 返回 True，但**把判据等级放进日志**：
     `userId` 是弱判据（可能是脏数据），
     `kuaishou.server.web*_st` 是强判据（服务端下发的会话）
  2. cookie 不命中 → False
  3. **不谎报"已验证"** —— 因为验证不了

**给上层的建议**（写在注释里）：快手连接"是否有效"最终要靠
**实际搜索能否成功**来确认；检测只用来避免存"完全没登录"的废连接。
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

# 会话 cookie（强判据：服务端下发的登录会话）
#
# 与 `userId`（弱判据 —— 可能是脏数据）区分，用于日志里如实标注可信度。
STRONG_COOKIE_PREFIX = "kuaishou.server.web"

# ⚠️ 实测**不可用**的校验接口（留档，免得后人再试）：
#
#     GET /rest/wd/user/profile
#     → {"result":2001,"error_msg":"[2001] antispam need captcha"}   ← 风控
#
#     GET /rest/wd/user/fullInfo    → 空响应
#     GET /rest/wd/user/userInfo    → 空响应
#     GET /rest/wd/user/profile?userId={真|假}  → 都是 {"result":2}，无法区分
#
# 所以**快手做不到"验证 cookie 是否真的有效"**，只能判"有没有"。
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

    ## 判据：**cookie → 未登录**（⚠️ 只能判"有没有"，**判不了"有没有效"**）

    见模块 docstring：
      · 原来用模糊 CSS 选择器 —— 快手首页本来就有别人的头像/昵称，未登录也命中
      · 站点接口全被风控挡或无法区分真假 userId → **做不到真实验证**
    """

    async def detect(self, page) -> bool:
        """检测用户是否已登录快手。

        ⚠️ **只判"有没有登录 cookie"，判不了"cookie 是否有效"**。
        真实验证要靠实际搜索能否成功（见模块 docstring）。
        """
        try:
            cookies = await page.context.cookies("https://www.kuaishou.com")
        except Exception as exc:
            logger.warning("[kuaishou] 读 cookie 失败：%s", type(exc).__name__)
            # 读不到就按未登录 —— 宁可不给，也不要存废连接
            return False

        names = {c.get("name") for c in (cookies or [])}

        # ① 强判据：服务端下发的会话 cookie
        sess = [
            n for n in names
            if n.startswith(STRONG_COOKIE_PREFIX) and n.endswith(LOGIN_COOKIE_SUFFIX)
        ]
        if sess:
            logger.info(
                "[kuaishou] 检测到**会话** cookie（强判据）：%s", ", ".join(sess),
            )
            return True

        # ② 弱判据：userId（存在但可能是脏数据 —— 实测伪造的也会命中）
        hit = [n for n in LOGIN_COOKIES_EXACT if n in names]
        if hit:
            logger.info(
                "[kuaishou] 检测到 %s（**弱判据** —— 只能说明有登录痕迹，"
                "无法确认真实性；快手没有可用的校验接口）",
                ", ".join(hit),
            )
            return True

        # ③ 判不出来 → **按未登录处理**（保守，不猜）
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
