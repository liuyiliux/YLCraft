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
    # 快手**没有客户端**，不该在里面
    assert "kuaishou" not in got, "快手还没实现客户端"


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
    assert url.rstrip("/") != "https://www.kuaishou.com", "不能指向首页（信息流）"


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


def test_kuaishou_detector_uses_cookie_first():
    """**回归**：要用 **cookie** 判据（登录才有 `kuaishou.server.web_st`）。"""
    from app.services.cookies.platforms import kuaishou

    assert "kuaishou.server.web_st" in kuaishou.LOGIN_COOKIES
    src = inspect.getsource(kuaishou.KuaishouDetector.detect)
    assert "cookies(" in src, "应读浏览器 cookie"
    assert "LOGIN_COOKIES" in src


def test_kuaishou_detector_defaults_to_not_logged_in():
    """**回归**：判不出来要返回 False（保守，不猜）。

    宁可不给，也不要存一个"看着登录了但没凭证"的废连接 ——
    那会导致之后所有搜索都失败且极难定位。
    """
    from app.services.cookies.platforms import kuaishou

    src = inspect.getsource(kuaishou.KuaishouDetector.detect)
    # 结尾必须是 return False
    assert src.rstrip().endswith("return False")


def test_kuaishou_detector_queries_site_api():
    """要有**站点接口**兜底（文档要求"问站点自己的接口"）。"""
    from app.services.cookies.platforms import kuaishou

    assert "rest/wd/user/profile" in kuaishou.USER_PROFILE_API
    src = inspect.getsource(kuaishou.KuaishouDetector.detect)
    assert "USER_PROFILE_API" in src


def test_kuaishou_extract_does_not_read_dom_nickname():
    """**回归**：账号信息也不该读 DOM 昵称（那是**别人的**）。"""
    from app.services.cookies.platforms import kuaishou

    src = inspect.getsource(kuaishou.KuaishouDetector.extract_account_info)
    assert "query_selector" not in src, "不该用 DOM 选择器取昵称"
    assert "userId" in src, "userId 从 cookie 取"
