"""抖音/小红书登录检测器回归测试。

2026-09-26 实测发现并修掉的缺陷：
  两个检测器都用「URL 里含有某个字符串」当作已登录：

      抖音: if "/recommend" in page.url: return True
      小红书: if "/explore" in page.url or "/user/profile" in page.url: return True

  而这些路径**未登录也能访问**，会把游客误判成已登录，从而保存一个
  没有登录凭证的废连接（后续搜索全部失败，且很难查出原因）。

  实测未登录基线：
    抖音 /recommend → 重定向到 /jingxuan；profile/self 接口 status_code=8
    小红书 /explore → 重定向到 /login；页面 [class*=avatar] 命中 0

  这些测试不联网：用假 page 对象钉住「不允许再有 URL 捷径」这一约束。
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# 结构约束：不允许把 URL 字符串当登录判据
# =============================================================================

@pytest.mark.parametrize(
    "module_name,cls_name,bad_url_bits",
    [
        ("app.services.cookies.platforms.douyin", "DouyinDetector", ["/recommend", "/follow"]),
        (
            "app.services.cookies.platforms.xiaohongshu",
            "XhsDetector",
            ["/explore", "/user/profile"],
        ),
    ],
)
def test_detector_has_no_url_shortcut(module_name, cls_name, bad_url_bits):
    """detect() 里不得再用「URL 含 X 就算已登录」的捷径。"""
    from importlib import import_module

    cls = getattr(import_module(module_name), cls_name)
    src = inspect.getsource(cls.detect)

    for bit in bad_url_bits:
        assert f'"{bit}" in' not in src, (
            f"{cls_name}.detect 又出现了 URL 捷径 {bit}——"
            f"该路径未登录也能访问，会把游客误判成已登录"
        )
        assert f"'{bit}' in" not in src


def test_detector_docstring_records_the_correction():
    """两个检测器都要留下"为什么不能这么做"的说明，避免后人改回去。"""
    from app.services.cookies.platforms import douyin, xiaohongshu

    assert "误判" in douyin.__doc__ or "未登录" in douyin.__doc__
    assert "误判" in xiaohongshu.__doc__ or "未登录" in xiaohongshu.__doc__


# =============================================================================
# 行为约束：假 page 下必须判为未登录
# =============================================================================

class _FakePage:
    """最小假 page：可指定 URL、元素命中表和 evaluate 返回。"""

    def __init__(self, url="", selectors=None, eval_result=None):
        self.url = url
        self._selectors = selectors or {}
        self._eval_result = eval_result

    async def query_selector(self, sel):
        return object() if self._selectors.get(sel) else None

    async def query_selector_all(self, sel):
        return [object()] * self._selectors.get(sel, 0)

    async def evaluate(self, _js):
        return self._eval_result

    async def inner_text(self):
        return ""


@pytest.mark.asyncio
async def test_douyin_logout_redirect_url_is_not_logged_in():
    """抖音落在公开推荐页且接口报未登录 → 必须 False。"""
    from app.services.cookies.platforms.douyin import DouyinDetector

    page = _FakePage(url="https://www.douyin.com/jingxuan", eval_result={"code": 8})
    assert await DouyinDetector().detect(page) is False


@pytest.mark.asyncio
async def test_douyin_profile_self_code_8_means_logged_out():
    """profile/self 返回 status_code=8（实测未登录值）→ False。"""
    from app.services.cookies.platforms.douyin import DouyinDetector

    page = _FakePage(url="https://www.douyin.com/", eval_result={"code": 8})
    assert await DouyinDetector().detect(page) is False


@pytest.mark.asyncio
async def test_douyin_avatar_means_logged_in():
    """出现头像 → True（新判据）。

    2026-09-26 实测：抖音对自动化浏览器会把 profile/self 判为风控，
    返回 {"status_code":0,"status_msg":"blocked","user":null}，
    用它当主判据会导致"扫码成功但永远检测不到"。改用 DOM 头像。
    """
    from app.services.cookies.platforms.douyin import DouyinDetector

    page = _FakePage(
        url="https://www.douyin.com/jingxuan",
        selectors={'[class*="avatar"] img': True},
    )
    assert await DouyinDetector().detect(page) is True


@pytest.mark.asyncio
async def test_douyin_login_prompt_means_logged_out():
    """页面出现登录引导 → False。"""
    from app.services.cookies.platforms.douyin import DouyinDetector

    page = _FakePage(
        url="https://www.douyin.com/",
        selectors={'[class*="login"] button': True},
    )
    assert await DouyinDetector().detect(page) is False


@pytest.mark.asyncio
async def test_douyin_blocked_response_does_not_decide_login_state():
    """接口返回 blocked 时**不能**据此判定登录态。

    blocked 是风控结果，不是"未登录"的证据——这正是当初的误判来源。
    """
    from app.services.cookies.platforms.douyin import DouyinDetector

    page = _FakePage(
        url="https://www.douyin.com/jingxuan",
        eval_result={"code": 0, "blocked": True, "uid": None},
    )
    # 没有 DOM 头像、接口被 blocked → 保守判未登录（但不把 blocked 当证据）
    assert await DouyinDetector().detect(page) is False


@pytest.mark.asyncio
async def test_douyin_profile_self_uid_still_works_as_fallback():
    """接口能拿到 uid 时（未被风控）仍可作为兜底判据。"""
    from app.services.cookies.platforms.douyin import DouyinDetector

    page = _FakePage(
        url="https://www.douyin.com/",
        eval_result={"code": 0, "blocked": False, "uid": "12345"},
    )
    assert await DouyinDetector().detect(page) is True


@pytest.mark.asyncio
async def test_douyin_unknown_state_defaults_to_logged_out():
    """接口探不出结果时保守判未登录，不能乐观判已登录。"""
    from app.services.cookies.platforms.douyin import DouyinDetector

    page = _FakePage(url="https://www.douyin.com/", eval_result=None)
    assert await DouyinDetector().detect(page) is False


@pytest.mark.asyncio
async def test_xhs_login_redirect_means_logged_out():
    """小红书被重定向到 /login（实测未登录行为）→ False。"""
    from app.services.cookies.platforms.xiaohongshu import XhsDetector

    page = _FakePage(
        url="https://www.xiaohongshu.com/login?redirectPath=http%3A%2F%2Fwww.xiaohongshu.com%2Fexplore"
    )
    assert await XhsDetector().detect(page) is False


@pytest.mark.asyncio
async def test_xhs_explore_without_avatar_is_logged_out():
    """即使停在 /explore，没有头像也必须判未登录（钉住 URL 捷径已移除）。"""
    from app.services.cookies.platforms.xiaohongshu import XhsDetector

    page = _FakePage(url="https://www.xiaohongshu.com/explore", selectors={})
    assert await XhsDetector().detect(page) is False


@pytest.mark.asyncio
async def test_xhs_avatar_means_logged_in():
    """出现用户头像 → True。"""
    from app.services.cookies.platforms.xiaohongshu import XhsDetector

    page = _FakePage(
        url="https://www.xiaohongshu.com/explore",
        selectors={".user-info .avatar": True},
    )
    assert await XhsDetector().detect(page) is True


# =============================================================================
# 登录等待时长
# =============================================================================

def test_login_timeout_defaults_to_ten_minutes():
    """默认等待要有 10 分钟。

    实测教训：原值 300 秒（5 分钟）对扫码登录太短——用户要开手机 App、
    找扫码入口、确认，中途还可能失败重来。用户在这个窗口内没完成，
    会话被判 failed，而用户以为自己"登录了"，实际什么都没存上。
    """
    from app.services.cookies.patchright_manager import DEFAULT_LOGIN_TIMEOUT

    assert DEFAULT_LOGIN_TIMEOUT >= 600, (
        f"默认登录等待只有 {DEFAULT_LOGIN_TIMEOUT}s，扫码常常不够"
    )


def test_login_timeout_is_configurable_by_env():
    """必须能用环境变量调大——否则慢的用户永远没机会。"""
    import inspect

    from app.services.cookies import patchright_manager

    src = inspect.getsource(patchright_manager)
    assert "YLCRAFT_LOGIN_TIMEOUT_SECONDS" in src, "应支持环境变量覆盖超时"


def test_login_wait_uses_elapsed_time_not_iterations():
    """等待上限必须按**真实流逝时间**算，不能按循环次数。

    循环体里除 sleep(1) 还有一次 detector.detect()（页面查询/接口请求），
    按次数算会让实际等待时间与预期严重不符。
    """
    import inspect

    from app.services.cookies import patchright_manager as pm

    src = inspect.getsource(pm.PatchrightAcquisitionManager._detect_login)
    assert "monotonic" in src, "应按单调时钟计算流逝时间"
    assert "for _ in range(DEFAULT_LOGIN_TIMEOUT)" not in src, (
        "不应再按迭代次数当秒数"
    )


def test_timeout_error_message_is_actionable():
    """超时提示要告诉用户怎么调大，不能只说"超时"。"""
    import inspect

    from app.services.cookies import patchright_manager as pm

    src = inspect.getsource(pm.PatchrightAcquisitionManager._detect_login)
    assert "YLCRAFT_LOGIN_TIMEOUT_SECONDS" in src, "超时提示应给出调大方法"
