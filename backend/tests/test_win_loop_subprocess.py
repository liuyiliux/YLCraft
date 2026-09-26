"""回归测试：uvicorn 事件循环必须能创建子进程（Patchright 依赖它）。

真机故障（2026-09-25）：账号中心点「启动浏览器」后没反应，后端报
`NotImplementedError` at `asyncio.create_subprocess_exec`。

根因是 uvicorn 的循环选择逻辑：

    def asyncio_loop_factory(use_subprocess=False):
        if sys.platform == "win32" and not use_subprocess:
            return asyncio.ProactorEventLoop
        return asyncio.SelectorEventLoop

`--reload` 会让 `use_subprocess=True`，于是退回 `SelectorEventLoop`；而 Windows 的
Selector 循环**不实现** `subprocess_exec`，Patchright 启不了 Chromium。

我们通过 `--loop app.core.win_loop:new_loop` 覆盖掉这个选择。

**签名契约（踩过两次坑，必须钉死）**：指向自定义 dotted path 时，uvicorn 不会传
`use_subprocess`，而是把解析到的对象**原样返回**，之后**零参调用**它并期望拿到
**循环实例**：

    # uvicorn/config.py 自定义分支
    return import_from_string(self.loop)
    # uvicorn/_compat.py
    loop = loop_factory()      # 必须是实例

所以：① 不能返回「工厂的工厂」（uvicorn 会把函数当循环用）；
② 不能直接返回 `asyncio.ProactorEventLoop` —— Python 3.10/Windows 下
**调用该类的返回结果是类本身而非实例**，会报
`BaseProactorEventLoop.close() missing 1 required positional argument: 'self'`。
"""

from __future__ import annotations

import asyncio
import sys

import pytest


def test_loop_factory_takes_no_arguments():
    """自定义 loop 路径下 uvicorn 是零参调用，签名必须无必填参数。"""
    import inspect

    from app.core.win_loop import new_loop

    sig = inspect.signature(new_loop)
    required = [
        p
        for p in sig.parameters.values()
        if p.default is inspect.Parameter.empty
        and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
    ]
    assert not required, f"new_loop 不应有必填参数（uvicorn 零参调用）：{required}"


def test_loop_factory_returns_a_loop_instance():
    """必须返回**实例**，不是类、不是函数。

    这是实际踩过的坑：返回类时 uvicorn 把类当实例用，
    报 `close() missing 1 required positional argument: 'self'`，进程直接崩。
    """
    from app.core.win_loop import new_loop

    loop = new_loop()
    try:
        assert isinstance(loop, asyncio.AbstractEventLoop), (
            f"必须返回循环实例，实际是 {type(loop).__name__}"
        )
    finally:
        loop.close()


def test_loop_supports_subprocess_exec():
    """核心诉求：该循环必须能创建子进程，否则 Patchright 起不来。"""
    from app.core.win_loop import new_loop

    loop = new_loop()
    try:
        assert hasattr(loop, "subprocess_exec"), (
            "该事件循环不支持 subprocess_exec，Patchright 无法启动浏览器"
        )
        if sys.platform == "win32":
            assert isinstance(loop, asyncio.ProactorEventLoop)
    finally:
        loop.close()


def test_loop_supports_uvicorn_post_construction_calls():
    """uvicorn 拿到循环后会立刻调 set_debug / shutdown_asyncgens / close。"""
    from app.core.win_loop import new_loop

    loop = new_loop()
    loop.set_debug(False)
    loop.run_until_complete(loop.shutdown_asyncgens())
    loop.close()


def test_uvicorn_resolved_factory_yields_instance():
    """端到端对齐 uvicorn 的真实解析方式（自定义 dotted path 分支）。"""
    from uvicorn.config import Config

    config = Config("app.main:app", loop="app.core.win_loop:new_loop")
    factory = config.get_loop_factory()
    assert factory is not None

    loop = factory()  # uvicorn/_compat.py 就是这么调的
    try:
        assert isinstance(loop, asyncio.AbstractEventLoop)
        assert hasattr(loop, "subprocess_exec")
    finally:
        loop.close()


