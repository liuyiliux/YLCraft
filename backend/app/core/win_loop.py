"""Uvicorn loop factory that always returns a Proactor event loop on Windows.

Why this exists
---------------
Patchright launches Chromium as a **subprocess**. On Windows only
``ProactorEventLoop`` implements ``subprocess_exec``; ``SelectorEventLoop``
raises ``NotImplementedError``. Uvicorn picks the loop via
``uvicorn.loops.asyncio.asyncio_loop_factory(use_subprocess=...)``:

    if sys.platform == "win32" and not use_subprocess:
        return asyncio.ProactorEventLoop
    return asyncio.SelectorEventLoop

``use_subprocess`` is true whenever uvicorn runs with ``--reload`` (the reloader
supervises a child process). So the common dev command
``uvicorn app.main:app --reload --port 8000`` silently switches to
``SelectorEventLoop``, and every browser-based Cookie acquisition dies with
``NotImplementedError`` — while still reporting ``success: true`` to the caller.

Usage:
    uvicorn app.main:app --reload --port 8000 \\
        --loop app.core.win_loop:new_loop

On non-Windows platforms this uses ``uvloop`` when available, otherwise the
default asyncio loop, so the same command works cross-platform.
"""

import asyncio
import sys
from typing import Any


def check_port_is_usable(port: int, host: str = "127.0.0.1") -> None:
    """启动前自检：端口被**坏掉的进程**占着时，**明确报错**（2026-10-06 加）

    ## 为什么需要这个检查

    实测踩过：上一轮后端被我**强杀**（`job_kill` / 任务管理器结束进程），
    留下了半个 ``--reload`` 的父子进程结构：

        PID 20968  uvicorn 主进程（--reload）
          └─ PID 40356  监听 8000
               └─ PID 37744  --reload 派生的 worker

    强杀把这棵树杀成半截后，监听器**还在**、``netstat`` 显示"在监听"，
    但它已经失去控制它的父进程，于是每次 accept 都崩：

        ERROR asyncio: Accept failed on a socket
          laddr=('127.0.0.1', 8000)
        OSError: [WinError 87] 参数错误

    ⇒ 后果是**新启动的后端绑到这个坏端口上，"看起来启动成功"，
    但所有请求都超时**。用户看到的是"点第 2 页空白"，
    会误以为是自己操作错了、或功能坏了。

    ⚠️ 关键教训：**"端口在监听" ≠ "端口能用"。**
       我当时只查了前一个，就说"8000 已释放 ✓" —— 那是误判。

    ## 这里做什么

    发一个真实的 HTTP 请求探活。**能应答 = 端口健康**（无论是谁在服务）；
    **连不上 = 端口干净**，可以启动。

    ⚠️ 探活要**短超时**（默认 3 秒）—— 端口真被坏进程占着时，
       connect 会成功但永远等不到响应，正好落进"探活失败 = 端口坏"
       这个分支，正是要抓的情况。
    """
    import socket

    # ① 能不能连上：连不上说明没人占，端口是干净的
    try:
        with socket.create_connection((host, port), timeout=2):
            pass
    except OSError:
        return  # 没人监听 → 干净，放行

    # ② 连得上但不应答 = 有人占着且是活的 → 那可能是正常的旧后端
    import urllib.error
    import urllib.request

    try:
        urllib.request.urlopen(f"http://{host}:{port}/", timeout=3)
        return  # 有响应 → 端口健康（可能只是上一次的进程还在跑）
    except urllib.error.HTTPError:
        return  # 有 HTTP 响应码也算"活的"
    except Exception:
        pass

    # ③ 连得上、却毫无响应 → 坏掉的监听器
    raise SystemExit(
        f"\n"
        f"{'=' * 68}\n"
        f"❌ 端口 {port} 被一个**坏掉的进程**占着，启动了也没用。\n"
        f"{'=' * 68}\n\n"
        f"   症状：所有请求都会超时（连最简单的接口也不响应）。\n"
        f"   原因：上一次的进程被**强杀**（Ctrl+C 之外的强杀 / 任务管理器\n"
        f"         结束进程），把 uvicorn 的 --reload 父子进程杀成了半截，\n"
        f"         监听器还在但已经失去控制它的父进程。\n\n"
        f"   解决办法（任选一条）：\n\n"
        f"     ① 结束掉残留进程：\n"
        f"          Get-Process python | Stop-Process -Force\n\n"
        f"     ② 或者换一个端口启动：\n"
        f"          uvicorn app.main:app --port {port + 1}\n\n"
        f"   ⚠️ 注意：用 Ctrl+C 正常停止就不会有这个问题。\n"
        f"{'=' * 68}\n"
    )


def new_loop() -> Any:
    """Build the event loop uvicorn should run on. Takes no arguments.

    Signature note (learned the hard way): when ``--loop`` points at a **custom**
    dotted path, uvicorn does *not* call it with ``use_subprocess`` — it returns
    the resolved object as-is and later calls it with **zero arguments**:

        # uvicorn/config.py, custom-path branch
        return import_from_string(self.loop)        # no (use_subprocess=...) call
        # uvicorn/_compat.py
        loop = loop_factory()                       # must yield a LOOP INSTANCE

    So this must be a plain zero-argument function returning an instance. Two
    earlier attempts failed here: returning the factory-of-a-factory (uvicorn got
    a function and crashed on ``loop.close()``), and returning
    ``asyncio.ProactorEventLoop`` directly — on Python 3.10/Windows *calling that
    class returns the class itself, not an instance*, which produced
    ``BaseProactorEventLoop.close() missing 1 required positional argument: 'self'``.
    """
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()

    try:  # uvloop is optional
        import uvloop  # type: ignore

        return uvloop.new_event_loop()
    except ImportError:
        return asyncio.new_event_loop()
