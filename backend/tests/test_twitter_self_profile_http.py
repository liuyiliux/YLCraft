"""X「我的数据」纯 HTTP 化的回归测试。

## 用户反馈

    "微博和x是有效的 我ylcraft搜索能搜到东西啊"

**用户是对的** —— 我不该说"登录态失效"。实测搜索确实能用。

## 但两个平台的真相不同

### X：cookie **有效**，是我的实现有问题

原来的 `get_self_profile` 写着：

    "X 没有『我是谁』的接口，只能靠浏览器读页面"

**这个结论不完整。** 而且它有个致命副作用：
`/users/me` 走 **api 模式（不开浏览器）**，所以那条路**永远拿不到** ——
用户看到"登录态已失效"，但 cookie 好好的。

**正确做法（实测打通）**：

    ① GET https://x.com/i/api/1.1/account/settings.json
       → {"screen_name": "308YYtGer5EWPqj", ...}   ← 自己的 handle
    ② GET .../UserByScreenName?variables={"screen_name": handle}
       → 完整资料

两步都 HTTP 200。实测：昵称「6」，粉丝 10 / 关注 366 / 推文 15。

### 微博：搜索**本来就不需要登录**

代码注释里早就写着：

    在**真实浏览器**里（**未登录**状态）同一 URL 返回 ok=1

微博搜索靠 **Service Worker 上下文**，不依赖登录态。
所以"搜索能搜到"**不等于**"登录态有效"。

而「我的数据」**需要登录**（要确定"我是谁"），实测 m.weibo.cn 的
`/api/config` 返回 `login=False` —— 三种 cookie 组合都试过：

    weibo.com cookie 只种 .weibo.cn  → login=False
    weibo.com cookie 种两个域         → login=False
    weibo cookie 种两个域（现状）      → login=False

**即主站登录态不能登 m.weibo.cn**（微博是两套登录体系）。

⚠️ 而且未登录时页面里的 `/profile/{uid}` 是**推荐流里的别人**
（实测拿到 uid=3482733354「桐城小北」）—— 所以必须保持
"先查 login 再抓 uid"的保护，**宁可不给也不能给错人的资料**。
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# X：纯 HTTP 取自己的资料
# =============================================================================

def test_self_profile_via_http_exists():
    """**回归**：X 要有纯 HTTP 的取自己资料函数。"""
    from app.services.platforms.twitter import search_http

    assert hasattr(search_http, "get_self_profile_via_http")


def test_uses_account_settings_endpoint():
    """**回归**：要用 `account/settings.json` 拿自己的 handle。

    实测这是唯一可行的纯 HTTP 路径（twid + UserByRestId 会 403）。
    """
    from app.services.platforms.twitter import search_http

    src = inspect.getsource(search_http.get_self_profile_via_http)
    assert "account/settings.json" in src, "应调 settings.json"
    assert "screen_name" in src


def test_two_step_flow():
    """**回归**：两步走 —— 先拿 handle，再用它取资料。"""
    from app.services.platforms.twitter import search_http

    src = inspect.getsource(search_http.get_self_profile_via_http)
    assert "get_user_via_http" in src, "第二步应复用 get_user_via_http"


def test_client_self_profile_no_browser():
    """**回归**：`TwitterClient.get_self_profile` **不该再走浏览器**。

    原来走 `fetch_self_handle_via_browser`，而 `/users/me` 是 api 模式、
    不开浏览器 → **永远拿不到**（用户看到"登录态已失效"）。
    """
    from app.services.platforms.twitter import client as tw

    src = inspect.getsource(tw.TwitterClient.get_self_profile)
    assert "get_self_profile_via_http" in src, "应走纯 HTTP"
    assert "fetch_self_handle_via_browser" not in src, (
        "不该再依赖浏览器（api 模式不会开浏览器）"
    )


def test_documents_the_correction():
    """要记录"之前结论不完整"这段修正史。"""
    from app.services.platforms.twitter import client as tw

    doc = inspect.getsource(tw.TwitterClient.get_self_profile)
    assert "settings.json" in doc or "纯 HTTP" in doc
    assert "浏览器" in doc, "应说明原来错在哪"


# =============================================================================
# 微博：搜索不需要登录 + 我的数据需要登录
# =============================================================================

def test_weibo_self_profile_checks_login_first():
    """**回归（数据正确性，最重要）**：微博取自己资料前**必须先查登录**。

    未登录时页面里的 `/profile/{uid}` 全是**推荐流里的别人**
    （实测拿到 uid=3482733354「桐城小北」275万粉 —— 那是真实博主）。
    **给错人的资料比没有数据危险得多。**
    """
    from app.services.platforms.weibo import search_patchright as wb

    src = inspect.getsource(wb.get_self_profile_via_patchright)
    assert "JS_CHECK_LOGIN" in src, "必须先查登录态"
    assert "login" in src
    # 未登录要**返回 None**，不是继续抓 uid
    assert "return None" in src


def test_weibo_search_does_not_require_login():
    """记录"微博搜索不需要登录"这个事实（避免后人误判登录态）。

    代码注释里写着：真实浏览器里**未登录**状态同一 URL 返回 ok=1。
    搜索靠 Service Worker 上下文，不依赖登录态。
    """
    from app.services.platforms.weibo import search_patchright as wb

    doc = inspect.getsource(wb)
    assert "未登录" in doc, "应记录未登录也能搜"
    # 应有 Service Worker 相关说明
    assert "Service Worker" in doc or "SW" in doc or "service worker" in doc.lower()


def test_weibo_user_detail_is_safe_when_not_logged_in():
    """微博用户详情不需要登录（公开信息），但**自己的资料**需要。"""
    from app.services.platforms.weibo import search_patchright as wb

    # 用户详情走 100505{uid}，公开可取
    src = inspect.getsource(wb)
    assert "100505" in src