@pytest.mark.asyncio
async def test_start_session_raises_instead_of_silently_succeeding(monkeypatch):
    """start_session 失败必须抛错，不能"假装成功"。

    修复前它只写 session.status=FAILED 就照常 return session_id，
    导致接口永远返回 success=true——浏览器没起来用户也看不出来。

    注意：现在默认走**持久化 profile**（persistent_profile），
    所以失败点在 `_runtime.new_context` 而不是 `ensure_browser`。
    这里把 new_context 打桩抛错，验证异常照样穿出去。
    """
    from app.services.cookies.patchright_manager import PatchrightAcquisitionManager

    manager = PatchrightAcquisitionManager()

    async def boom(*args, **kwargs):
        raise NotImplementedError()

    monkeypatch.setattr(manager._runtime, "new_context", boom)

    with pytest.raises(NotImplementedError):
        await manager.start_session(platform="fanqie", headless=True)


@pytest.mark.asyncio
async def test_start_session_raises_when_browser_launch_fails_non_persistent(monkeypatch):
    """非持久化模式下（关掉开关），ensure_browser 失败同样必须抛出。"""
    from app.services.cookies.patchright_manager import PatchrightAcquisitionManager

    manager = PatchrightAcquisitionManager()
    monkeypatch.setenv("YLCRAFT_BROWSER_PERSISTENT", "0")

    async def boom(headless=False):
        raise NotImplementedError()

    monkeypatch.setattr(manager, "ensure_browser", boom)

    with pytest.raises(NotImplementedError):
        await manager.start_session(platform="fanqie", headless=True)


def test_start_bat_wires_the_loop_factory():
    """启动脚本必须带上 --loop，否则用户按默认方式启动仍会踩坑。"""
    from pathlib import Path

    start_bat = Path(__file__).resolve().parents[2] / "start.bat"
    if not start_bat.exists():
        pytest.skip("start.bat not present")

    content = start_bat.read_text(encoding="utf-8", errors="ignore")
    assert "--loop app.core.win_loop:new_loop" in content, (
        "start.bat 的后端启动命令缺少 --loop app.core.win_loop:new_loop"
    )


def test_login_navigation_does_not_require_networkidle():
    """登录页导航不得依赖 networkidle。

    真机故障（2026-09-25）：番茄作家后台有常驻轮询，网络永不空闲，
    `wait_until="networkidle"` 必然超时（Page.goto: Timeout 30000ms exceeded），
    并把整个会话判失败——尽管登录页早已打开、二维码都能扫。
    """
    import inspect

    from app.services.cookies import patchright_manager as pm

    source = inspect.getsource(pm)
    # 只看真实调用，别误伤解释性注释里对 networkidle 的说明
    assert 'wait_until="networkidle"' not in source, (
        "登录页导航不应等 networkidle（有常驻轮询的站点必然超时）"
    )
    assert "wait_until='networkidle'" not in source, (
        "登录页导航不应等 networkidle（有常驻轮询的站点必然超时）"
    )
    assert "_goto_login_page" in source, "应通过 _goto_login_page 统一处理登录页导航"
    # 且 goto 必须显式用 domcontentloaded
    assert 'wait_until="domcontentloaded"' in source, (
        "登录页导航应使用 domcontentloaded"
    )


@pytest.mark.asyncio
async def test_goto_login_page_tolerates_navigation_timeout():
    """导航超时只告警，不应中断会话——用户要的是打开页面等他登录。"""

    from app.services.cookies.patchright_manager import PatchrightAcquisitionManager

    class FakePage:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def goto(self, url, **kwargs):
            self.calls.append({"url": url, **kwargs})
            raise TimeoutError("Page.goto: Timeout 30000ms exceeded")

    manager = PatchrightAcquisitionManager()
    page = FakePage()

    # 不应抛出
    await manager._goto_login_page(page, "https://fanqienovel.com/main/writer/book-manage")

    assert page.calls, "应真的尝试过导航"
    assert page.calls[0]["wait_until"] != "networkidle", "不应使用 networkidle"
