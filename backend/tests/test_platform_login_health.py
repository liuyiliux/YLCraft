"""抖音/小红书登录态体检的契约测试。

背景（用户实测反馈，2026-09-26）：
  这两个平台原先只有「选择连接」下拉、**没有体检**，用户存完 Cookie
  完全不知道还能不能用。实测发生过"小红书 Cookie 保存成功但搜索一直失败"
  ——因为存进去的其实是**游客态**值（web_session 仅 38 字符、没有 id_token），
  界面却显示一切正常。

这些测试钉住：体检存在、能识别"游客态 vs 登录态"、且不泄漏 cookie 值。
"""

from __future__ import annotations

import inspect
import json

import pytest


# =============================================================================
# 路由存在
# =============================================================================

@pytest.mark.parametrize(
    "path",
    ["/api/v1/douyin/login-health", "/api/v1/xhs/login-health"],
)
def test_health_route_mounted(path):
    """体检路由必须挂载——对齐 B站 /api/v1/bilibili/login-health。"""
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert path in paths


# =============================================================================
# Cookie 解析（不泄漏值）
# =============================================================================

def test_cookie_names_header_format():
    from app.services.platforms.login_health import cookie_names

    names = cookie_names("a1=xyz; web_session=abc; id_token=tok")
    assert names == ["a1", "web_session", "id_token"]


def test_cookie_names_netscape_format():
    from app.services.platforms.login_health import cookie_names

    raw = (
        "# Netscape HTTP Cookie File\n"
        ".xiaohongshu.com\tTRUE\t/\tTRUE\t0\tweb_session\tabc123\n"
        ".xiaohongshu.com\tTRUE\t/\tTRUE\t0\tid_token\ttok456\n"
    )
    assert cookie_names(raw) == ["web_session", "id_token"]


def test_cookie_names_returns_no_values():
    """函数必须只返回名字——体检结果里绝不能出现 cookie 值。"""
    from app.services.platforms.login_health import cookie_names

    secret = "SUPER_SECRET_VALUE_12345"
    names = cookie_names(f"web_session={secret}")
    assert names == ["web_session"]
    assert secret not in json.dumps(names)


def test_netscape_to_header_filters_domain():
    from app.services.platforms.login_health import netscape_to_header

    raw = (
        ".xiaohongshu.com\tTRUE\t/\tTRUE\t0\tweb_session\tabc\n"
        ".other.com\tTRUE\t/\tTRUE\t0\tleak\tbad\n"
    )
    header = netscape_to_header(raw, "xiaohongshu")
    assert "web_session=abc" in header
    assert "leak" not in header


# =============================================================================
# 游客态识别（这次踩的坑）
# =============================================================================

def test_xhs_health_flags_missing_id_token_as_guest():
    """没有 id_token 时必须提示"可能是游客态"。

    实测：游客态的 web_session 也存在但很短，且没有 id_token。
    当初就是因为只看 web_session 存在与否，把游客 cookie 当成了登录成功。
    """
    from app.services.platforms.xiaohongshu import routes as xhs_routes

    src = inspect.getsource(xhs_routes.xhs_login_health)
    assert "id_token" in src, "必须检查 id_token"
    assert "游客" in src, "应提示游客态这个具体原因"


def test_douyin_health_flags_missing_sessionid():
    """没有 sessionid 时必须提示"通常是游客态"（搜索会 2483）。"""
    from app.services.platforms.douyin import health as dy_health

    src = inspect.getsource(dy_health.douyin_login_health)
    assert "sessionid" in src
    assert "游客" in src
    assert "2483" in src, "应说明后果（搜索返回 2483）"


def test_douyin_session_cookie_names_include_all_variants():
    from app.services.platforms.douyin.health import SESSION_COOKIE_NAMES

    for name in ("sessionid", "sessionid_ss", "sid_tt"):
        assert name in SESSION_COOKIE_NAMES


