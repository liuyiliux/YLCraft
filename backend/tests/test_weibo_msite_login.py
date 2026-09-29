"""微博 m 站登录 + 会话自愈的回归测试。

## ① 微博必须在 **m 站**登录

微博有**两套登录体系**：`weibo.com`（主站）与 `m.weibo.cn`（移动站）。
而我们的搜索/详情/「我的数据」**全走 m 站**
（`m.weibo.cn/api/container/getIndex`）。

实测（重要）：用主站登录态打开 m 站，`/api/config` 返回 **login=False**；
三种 cookie 组合都试过：

    weibo.com cookie 只种 .weibo.cn  → login=False
    weibo.com cookie 种两个域         → login=False
    weibo cookie 种两个域（现状）      → login=False

**换到 m 站登录入口后成功**：

    登录 URL 改为 `https://m.weibo.cn/login`
    → 跳 `passport.weibo.com/sso/signin?entry=wapsso`（无线 SSO）
    → 扫码登录后 `.weibo.cn` 域多了 **ALF / SCF / SSOLoginState**（登录凭证）

    实测结果：`想见雪-` 粉丝8 关注11 微博237 ✅

## ⚠️ 排查时的一个弯路（值得记）

用户说"微博和 x 是有效的，我搜索能搜到东西啊"——**用户是对的**。

微博**搜索靠 Service Worker 上下文，本来就不需要登录**
（代码注释里早就写着"真实浏览器里未登录状态同一 URL 返回 ok=1"）。

**"搜索能用" ≠ "登录态有效"** —— 我把这两件事混为一谈了。

## ② 会话池要能识别"已失效的会话"

实测：杀掉 chrome 后，会话池里**还留着那个会话**，下次仍复用：

    Page.evaluate: Target page, context or browser has been closed

**连搜两次都失败**，而重建会话就恢复。
用户关掉浏览器窗口后第一次操作必然踩这个坑。

修法：`PooledSession.alive()` 检查 page/ctx 的 `is_closed()`，
失效就摘掉让调用方重建。
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# ① 微博 m 站登录
# =============================================================================

def test_weibo_login_url_is_m_site():
    """**回归**：微博登录 URL 必须是 **m 站**入口。

    主站的登录态在 m 站无效（实测 `/api/config` 返回 login=False），
    而我们的所有微博能力都走 m 站。
    """
    from app.services.cookies.base import get_login_url

    url = get_login_url("weibo")
    assert "m.weibo.cn" in url or "passport.weibo.com/sso" in url, (
        f"微博登录 URL 应是 m 站入口，实际 {url!r}"
    )
    assert url != "https://weibo.com", "不该用主站登录页"
    assert "/login" in url or "sso" in url


def test_weibo_domains_include_m_site():
    """**回归**：微博 cookie 域必须包含 `.weibo.cn`。

    m 站的登录态（`SUB`/`SSOLoginState`）种在 `.weibo.cn` ——
    只存 `.weibo.com` 会漏掉它。
    """
    from app.services.cookies.base import PLATFORM_DOMAINS

    doms = PLATFORM_DOMAINS["weibo"]
    assert "weibo.cn" in doms, "应包含 m 站域"
    assert "weibo.com" in doms


def test_weibo_documents_two_login_systems():
    """要记录"两套登录体系"这件事 —— 避免后人改回主站。"""
    from app.services.cookies import base as cookie_base

    src = inspect.getsource(cookie_base)
    assert "两套登录体系" in src or "m 站" in src
    # 要写明为什么必须用 m 站
    assert "login=False" in src or "移动站" in src


# =============================================================================
# ② 会话池自愈
# =============================================================================

def test_pooled_session_has_alive_check():
    """**回归**：`PooledSession` 要有 `alive()`。"""
    from app.services.platforms.session_pool import PooledSession

    assert hasattr(PooledSession, "alive")


def test_alive_checks_is_closed():
    """**回归**：要查 page/ctx 的 `is_closed()`。

    用户关掉浏览器后，池里还留着会话，复用就报
    `Target page, context or browser has been closed`。
    """
    from app.services.platforms.session_pool import PooledSession

    src = inspect.getsource(PooledSession.alive)
    assert "is_closed" in src


def test_get_drops_dead_session():
    """**回归**：`get()` 要摘掉已失效的会话（让调用方重建）。"""
    from app.services.platforms.session_pool import SessionPool

    src = inspect.getsource(SessionPool.get)
    assert "alive()" in src, "get 里要检查会话是否还活着"
    assert "del self._sessions[key]" in src


class _FakePage:
    def __init__(self, closed: bool):
        self._closed = closed

    def is_closed(self):
        return self._closed


class _FakeCtx:
    def __init__(self, closed: bool = False):
        self._closed = closed

    def is_closed(self):
        return self._closed


def test_alive_true_when_open():
    from app.services.platforms.session_pool import PooledSession

    s = PooledSession(ctx=_FakeCtx(), page=_FakePage(False))
    assert s.alive() is True


def test_alive_false_when_page_closed():
    from app.services.platforms.session_pool import PooledSession

    s = PooledSession(ctx=_FakeCtx(), page=_FakePage(True))
    assert s.alive() is False


def test_alive_false_when_ctx_closed():
    from app.services.platforms.session_pool import PooledSession

    s = PooledSession(ctx=_FakeCtx(True), page=_FakePage(False))
    assert s.alive() is False


def test_alive_false_on_exception():
    """检查过程报错 → 当作不可用（重建更安全）。"""
    from app.services.platforms.session_pool import PooledSession

    class _Boom:
        def is_closed(self):
            raise RuntimeError("boom")

    s = PooledSession(ctx=_Boom(), page=_Boom())
    assert s.alive() is False


def test_get_returns_none_for_dead_session():
    """端到端：失效会话不该被返回。"""
    from app.services.platforms.session_pool import PooledSession, SessionPool

    pool = SessionPool()
    s = PooledSession(ctx=_FakeCtx(), page=_FakePage(True))
    pool.put("k", s)
    assert pool.get("k") is None, "失效会话应返回 None（调用方会重建）"


def test_get_returns_live_session():
    """活着的会话要正常复用（别把自愈写成"永远重建"）。"""
    from app.services.platforms.session_pool import PooledSession, SessionPool

    pool = SessionPool()
    s = PooledSession(ctx=_FakeCtx(), page=_FakePage(False))
    pool.put("k", s)
    got = pool.get("k")
    assert got is s, "活着的会话应被复用"
    assert pool.reused >= 1
