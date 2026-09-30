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

# ⚠️ **cookie 判据是假阳性 —— 必须用接口兜底**（2026-09-30 实测）
#
# 原来只用 cookie 名判断，实测日志：
#
#     20:03:03~08  [kuaishou] 未检测到登录 cookie（只有设备标识）
#     20:03:09     [kuaishou] 检测到**会话** cookie：kuaishou.server.webday7_st
#     20:03:10     Cookie file synced
#
# **那 6 秒内用户没扫码** —— 浏览器**自己**生成了 `webday7_st`，
# 即**访客也有这个 cookie**！于是：
#
#   · 检测器报"成功"（**假阳性**）
#   · 存下的是**未登录的 cookie**
#   · 用户下次来还得扫码（"为啥又要扫码"）
#   · `profile/get` 恒返回 `result:2`（页面 UI 也显示"登录即可享受"）
#
# `ADDING_A_PLATFORM.md` 早就警告过：
#   "会把游客误判成已登录，存下一个**没有登录凭证的废连接**"
#
# **可靠判据**：`/rest/v/profile/get` —— 登录时 `result=1`，
# 未登录时 `result=2`（实测：页面自己发也是 2）。
PROFILE_API = "https://www.kuaishou.com/rest/v/profile/get"

# 实测**不可用**的校验接口（留档，免得后人再试）：
#
#     GET /rest/wd/user/profile
#     → {"result":2001,"error_msg":"[2001] antispam need captcha"}   ← 风控
#
#     GET /rest/wd/user/fullInfo    → 空响应
#     GET /rest/wd/user/userInfo    → 空响应
#     GET /rest/wd/user/profile?userId={真|假}  → 都是 {"result":2}，无法区分
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

    ## 判据：**cookie 有登录痕迹 → 再用接口确认**（2026-09-30 修正）

    见模块 docstring：
      · 原来用模糊 CSS 选择器 —— 快手首页本来就有别人的头像/昵称，未登录也命中
      · 改成只判 cookie 后**仍然假阳性** —— 实测访客也有 `webday7_st`，
        于是"检测成功 → 存下废连接 → 用户下次还得扫码"
      · 现在加**接口确认**：`/rest/v/profile/get` 登录时 `result=1`、
        未登录 `result=2`
    """

    async def detect(self, page) -> bool:
        """检测用户是否已登录快手（cookie 初筛 + **接口确认**）。"""
        try:
            cookies = await page.context.cookies("https://www.kuaishou.com")
        except Exception as exc:
            logger.warning("[kuaishou] 读 cookie 失败：%s", type(exc).__name__)
            # 读不到就按未登录 —— 宁可不给，也不要存废连接
            return False

        names = {c.get("name") for c in (cookies or [])}
        has_sess = any(
            n.startswith(STRONG_COOKIE_PREFIX) and n.endswith(LOGIN_COOKIE_SUFFIX)
            for n in names
        )
        has_uid = any(n in names for n in LOGIN_COOKIES_EXACT)

        # ---- 初筛：连登录痕迹都没有 → 直接未登录（省一次请求）----
        if not has_sess and not has_uid:
            logger.info("[kuaishou] 未检测到登录 cookie（只有设备标识）")
            return False

        # ---- 确认：必须问站点接口 ----
        #
        # ⚠️ **不能只信 cookie**：实测访客也有 `webday7_st`，
        # 只判 cookie 会把游客当成已登录（用户反馈"为啥又要扫码"）。
        try:
            raw = await page.evaluate(_JS_FETCH, PROFILE_API)
            import json as _json

            data = _json.loads(raw) if isinstance(raw, str) else (raw or {})
            result = data.get("result")
            if result == 1:
                logger.info("[kuaishou] 接口确认已登录（profile/get result=1）")
                return True
            logger.info(
                "[kuaishou] cookie 有登录痕迹，但接口返回 result=%s "
                "→ **判为未登录**（访客也有 webday7_st，不能只看 cookie）",
                result,
            )
            return False
        except Exception as exc:
            logger.warning(
                "[kuaishou] 接口确认失败（%s）→ 保守判为未登录",
                type(exc).__name__,
            )
            # 判不出来一律按"未登录"（`ADDING_A_PLATFORM.md` 的规矩）
            return False
            return True

    async def extract_account_info(self, page) -> dict:
        """提取快手账号信息。

        ## 来源（按可靠性排序）

        1. **`/rest/v/profile/get`**（登录时 `result=1`）—— 能拿到昵称/头像。
           实测未登录时返回 `result=2`，所以拿不到就**留空**（不编造）。
        2. `userId` 从 cookie 取（**注意：访客也可能有这个 cookie**，
           所以只在接口确认后才可信）。

        ⚠️ **不读 DOM** —— 实测快手首页的昵称/头像是**别人的**
        （信息流作者），不是登录用户。
        """
        info = {
            "account_id": None,
            "account_name": None,
            "account_avatar": None,
            "account_url": None,
        }

        # ① 接口优先（能拿到昵称/头像）
        try:
            raw = await page.evaluate(_JS_FETCH, PROFILE_API)
            import json as _json

            data = _json.loads(raw) if isinstance(raw, str) else (raw or {})
            if data.get("result") == 1:
                d = data.get("data") or {}
                user = d.get("user") if isinstance(d.get("user"), dict) else d
                uid = str(user.get("id") or user.get("userId") or "")
                if uid:
                    info["account_id"] = uid
                    info["account_url"] = (
                        f"https://www.kuaishou.com/profile/{uid}"
                    )
                name = user.get("name") or user.get("userName")
                avatar = user.get("headUrl") or user.get("headurl")
                if name:
                    info["account_name"] = str(name)
                if avatar:
                    info["account_avatar"] = str(avatar)
                if info["account_id"] or info["account_name"]:
                    return info
        except Exception as exc:
            logger.debug("[kuaishou] 接口取资料失败：%s", type(exc).__name__)

        # ② 兜底：cookie 里的 userId（**不取昵称** —— 拿不到就留空）
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
