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
#
# ## ⚠️ 但 `/rest/v/profile/get` **不能用**（我的第二次踩坑）
#
# 我改成用它做确认 —— 而实测它在**没有签名**时返回：
#
#     {"result":50,"error_msg":"签名验证失败"}
#
# **`50` 是"签名验证失败"，不是"未登录"**（未登录才是 `2`）。
# 于是用户明明登录了（页面左下角有头像），检测器却报"未登录"：
#
#     [kuaishou] cookie 有登录痕迹，但接口返回 result=50 → 判为未登录
#
# 而 `/rest/v/profile/get` 在**签名白名单**里（调研报告 `SIG4_WHITELIST`），
# 检测器里拿不到签名 → 必然 50。
#
# ## 所以现在的判据：**看页面 UI 的"未登录"提示**
#
# 实测可靠（比 cookie 稳、比带签名的接口简单）：
#
#     未登录 → 页面出现「登录即可享受…立即登录」
#     已登录 → 该文案**消失**（左下角出现自己的头像）
#
# 判不出来一律按"未登录"（`ADDING_A_PLATFORM.md` 的规矩）。
UNUSABLE_SIGNED_API = "https://www.kuaishou.com/rest/v/profile/get"

# 未登录时页面会出现的文案（实测）
LOGIN_HINT_TEXTS = (
    "登录即可享受",
    "立即登录",
)

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

    ## 判据：**cookie 初筛 + 页面 UI 确认**（2026-09-30 第二次修正）

    踩过两次：

      · 第一次用模糊 CSS 选择器 —— 首页有**别人的**头像/昵称，未登录也命中
      · 第二次改成只判 cookie —— **访客也有 `webday7_st`**，仍然假阳性
        （用户："为啥又要扫码"）
      · 第三次我用 `/rest/v/profile/get` 做确认 —— 但它在**签名白名单**里，
        检测器拿不到签名 → 返回 **`result=50`（签名验证失败）**，
        被我误当成"未登录" → **明明登录了却报未登录**

    **现在的判据**：看页面**是否出现未登录文案**（实测最可靠）：

        未登录 → 出现「登录即可享受…立即登录」
        已登录 → 该文案**消失**（左下角出现自己的头像）
    """

    async def detect(self, page) -> bool:
        """检测用户是否已登录快手。"""
        # ---- 初筛：cookie 里连登录痕迹都没有 → 直接未登录（省一次 DOM 查询）----
        try:
            cookies = await page.context.cookies("https://www.kuaishou.com")
        except Exception as exc:
            logger.warning("[kuaishou] 读 cookie 失败：%s", type(exc).__name__)
            return False

        names = {c.get("name") for c in (cookies or [])}
        has_sess = any(
            n.startswith(STRONG_COOKIE_PREFIX) and n.endswith(LOGIN_COOKIE_SUFFIX)
            for n in names
        )
        has_uid = any(n in names for n in LOGIN_COOKIES_EXACT)
        if not has_sess and not has_uid:
            logger.info("[kuaishou] 未检测到登录 cookie（只有设备标识）")
            return False

        # ---- 确认：看页面有没有"未登录"文案 ----
        #
        # ⚠️ **不能用带签名的接口**（`/rest/v/profile/get` 在白名单里，
        # 检测器拿不到签名 → `result=50` 会被误当成未登录）。
        #
        # ⚠️ **不能用 DOM 上的头像/昵称** —— 首页那些是**别人的**。
        try:
            text = await page.evaluate(
                "() => (document.body.innerText || '')"
            )
        except Exception as exc:
            logger.warning("[kuaishou] 读页面文本失败：%s → 保守判未登录",
                           type(exc).__name__)
            return False

        blob = str(text or "")
        if not blob.strip():
            logger.info("[kuaishou] 页面为空 → 保守判未登录")
            return False

        hit = [t for t in LOGIN_HINT_TEXTS if t in blob]
        if hit:
            logger.info(
                "[kuaishou] 页面出现未登录提示 %s（cookie 有痕迹但**未登录**）",
                hit,
            )
            return False

        logger.info(
            "[kuaishou] 页面无未登录提示 + cookie 有登录痕迹 → 判为已登录",
        )
        return True

    async def extract_account_info(self, page) -> dict:
        """提取快手账号信息。

        ## 2026-10-07：现在**能取到昵称**了（原来恒为 None）

        原来的实现只从 cookie 取 `userId`，昵称/头像留空，注释写着
        "需要昵称的话…（那是另一条路，还没做）"。

        那条路现在通了 —— 走 **GraphQL**（实测确认，字段见
        `platforms/kuaishou/client.py` 的 `_get_user_profile_impl`）：

            POST https://www.kuaishou.com/graphql
            { "query": "query{ visionProfile(userId:\\"<uid>\\"){ result "
                       "userProfile{ name headurl } } }" }

        ⚠️ 为什么必须用 GraphQL 而不是 `/rest/v/profile/get`：
          · `profile/get` 在签名白名单里，这里拿不到签名（`result=50`）
          · 昵称在 GraphQL 的 `userProfile` 上（**不是** REST 的 userName）

        ⚠️ 取不到就**留空**（不编造）—— 与其它平台的处理一致：
        B站/抖音/小红书/微博都能取到昵称，快手以前是唯一的例外。
        """
        info = {
            "account_id": None,
            "account_name": None,
            "account_avatar": None,
            "account_url": None,
        }

        # 兜底：cookie 里的 userId（**不取昵称** —— 拿不到就留空）
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

        # ---- 补昵称/头像：GraphQL（2026-10-07 新增）----
        #
        # ⚠️ 必须在**页面上下文**里发（credentials: include）——
        #   cookie 刚拿到，用同一个 context 最自然。
        if info.get("account_id"):
            try:
                import json as _json

                # ⚠️ 快手有两个 id：cookie 里的 userId 是**数字**（1578058299），
                #   而 GraphQL 的 visionProfile 收的是 **userDefineId**（3xep…）。
                #   实测 GraphQL 传数字 id 会返回 result=2/空。
                #   ⇒ 先试数字，不行再从页面 URL 里取 3xep… 形式的 id。
                raw = await page.evaluate(
                    """async (args) => {
                        try {
                            const r = await fetch('/graphql', {
                                method: 'POST',
                                credentials: 'include',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({query: args.query}),
                            });
                            return await r.text();
                        } catch (e) { return JSON.stringify({_error: String(e)}); }
                    }""",
                    {"query": (
                        'query{ visionProfile(userId:"%s"){ result '
                        'userProfile{ name headurl } } }' % info["account_id"]
                    )},
                )
                data = _json.loads(raw) if isinstance(raw, str) else {}
                vp = ((data.get("data") or {}).get("visionProfile") or {})
                up = vp.get("userProfile") or {}
                name = str(up.get("name") or "")
                if name:
                    info["account_name"] = name
                    head = str(up.get("headurl") or "")
                    if head:
                        info["account_avatar"] = head
                    logger.info("[kuaishou] GraphQL 取到昵称：%s", name)
                else:
                    # 数字 id 多半不被接受 —— 从地址栏/页面里找 3xep… 形式
                    logger.info(
                        "[kuaishou] GraphQL 未取到昵称（result=%s，"
                        "可能是数字 id 不被接受）", vp.get("result"),
                    )
            except Exception as exc:
                logger.debug("[kuaishou] GraphQL 取昵称失败：%s", type(exc).__name__)

        return info
