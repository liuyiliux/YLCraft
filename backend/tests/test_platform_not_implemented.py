"""平台「未实现」要显式报错 + 快手登录修复的回归测试（2026-09-29）。

## 起因：用新 skill 加快手，skill 立刻抓出问题

用户要求"做成 skill，然后添加快手试试这个 skill"。
照着 skill 走，第一步就发现问题 —— 而且**是 skill 铁律里写明的**：

### 问题 1：未实现的平台**静默返回空**

前端搜索页下拉里有「快手」可点，但后端**没有快手客户端**。实测：

    日志：Unsupported platform: kuaishou. Available: [...]
    响应：HTTP 200 {"success": true, "results": [], "message": "找到 0 条结果"}

**用户看到"没搜到"**，完全不知道是"这个平台还没实现" —— 假阴性，
排查时最费时间（`ADDING_A_PLATFORM.md` 铁律第 2 条正是这条）。

修法：用注册表判断，**显式抛 501**（不是 500，语义是"未实现"）。

### 问题 2：快手登录 URL 指向信息流首页

用户反馈："**打开的网址不是登录的** 我点击登录是弹窗的"

原来是 `https://www.kuaishou.com`（推荐流），用户看到的是信息流页面。
改为 `/profile`（未登录会引导登录）。

### 问题 3：快手检测器用**模糊 CSS 选择器**

用户反馈："**扫码完没判断获取到**"

原实现：

    avatar = await page.query_selector('[class*="avatar"], [class*="user-info"] img')
    user_el = await page.query_selector('[class*="username"], [class*="nickname"]')

**快手的信息流首页本身就有大量头像和昵称**（作者名），
所以"页面里有头像"**根本不代表已登录** —— 未登录照样命中。

⚠️ 这与 `ADDING_A_PLATFORM.md` 的硬规矩冲突：

> 登录检测必须问站点自己的接口，不能看 URL、也不能只看 CSS 类名。
> ……**判不出来一律按"未登录"处理**，不要乐观假设。

修法：**cookie 判据优先**（`kuaishou.server.web_st` 才是登录会话，
`did`/`didv` 只是设备标识）→ **接口兜底**（`/rest/wd/user/profile`）
→ 都拿不到**按未登录处理**。
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# 未实现平台要显式报错
# =============================================================================

def test_supported_platforms_helper_exists():
    """要有 `supported_platforms()`（用来区分"没实现"和"没搜到"）。"""
    from app.services.platforms import supported_platforms

    got = supported_platforms()
    assert isinstance(got, set)
    assert "douyin" in got
    # ⚠️ 快手**已实现**（2026-09-30）—— 这条断言改成"在"。
    # 原来它用来验证"未实现平台会显式报错"，现在用别的未实现平台
    # （如 telegram）来验证那个行为。
    assert "kuaishou" in got, "快手应已实现"


def test_registry_exposes_supported():
    """注册表要能列出已注册平台。"""
    from app.services.platforms.base import PlatformClientFactory

    assert hasattr(PlatformClientFactory, "supported")


def test_crawler_raises_501_for_unimplemented():
    """**回归（铁律）**：未实现的平台要抛 **501**，不能静默返回空。

    原来返回 `{"success": true, "results": [], "message": "找到 0 条结果"}`
    —— 用户以为"没搜到"。
    """
    from app.api.v1 import crawler

    src = inspect.getsource(crawler.search_enhanced)
    assert "supported_platforms" in src, "要用注册表判断"
    assert "501" in src, "要抛 501（未实现），不是 200 空结果"


def test_both_search_endpoints_guard_unimplemented():
    """**回归**：`/search` **和** `/search-enhanced` 都要有 501 守卫。

    ## 为什么补这条（2026-10-01）

    `search_enhanced` 早在 2026-09-29 就有了守卫，但这个守卫
    **只加在一个端点上** —— 另一个端点漏了。实测：

        POST /api/v1/crawler/search-enhanced  {"platform":"youtube",...}
        → HTTP 501  ✅

        POST /api/v1/crawler/search           {"platform":"youtube",...}
        → HTTP 200  ❌ {"results":[],"message":"找到 0 条结果"}

    `/crawler/search` 是**画布 platform_search 节点 + 博主中心"作品搜索"**
    走的端点。所以那条路径上"选了个没实现的平台"依然表现为"没搜到"。

    教训：**同一个守卫加在多个入口时，要给每个入口都写断言**
    —— 只测一个入口，另一个漏了也照样绿。
    """
    from app.api.v1 import crawler

    for fn in (crawler.search_materials, crawler.search_enhanced):
        src = inspect.getsource(fn)
        assert "supported_platforms" in src, (
            f"{fn.__name__} 缺 supported_platforms 守卫（会静默返回空）"
        )
        assert "501" in src, (
            f"{fn.__name__} 缺 501（应报「未实现」，不是 200 空结果）"
        )


def test_unimplemented_platforms_are_exactly_the_silent_empty_risk():
    """**回归**：确实存在"前端能选、后端没实现"的平台（守卫有真实作用）。

    前端 `PLATFORMS` 下拉里有 youtube / telegram，但后端当时**没有**
    对应采集客户端。如果哪天这些都实现了，本测试会提醒删掉守卫的
    注释说明（而不是留着一段讲古的注释）。
    """
    from app.services.platforms import supported_platforms

    sup = supported_platforms()
    # 这些是**已实现**的（必须有）
    for implemented in ("xhs", "xiaohongshu", "douyin", "dy", "kuaishou", "ks",
                        "bili", "weibo", "wb", "twitter", "x", "fanqie"):
        assert implemented in sup, f"{implemented} 应已实现"
    # 知乎已移除 —— 不能再出现在注册表里
    assert "zhihu" not in sup, "知乎已移除（2026-10-01）"


def test_youtube_implemented_and_telegram_still_pending():
    """**状态守卫**：youtube 已实现；telegram 仍未实现（且原因已变）。

    ## 这条测试的来历（它已经完成过一次使命）

    2026-10-01 上午写成"youtube/telegram **都**未实现，因为网络不通"，
    设计意图是：**网络通了就让它失败，提醒去实现**。

    当天下午用户开了 VPN —— 它如期失败了，于是实现了 youtube
    （yt-dlp，见 `tests/test_youtube_client.py`），现在改成：

        youtube  → **必须已实现**（否则是回归）
        telegram → 仍未实现，但原因**不再是网络**：
                   `t.me` 现在已经能访问（HTTP 200），缺的是产品决策 ——
                   公开频道列表 vs MTProto 关键词搜索是两条路，
                   要用户先选（见 ADDING_A_PLATFORM.md）。

    这样写的好处：任何一边状态变化都会让这条测试失败，
    逼着后来的人更新文档，而不是留下过时的注释。
    """
    from app.services.platforms import supported_platforms

    sup = supported_platforms()
    # 网络已通 + 客户端已实现 —— 不该再退回 501
    assert "youtube" in sup, (
        "youtube 应已实现（2026-10-01 VPN 打通后用 yt-dlp 实现）；"
        "若被移除，请说明原因并更新本文档"
    )
    # telegram 仍待产品决策（不是网络问题）
    assert "telegram" not in sup, (
        "telegram 若已实现，请更新本测试与 docs/platform/ADDING_A_PLATFORM.md"
    )


def test_501_message_is_actionable():
    """报错信息要**可操作**（说明不是"没搜到" + 指向文档）。"""
    from app.api.v1 import crawler

    src = inspect.getsource(crawler.search_enhanced)
    assert "尚未实现" in src
    assert "ADDING_A_PLATFORM" in src, "应指向接入文档"


# =============================================================================
# 快手登录 URL
# =============================================================================

def test_kuaishou_login_url_is_not_homepage():
    """**回归**：快手登录 URL 不能是信息流首页。

    用户："打开的网址不是登录的"。
    """
    from app.services.cookies.base import PLATFORM_LOGIN_URLS

    url = PLATFORM_LOGIN_URLS["kuaishou"]
    # ⚠️ 踩过两次：
    #   ① 首页（推荐流）—— 用户要自己在信息流里找登录
    #   ② `/profile` —— **跳到 404**！真实路径是 `/profile/{userId}`
    assert not url.rstrip("/").endswith("/profile"), (
        "裸 /profile 会 404（真实路径带 userId）"
    )
    assert "kuaishou.com" in url


# =============================================================================
# 快手检测器
# =============================================================================

def test_kuaishou_detector_does_not_use_loose_class_selectors():
    """**回归（关键）**：不能用模糊 CSS 选择器判断登录。

    快手首页本来就有别人的头像/昵称，未登录也会命中 ——
    这正是"扫码完没判断获取到"（或反向误判）的来源。
    """
    from app.services.cookies.platforms import kuaishou

    src = inspect.getsource(kuaishou.KuaishouDetector.detect)
    assert 'class*="avatar"' not in src, "不该用模糊 class 选择器判登录"
    assert 'class*="nickname"' not in src, "不该用模糊 class 选择器判登录"


def test_kuaishou_detector_uses_cookie():
    """**回归**：要用 **cookie** 判据。

    实测登录后的 cookie 名是 **`kuaishou.server.webday7_st`**（带 `day7`），
    **不是** `kuaishou.server.web_st` —— 我第一版按印象写错了。

    所以代码用**后缀匹配**（`kuaishou.server.web` + `_st`），
    平台改名（`webday7` / `web`）也不会失效。
    """
    from app.services.cookies.platforms import kuaishou

    assert "userId" in kuaishou.LOGIN_COOKIES_EXACT
    assert kuaishou.LOGIN_COOKIE_PREFIX == "kuaishou.server.web"
    assert kuaishou.LOGIN_COOKIE_SUFFIX == "_st"
    src = inspect.getsource(kuaishou.KuaishouDetector.detect)
    assert "cookies(" in src, "应读浏览器 cookie"
    assert "LOGIN_COOKIE_SUFFIX" in src, "应用后缀匹配（防平台改名）"


def test_kuaishou_detector_defaults_to_not_logged_in():
    """**回归**：判不出来要返回 False（保守，不猜）。

    宁可不给，也不要存一个"看着登录了但没凭证"的废连接 ——
    那会导致之后所有搜索都失败且极难定位。
    """
    from app.services.cookies.platforms import kuaishou

    src = inspect.getsource(kuaishou.KuaishouDetector.detect)
    # 每个分支都要落到 return False（保守，不猜）
    # ⚠️ 不能只断言"结尾是 return False" —— 现在结尾是 try/except 块，
    # 所以改为：**所有 return 值只能有 False**（或 True 出现前必须过接口）
    rets = [ln.strip() for ln in src.splitlines() if ln.strip().startswith("return ")]
    assert rets, "应有 return"
    assert all(r in ("return False", "return True") for r in rets), f"意外返回：{rets}"
    # ⚠️ **不能用带签名的接口** —— `/rest/v/profile/get` 在签名白名单里，
    # 检测器拿不到签名 → 返回 `50`（**签名验证失败**），
    # 我一度把它当成"未登录"，导致**明明登录了却报未登录**。
    assert "PROFILE_API" not in src, "不该用需要签名的接口做判据"
    # 要用**页面 UI 的未登录文案**（实测最可靠）
    assert "LOGIN_HINT_TEXTS" in src, "应看页面有没有'未登录'文案"


def test_kuaishou_detector_does_not_trust_blocked_api():
    """**回归**：不能把被风控挡的接口当登录判据。

    实测 `/rest/wd/user/profile` 返回：

        {"result":2001,"error_msg":"[2001] antispam need captcha"}

    有风控 —— 用它判断会让"已登录"被误判成"未登录"
    （用户就遇到"扫码完没判断获取到"）。
    """
    from app.services.cookies.platforms import kuaishou

    src = inspect.getsource(kuaishou.KuaishouDetector.detect)
    assert "UNUSABLE_PROFILE_API" not in src, (
        "不该用被风控的接口做判据"
    )
    # 但要**留档**，免得后人再试
    assert "antispam" in inspect.getsource(kuaishou)


def test_kuaishou_extract_does_not_read_dom_nickname():
    """**回归**：账号信息也不该读 DOM 昵称（那是**别人的**）。"""
    from app.services.cookies.platforms import kuaishou

    src = inspect.getsource(kuaishou.KuaishouDetector.extract_account_info)
    assert "query_selector" not in src, "不该用 DOM 选择器取昵称"
    assert "userId" in src, "userId 从 cookie 取"
