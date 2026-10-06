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


def _pids_listening_on(port: int) -> list[int]:
    """列出正在监听 ``port`` 的进程 PID（取不到就返回空列表）。

    只用标准库 —— 这个项目**没有 psutil**（实测确认），
    所以走 ``netstat -ano``。查不到不是错误，返回空列表由调用方放行。
    """
    import subprocess

    try:
        out = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        return []

    pids = set()
    needle = f":{port}"
    for line in out.splitlines():
        parts = line.split()
        # LISTENING 状态 + 末尾一列是 PID
        if len(parts) >= 5 and parts[0].upper() == "TCP" \
                and parts[1].endswith(needle) and "LISTENING" in parts[-2].upper():
            try:
                pids.add(int(parts[-1]))
            except ValueError:
                continue
    return sorted(pids)


def _pid_alive(pid: int) -> bool:
    """PID 对应的进程是否还活着。"""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        # 查不了 ≠ 死了 —— 按"活着"处理，宁可放过
        return True
    return str(pid) in out


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

    ## ⚠️⚠️ 这个检查**曾把正常后端拦下来**（写第一版时犯的错）

    第一版只发一个 HTTP 请求探活，3 秒没应答就判"坏"。结果用户正常启动
    后端时**被这个检查挡在门外**，直接起不来：

        SystemExit: 端口 8000 被一个坏掉的进程占着

    而那个后端**是好的** —— 它正在启动过程中，正忙于初始化（AI Provider、
    连接器注册、数据库），3 秒当然应答不过来。

    ⇒ **"3 秒没应答" ≠ "坏了"。** 一个正在启动或正忙的服务也是这个表现。

    ## 所以现在的判据：**能不能说清占用者是谁**

    用 `netstat` 找到占着端口的 PID，再看那个进程**还在不在**：

    | 占用者状态              | 结论           | 动作     |
    | ---------------------- | -------------- | -------- |
    | 没人占                  | 干净           | 放行     |
    | PID 活着、是我们的后端 | **正常**       | 放行     |
    | PID 活着、但**探活有响应** | 正常（旧实例） | 放行   |
    | PID 活着、却毫无响应    | ⚠️ 可疑       | **只警告，不阻止启动** |
    | **PID 查不到 / 已退出** | **确定坏了**   | 报错拦住 |

    ⇒ 只有**确定坏**（占着端口的进程根本不存在）才拦启动。
       其余情况一律放行 —— 启动检查宁可放过，也绝不能挡住正常启动。
    """
    import socket

    # ---------- ① 能不能连上：连不上说明没人占，端口是干净的 ----------
    try:
        with socket.create_connection((host, port), timeout=2):
            pass
    except OSError:
        return  # 没人监听 → 干净，放行

    # ---------- ② 找占用者 ----------
    pids = _pids_listening_on(port)
    if not pids:
        # 连得上却查不到占用者（端口被关掉了、或权限不足）—— 不确定，放行
        return

    alive = [p for p in pids if _pid_alive(p)]

    # ---------- ③ 占用者还活着 → 它就是服务，放行 ----------
    if alive:
        return

    # ---------- ④ 占着端口的进程**已经不在了** → 确定是坏残留 ----------
    raise SystemExit(
        f"\n"
        f"{'=' * 68}\n"
        f"❌ 端口 {port} 被一个**已经死掉的进程**的残留监听器占着，"
        f"启动了也没用。\n"
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