def test_douyin_health_does_not_rely_on_blocked_endpoint():
    """体检**不能**用 profile/self 判断登录态。

    2026-09-26 实测：抖音对自动化会风控该接口，返回
      {"status_code":0,"status_msg":"blocked","user":null}
    status_code 是 0 但 user 为 null。照它判断会误报"未登录"，
    导致体检结果与实际不符（用户已登录却显示不通过）。
    必须改用浏览器看 DOM。
    """
    from app.services.platforms.douyin import health as dy_health

    src = inspect.getsource(dy_health.douyin_login_health)
    assert "PROFILE_SELF" not in src, "不应再用被风控的 profile/self 作判据"
    assert "fetch_page" in src, "应改用浏览器打开页面看 DOM"
    assert "验证码" in src, "应识别并提示验证码拦截"


def test_douyin_health_uses_headful_mode():
    """必须用有头模式——实测无头会触发验证码页，任何 DOM 判据都会失败。"""
    from app.services.platforms.douyin import health as dy_health

    src = inspect.getsource(dy_health.douyin_login_health)
    assert "headless=False" in src, "无头模式会被抖音甩验证码页"


def test_douyin_health_converts_netscape_cookie():
    """存的 cookie 是 Netscape 格式，必须先转成 `k=v; k2=v2`。

    实测直接喂原文会报
      BrowserContext.add_cookies: Protocol error (Storage.setCookies):
      Invalid cookie fields
    """
    from app.services.platforms.douyin import health as dy_health

    src = inspect.getsource(dy_health.douyin_login_health)
    assert "netscape_to_header" in src, "应先把 Netscape 转成 header 格式"


@pytest.mark.asyncio
async def test_health_reports_not_ready_without_cookie(monkeypatch):
    """没有 Cookie 时 ready 必须是 False，且各项都给出可读原因。"""
    from app.services.platforms.douyin import health as dy_health

    monkeypatch.setattr(dy_health, "get_raw_cookie", lambda _cid: "")
    result = await dy_health.douyin_login_health(conn_id="")
    data = result["data"]
    assert data["ready"] is False
    assert data["checks"]["cookie"]["ok"] is False
    assert data["checks"]["cookie"]["message"]
    assert data["checks"]["login"]["ok"] is False


@pytest.mark.asyncio
async def test_xhs_health_reports_not_ready_without_cookie(monkeypatch):
    from app.services.platforms.xiaohongshu import routes as xhs_routes

    monkeypatch.setattr(xhs_routes, "get_raw_cookie", lambda _cid: "")
    result = await xhs_routes.xhs_login_health(conn_id="")
    data = result["data"]
    assert data["ready"] is False
    assert data["checks"]["cookie"]["ok"] is False


@pytest.mark.asyncio
async def test_xhs_health_flags_guest_cookie_without_network(monkeypatch):
    """只有 web_session、没有 id_token 的游客 cookie：应判为未就绪。

    这里不发真实网络请求：游客态在 id_token 这一项就已经 False，
    且网络探测部分用假的 runtime 短路。
    """
    from app.services.platforms.xiaohongshu import routes as xhs_routes

    guest_cookie = "a1=abc; web_session=shortvalue"

    class _FakeResult:
        url = "https://www.xiaohongshu.com/login?redirectPath=..."
        html = ""

    class _FakeRuntime:
        async def fetch_page(self, *a, **k):
            return _FakeResult()

        async def close(self):
            return None

    monkeypatch.setattr(xhs_routes, "get_raw_cookie", lambda _cid: guest_cookie)
    monkeypatch.setattr(
        "app.services.browser.patchright_runtime.get_patchright_runtime",
        lambda: _FakeRuntime(),
    )

    result = await xhs_routes.xhs_login_health(conn_id="x")
    data = result["data"]
    assert data["checks"]["id_token"]["ok"] is False
    assert "游客" in data["checks"]["id_token"]["message"]
    assert data["checks"]["login"]["ok"] is False, "被重定向到登录页应判未登录"
    assert data["ready"] is False
