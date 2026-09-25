"""事件循环阻塞回归测试。

真机故障（2026-09-26）：uvicorn 服务反复"假死"——端口仍在 Listen，
但所有请求超时（连最简单的 `/api/v1/platforms` 都不响应），
连接堆在 `CloseWait`。同一段代码脱离 uvicorn 单独跑只需约 1 秒。

根因：`PatchrightAcquisitionManager._save_to_db` / `QrcodeAcquisitionManager._save_to_db`
声明为 `async`，内部却直接调用**同步** SQLAlchemy（`SessionLocal()` + `db.commit()`）。
uvicorn 只有一个事件循环，同步阻塞 I/O 会把整个服务卡住。

修法：同步落库体拆成 `_save_to_db_sync`，由 `asyncio.to_thread` 丢到工作线程执行。
本测试把这条约束钉住：同步方法体内不得出现 `await`，异步方法必须委托线程。
"""

from __future__ import annotations

import inspect

import pytest


BLOCKING_PAIRS = [
    (
        "app.services.cookies.patchright_manager",
        "PatchrightAcquisitionManager",
    ),
    (
        "app.services.cookies.qrcode_manager",
        "QrcodeAcquisitionManager",
    ),
]


@pytest.mark.parametrize("module_name,class_name", BLOCKING_PAIRS)
def test_async_save_delegates_to_thread(module_name, class_name):
    """异步 _save_to_db 必须把阻塞落库交给工作线程，不能占着事件循环。"""
    import importlib

    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)

    assert hasattr(cls, "_save_to_db_sync"), (
        f"{class_name} 缺少 _save_to_db_sync：同步落库体必须独立出来"
    )

    source = inspect.getsource(cls._save_to_db)
    assert "to_thread" in source, (
        f"{class_name}._save_to_db 必须用 asyncio.to_thread 执行阻塞落库；"
        "直接在事件循环里跑同步 DB 会卡死整个 uvicorn"
    )


@pytest.mark.parametrize("module_name,class_name", BLOCKING_PAIRS)
def test_sync_body_has_no_await(module_name, class_name):
    """同步体内不得出现 await——它是给工作线程跑的。"""
    import importlib

    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)

    source = inspect.getsource(cls._save_to_db_sync)
    offenders = [
        line.strip() for line in source.splitlines() if "await " in line
    ]
    assert not offenders, f"{class_name}._save_to_db_sync 不应含 await：{offenders}"


@pytest.mark.parametrize("module_name,class_name", BLOCKING_PAIRS)
def test_sync_body_actually_uses_sync_session(module_name, class_name):
    """确认同步体确实是同步 DB 实现（防止未来误改成 async 而测试形同虚设）。"""
    import importlib

    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)

    source = inspect.getsource(cls._save_to_db_sync)
    assert "SessionLocal()" in source, (
        f"{class_name}._save_to_db_sync 应使用同步 SessionLocal"
    )
    assert not inspect.iscoroutinefunction(cls._save_to_db_sync), (
        "_save_to_db_sync 必须是普通同步函数"
    )
