"""小红书"不弹浏览器"的回归测试（2026-09-28 用户反馈）。

## 用户症状

    "我先搜索打开了浏览器，然后显示没登录，我扫码登录了，关了浏览器，
     重新搜索就不弹浏览器了。"

## 根因（实测确认）

持久化 profile 里**残留上次的登录态**，于是：

    启动浏览器（4 秒）
    检测器第一秒就判"已登录"（页面进 /explore + 有 .reds-avatar）
    → 立刻保存 Cookie → page.context.close()
    → **窗口只存在 4 秒**，用户来不及扫码

日志实证：

    18:38:01 启动持久化 profile
    18:38:05 Session success, connector_id=...
    （中间没有任何用户交互时间）

## 修法

1. **检测器加 cookie 检查**：有头像元素但**没有 web_session** → 判未登录
   （挡掉"只有残留 DOM、没有凭证"的情况）
2. **保存后保留窗口**：`LOGIN_CONFIRM_SECONDS`（默认 45s）
   让想换账号的用户有时间扫码覆盖；不操作则到点自动关

## 试过但行不通的方案（重要，避免后人重走）

我一度改成"调 `user/me` 验证登录态真的可用"，但实测：

    user/me       → 500 create invoker failed, service: jarvis-gateway-default
    config        → 500 同上
    homefeed      → 500 同上
    user_selfinfo → 406（edith 域跨域）

**小红书网关对这些接口一律拒绝，与登录态无关** ——
所以**没有可用的 HTTP 判据**，只能靠 DOM + cookie 组合。

（本模块顶部的历史注释也早就记过"user/me 不能作为判据"。）
"""

from __future__ import annotations

import inspect

import pytest


def test_detector_checks_session_cookie():
    """**回归**：有头像元素但没 `web_session` 要判未登录。

    否则"上次登录残留的 DOM"会被误判成已登录 → 立刻关窗口 →
    用户来不及扫码（就是用户反馈的那个症状）。
    """
    from app.services.cookies.platforms.xiaohongshu import XhsDetector

    src = inspect.getsource(XhsDetector.detect)
    assert "_has_session_cookie" in src, "应检查 web_session"

    cookie_src = inspect.getsource(XhsDetector._has_session_cookie)
    assert "web_session" in cookie_src

    # 先看 URL 是否 /login
    assert "/login" in src


def test_detector_does_not_use_gateway_blocked_apis():
    """**回归**：不要用 `user/me` 之类做登录判据。

    实测这些接口一律 500（网关拒绝），**与登录态无关** ——
    据此判断会永远返回 False（连真登录也判成未登录）。

    注：只检查**代码**，模块 docstring 里会提到这些接口（说明为什么不用）。
    """
    from app.services.cookies.platforms.xiaohongshu import XhsDetector

    code = inspect.getsource(XhsDetector.detect)
    first = code.find('"""')
    if first != -1:
        second = code.find('"""', first + 3)
        if second != -1:
            code = code[:first] + code[second + 3:]

    for blocked in ("user/me", "v2/user/me"):
        assert blocked not in code, f"不应依赖 {blocked}（实测网关拒绝）"


def test_detector_documents_the_history():
    """要记录"接口判据行不通"这个结论，避免后人重走。"""
    from app.services.cookies.platforms.xiaohongshu import XhsDetector

    doc = inspect.getsource(XhsDetector.detect)
    assert "jarvis-gateway" in doc or "500" in doc, "应记录接口被网关拒绝"


def test_login_confirm_window_exists():
    """**回归**：保存 Cookie 后要**保留窗口一段时间**。

    原实现保存后立刻 `page.context.close()` —— 实测窗口只存在 4 秒，
    用户根本来不及扫码换账号。
    """
    from app.services.cookies import patchright_manager as pm

    assert hasattr(pm, "LOGIN_CONFIRM_SECONDS"), "应有确认窗口期配置"
    assert pm.LOGIN_CONFIRM_SECONDS > 0, "默认应大于 0"

    src = inspect.getsource(pm.PatchrightAcquisitionManager._detect_login)
    i_confirm = src.find("LOGIN_CONFIRM_SECONDS")
    i_close = src.find("page.context.close()")
    assert i_confirm != -1, "应使用确认窗口期"
    assert i_close != -1, "仍要关闭"
    assert i_confirm < i_close, "必须先等待再关闭（否则用户来不及扫码）"


def test_confirm_window_is_configurable():
    """要能通过环境变量调整（扫码慢的用户可以调大）。"""
    from app.services.cookies import patchright_manager as pm

    src = inspect.getsource(pm)
    assert "YLCRAFT_LOGIN_CONFIRM_SECONDS" in src, "应支持环境变量"


def test_detect_login_documents_symptom():
    """要记录用户的原始症状，便于后人理解为什么有这个窗口期。"""
    from app.services.cookies import patchright_manager as pm

    src = inspect.getsource(pm.PatchrightAcquisitionManager._detect_login)
    assert "来不及" in src or "不弹浏览器" in src, "应记录症状"
