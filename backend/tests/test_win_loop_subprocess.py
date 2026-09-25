"""回归测试：uvicorn 事件循环必须能创建子进程（Patchright 依赖它）。

真机故障（2026-09-25）：账号中心点「启动浏览器」无反应，后端报
`NotImplementedError` at `asyncio.create_subprocess_exec`。

根因是 uvicorn 的循环选择逻辑：

    def asyncio_loop_factory(use_subprocess=False):
        if sys.platform == "win32" and not use_subprocess:
            return asyncio.ProactorEventLoop
        return asyncio.SelectorEventLoop

`--reload` 会让 `use_subprocess=True`，于是退回 `SelectorEventLoop`；而 Windows 的
Selector 循环**不实现** `subprocess_exec`，Patchright 启不了 Chromium。

我们通过 `--loop app.core.win_loop:proactor_loop_factory` 覆盖掉这个选择。
这里把契约钉住：**无论 use_subprocess 传什么，都必须给出能建子进程的循环**。
"""

from __future__ import annotations

import asyncio
import sys

import pytest


def test_factory_returns_proactor_even_when_use_subprocess_true():
    """这正是 --reload 的场景：use_subprocess=True 时仍必须支持子进程。

    若这里退化成 SelectorEventLoop，故障就会复现。
    """
    from app.core.win_loop import proactor_loop_factory

    loop_cls = proactor_loop_factory(use_subprocess=True)

    if sys.platform == "win32":
        assert loop_cls is asyncio.ProactorEventLoop


def test_factory_result_actually_supports_subprocess_exec():
    """不能只比类名——要确认实例真有 subprocess_exec。"""
    from app.core.win_loop import proactor_loop_factory

    loop = proactor_loop_factory(use_subprocess=True)()
    try:
        assert hasattr(loop, "subprocess_exec"), (
            "该事件循环不支持 subprocess_exec，Patchright 无法启动浏览器"
        )
    finally:
        loop.close()


def test_factory_accepts_uvicorn_call_signature():
    """uvicorn 以 `factory(use_subprocess=...)` 方式调用，签名必须兼容。"""
    from app.core.win_loop import proactor_loop_factory

    # 位置参数与关键字两种调用都要能跑
    assert proactor_loop_factory(True) is not None
    assert proactor_loop_factory(use_subprocess=False) is not None
    assert proactor_loop_factory() is not None


@pytest.mark.asyncio
async def test_start_session_raises_instead_of_silently_succeeding(monkeypatch):
    """start_session 失败必须抛错，不能"假装成功"。

    修复前它只写 session.status=FAILED 就照常 return session_id，
    导致接口永远返回 success=true——浏览器没起来用户也看不出来。
    """
    from app.services.cookies.patchright_manager import PatchrightAcquisitionManager

    manager = PatchrightAcquisitionManager()

    async def boom(headless=False):
        raise NotImplementedError()

    monkeypatch.setattr(manager, "ensure_browser", boom)

    with pytest.raises(NotImplementedError):
        await manager.start_session(platform="fanqie", headless=True)
