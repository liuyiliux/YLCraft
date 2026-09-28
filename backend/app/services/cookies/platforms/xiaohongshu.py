"""
YLCraft — 小红书平台适配器

登录检测 + 账号信息提取

2026-09-26 实测更正：
  原先 detect() 里 `if "/explore" in page.url or "/user/profile" in page.url: return True`
  是**错的**方向——这两个路径未登录也能打开（/user/profile 直接访问不跳转），
  会把游客误判成已登录。

  实测未登录基线（headless，干净 profile）：
    访问 /explore  → 被重定向到 /login?redirectPath=...   ← 可靠信号
    页面 [class*="login"] 命中 3 个，[class*="avatar"] 命中 0 个
    user/me 接口返回 500（网关拒绝），**不能**作为判据

  所以判据改为：
    1) URL 落在 /login → 明确未登录（最强、最稳）
    2) 出现用户头像 → 已登录
    3) 都判不出 → 未登录（宁可不保存，也不存一个假连接）
"""

from __future__ import annotations

import logging

from app.services.cookies.base import PlatformDetector

logger = logging.getLogger("ylcraft.cookies.xhs")


class XhsDetector(PlatformDetector):
    """小红书登录检测"""

    async def detect(self, page) -> bool:
        """检测用户是否已登录小红书。

        ## 判据顺序

          1. 落在 /login → False（实测未登录必被重定向到这里）
          2. 头像元素 **且** 有 `web_session` → True
          3. 其余 → False（不猜）

        ## ⚠️ 为什么加 "且有 web_session"

        用户反馈"扫码登录后关掉浏览器，再搜索就不弹浏览器了"。

        实测原因：持久化 profile 里**残留着上次的 `web_session`**，
        于是页面直接进 `/explore`（不跳登录页）、DOM 里也有
        `.reds-avatar` → 检测器判"已登录" → **4 秒内保存并关闭**，
        用户**根本来不及扫码**。

        加一层 cookie 检查能挡掉"只有残留 DOM、没有凭证"的情况。

        ## ⚠️ 试过但**行不通**的方案：接口验证（2026-09-28）

        我一度改成"调 `user/me` 验证登录态真的可用"，但实测：
        `user/me` / `config` / `homefeed` **全部返回 500
        `create invoker failed, service: jarvis-gateway-default`**
        —— 小红书网关对这些接口一律拒绝，**与登录态无关**。
        `user_selfinfo`（edith 域）则是 406 跨域。

        所以**没有可用的 HTTP 判据**，只能靠 DOM + cookie 组合。
        （本文件顶部的历史注释也早就记过"user/me 不能作为判据"。）
        """
        url = page.url or ""

        # 1. 明确未登录：被重定向到登录页（含二维码/手机号登录界面）
        if "/login" in url:
            return False

        # 2. 头像元素 + 有效凭证
        try:
            for sel in (
                ".user-info .avatar",
                '[class*="side-bar"] [class*="avatar"]',
                '[class*="user"] img[class*="avatar"]',
                ".reds-avatar",
            ):
                el = await page.query_selector(sel)
                if el:
                    if await self._has_session_cookie(page):
                        return True
                    logger.info(
                        "[XhsDetector] 页面有头像元素但没有 web_session，"
                        "判为未登录（可能是上次登录的残留 DOM）"
                    )
                    return False
        except Exception as exc:
            logger.debug("[XhsDetector] 头像探测失败：%s", exc)

        # 3. 判不出来就是没登录——不能把"不确定"当成"已登录"，
        #    否则会保存一个没有登录凭证的废连接，后面搜索全部失败还查不出原因。
        return False

    @staticmethod
    async def _has_session_cookie(page) -> bool:
        """检查持久化 profile 里有没有 `web_session`。"""
        try:
            cookies = await page.context.cookies()
            names = {c.get("name") for c in cookies}
            return "web_session" in names
        except Exception:
            return False

    async def extract_account_info(self, page) -> dict:
        """提取小红书账号信息（DOM；接口在未登录/网关拒绝时不可用）。"""
        info = {
            "account_id": None,
            "account_name": None,
            "account_avatar": None,
            "account_url": None,
        }
        try:
            # 头像
            avatar_el = await page.query_selector(
                '.user-info .avatar img, [class*="side-bar"] [class*="avatar"] img'
            )
            if avatar_el:
                info["account_avatar"] = await avatar_el.get_attribute("src") or ""
            # 昵称
            name_el = await page.query_selector(
                '[class*="nickname"], .user-info .name, [class*="user-name"]'
            )
            if name_el:
                info["account_name"] = (await name_el.inner_text()).strip()
        except Exception as exc:
            logger.debug("[XhsDetector] 提取账号信息失败：%s", exc)
        return info
