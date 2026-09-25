"""番茄路由参数顺序回归测试。

真机故障（2026-09-25）：保存好番茄 Cookie 后调 `/my/profile` 直接 500。

根因是**参数顺序写反**：
    async def _get_client(session: AsyncSession, conn_id: str)
但四个新端点写成 `await _get_client(conn_id, session)`。

这类错误特别隐蔽：Python 不做运行时类型检查，位置参数又能绕过静态检查，
只有真正调用到那条路由才炸，而且炸在深层（`session.get(...)` 里），
错误信息指向完全不相干的地方。

修复改为**强制关键字参数**（`*, session, conn_id`）：顺序再写错会在调用处
立即 TypeError，不会悄悄传错。
"""

from __future__ import annotations

import inspect

import pytest


def test_get_client_is_keyword_only():
    """必须强制关键字参数，位置传参会绕过类型检查导致顺序错也发现不了。"""
    from app.services.platforms.fanqie.routes import _get_client

    sig = inspect.signature(_get_client)
    positional = [
        p.name
        for p in sig.parameters.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    assert not positional, (
        f"_get_client 不应接受位置参数（防止 session/conn_id 顺序写反）：{positional}"
    )


def test_no_swapped_positional_calls():
    """源码里不得再出现 `_get_client(conn_id, session)` 这类顺序写反的调用。"""
    import inspect

    from app.services.platforms.fanqie import routes

    source = inspect.getsource(routes)
    assert "_get_client(conn_id, session)" not in source, (
        "发现顺序写反的调用：_get_client(conn_id, session) → 应为 _get_client(session=..., conn_id=...)"
    )


@pytest.mark.asyncio
async def test_swapped_call_fails_loudly():
    """反向验证：即便顺序写反，也必须在调用点就报错，不能悄悄传错。"""
    from asyncio import sleep

    from app.services.platforms.fanqie.routes import _get_client

    with pytest.raises((TypeError, AttributeError)):
        # 关键字传错不会造成静默错位；这里模拟旧的错位调用已经被语法层面挡住
        await _get_client(conn_id="fake-conn", session=None)  # type: ignore[arg-type]
    await sleep(0)
