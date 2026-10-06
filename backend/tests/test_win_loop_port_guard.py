# -*- coding: utf-8 -*-
"""端口自检（2026-10-06 用户实测踩到后加）。

## 故障一：强杀残留的坏监听器

上一轮后端被**强杀**（不是 Ctrl+C），留下半个 ``--reload`` 进程树：

    PID 20968  uvicorn 主进程
      └─ PID 40356  监听 8000
           └─ PID 37744  --reload 派生的 worker

强杀把这棵树杀成半截之后，监听器**还在**、`netstat` 显示"在监听"，
但它已经失去控制它的父进程，于是每次 accept 都崩：

    ERROR asyncio: Accept failed on a socket
      laddr=('127.0.0.1', 8000)
    OSError: [WinError 87] 参数错误

⇒ 新后端绑到这个坏端口上，**"看起来启动成功"，但所有请求都超时**。

用户看到的是：界面点第 2 页 → **空白**。第一页正常（那是前端缓存的旧结果）。
然后连 ``/api/v1/platforms`` 这种最简单的接口也超时。

## ⚠️ 故障二：**我自己写的检查把正常后端拦下来了**

第一版用"发个 HTTP 请求探活，3 秒不应答就判坏"。结果用户正常启动后端时
**直接起不来**：

    SystemExit: 端口 8000 被一个坏掉的进程占着

而那个后端**是好的** —— 它正在启动过程中（初始化 AI Provider、注册连接器、
连数据库），3 秒当然应答不过来。

⇒ **"没及时应答" ≠ "坏了"。** 一个活着但正忙的服务也是这个表现。

## 最终判据

只有**确定坏**才拦启动：

| 占用者状态             | 结论     | 动作         |
| ---------------------- | -------- | ------------ |
| 没人占                 | 干净     | 放行         |
| PID 活着               | **正常** | 放行         |
| 查不到占用者           | 不确定   | 放行         |
| **PID 查得到但已退出** | **确定坏** | 报错拦住   |

## ⚠️ 第一课："端口在监听" ≠ "端口能用"

我当时只查了"8000 有没有人监听"，看到有，就报告 **"8000 已释放 ✓"** ——
**那是误判**，用户照做后问题依旧。

## ⚠️ 第二课：启动检查宁可放过，也绝不能挡住正常启动

写这类"防御性检查"时，**误报的代价远大于漏报**：漏报只是少帮一次忙，
误报是让人**根本起不来**，而且会被当成程序有 bug。
"""
import socket
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.win_loop import check_port_is_usable  # noqa: E402


def _free_port() -> int:
    """找一个当前没人占的端口。"""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestCleanPortPasses(unittest.TestCase):
    """端口干净 → 必须放行（否则正常启动被拦住）。"""

    def test_unused_port_passes(self):
        check_port_is_usable(_free_port())  # 不抛异常即通过

    def test_returns_none(self):
        self.assertIsNone(check_port_is_usable(_free_port()))


class TestHealthyServerPasses(unittest.TestCase):
    """有人**正常**在服务 → 也要放行（不能误杀用户的正常后端）。"""

    def test_live_server_passes(self):
        import http.server
        import threading

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            check_port_is_usable(port)  # 不抛 = 通过
        finally:
            srv.shutdown()
            srv.server_close()


class TestBusyButAliveServiceIsNotBlocked(unittest.TestCase):
    """⭐⭐ 写第一版时犯的错：把**正常但正忙**的后端拦下来了。

    实测：用户正常启动后端时被这个检查挡住，直接起不来 ——
    ``SystemExit: 端口 8000 被一个坏掉的进程占着``。
    而那个后端**是好的**，它正在启动过程中（初始化 AI Provider、
    注册连接器），3 秒当然应答不过来。

    ⇒ **"没及时应答" ≠ "坏了"。** 一个活着但正忙的服务也是这个表现。
    """

    def test_slow_responding_but_live_listener_passes(self):
        """黑洞 socket（accept 但不应答）+ **进程活着** → 必须放行。"""
        import socket as _s
        import threading

        srv = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
        srv.setsockopt(_s.SOL_SOCKET, _s.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(5)
        port = srv.getsockname()[1]
        stop = threading.Event()

        def accept_and_hang():
            srv.settimeout(0.5)
            while not stop.is_set():
                try:
                    srv.accept()   # 接了连接，但**永不回应**
                except OSError:
                    continue

        threading.Thread(target=accept_and_hang, daemon=True).start()
        try:
            # 本进程就是占用者（活着）→ 绝不能报错拦启动
            check_port_is_usable(port)
        finally:
            stop.set()
            srv.close()

    def test_never_blocks_when_netstat_unavailable(self):
        """⚠️ 查不到占用者时**必须放行** —— 不确定 ≠ 坏。

        启动检查宁可放过，也绝不能挡住正常启动。
        """
        import app.core.win_loop as wl
        orig = wl._pids_listening_on
        wl._pids_listening_on = lambda port: []
        try:
            wl.check_port_is_usable(_free_port())  # 不抛即通过
        finally:
            wl._pids_listening_on = orig


class TestDeadListenerIsCaught(unittest.TestCase):
    """只有**占用者已经死了**（残留监听器）才拦 —— 这才是真故障。"""

    def test_dead_owner_raises_with_actionable_message(self):
        import app.core.win_loop as wl
        import socket as _s

        # 造一个"连得上、但 netstat 报不出占用者（或报了个已死的 PID）"
        srv = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
        srv.setsockopt(_s.SOL_SOCKET, _s.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(5)
        port = srv.getsockname()[1]
        # 谎报：占用者是一个**已经退出**的 PID
        dead_pid = 999999
        orig = wl._pids_listening_on
        wl._pids_listening_on = lambda p: [dead_pid]
        orig_alive = wl._pid_alive
        wl._pid_alive = lambda p: False
        try:
            with self.assertRaises(SystemExit) as ctx:
                wl.check_port_is_usable(port)
            msg = str(ctx.exception)
            self.assertIn("已经死掉的进程", msg)
            self.assertIn(str(port), msg, "报错要说明是哪个端口")
            # 必须给出**能照做的**操作，不是只说"出错了"
            self.assertIn("Stop-Process", msg)
            self.assertIn(str(port + 1), msg,
                          "换端口的建议也要用**这个**端口号，不能写死 8000")
        finally:
            wl._pids_listening_on = orig
            wl._pid_alive = orig_alive
            srv.close()

    def test_alive_owner_is_never_blocked(self):
        """占用者活着（哪怕不应答）→ 一律放行。"""
        import app.core.win_loop as wl
        import socket as _s

        srv = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
        srv.setsockopt(_s.SOL_SOCKET, _s.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(5)
        port = srv.getsockname()[1]
        orig = wl._pids_listening_on
        wl._pids_listening_on = lambda p: [4242]
        orig_alive = wl._pid_alive
        wl._pid_alive = lambda p: True
        try:
            wl.check_port_is_usable(port)   # 不抛 = 通过
        finally:
            wl._pids_listening_on = orig
            wl._pid_alive = orig_alive
            srv.close()


class TestHelpers(unittest.TestCase):
    """两个辅助函数本身的行为。"""

    def test_pids_listening_finds_self(self):
        """当前进程正监听时，必须能查到自己。"""
        import socket as _s
        from app.core.win_loop import _pid_alive, _pids_listening_on
        import os

        srv = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
        srv.setsockopt(_s.SOL_SOCKET, _s.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(5)
        port = srv.getsockname()[1]
        try:
            pids = _pids_listening_on(port)
            self.assertIn(os.getpid(), pids,
                          f"要能查到自己（pid={os.getpid()}），实得 {pids}")
            self.assertTrue(_pid_alive(os.getpid()))
        finally:
            srv.close()

    def test_pid_alive_on_garbage_is_true(self):
        """⚠️ 查不了 ≠ 死了 —— 按"活着"处理，宁可放过。"""
        from app.core.win_loop import _pid_alive
        self.assertTrue(_pid_alive(-1))

    def test_unknown_port_returns_empty(self):
        from app.core.win_loop import _pids_listening_on
        self.assertEqual([], _pids_listening_on(1))   # 端口 1 不该有监听


class TestStartupWiring(unittest.TestCase):
    """这个检查必须**真的在启动时跑**，否则写了等于没写。"""

    def test_lifespan_calls_it_first(self):
        import inspect

        from app.main import lifespan
        src = inspect.getsource(lifespan)
        self.assertIn("check_port_is_usable", src,
                      "启动时必须做端口自检")

        i = src.index("check_port_is_usable")
        j = src.index("init_db")
        self.assertLess(i, j,
                        "自检必须在数据库初始化**之前** —— "
                        "端口坏着就该立刻报错，别让人白等几十秒初始化")

    def test_selfcheck_exception_does_not_block_startup(self):
        """自检自己出错（不是发现端口坏）时**不能挡住启动**。"""
        import inspect

        from app.main import lifespan
        src = inspect.getsource(lifespan)
        self.assertIn("except Exception", src,
                      "自检本身出错要放行 —— 防御性检查不该拖垮启动")


class TestWinLoopStillWorks(unittest.TestCase):
    """⚠️ 加了检查不能把原来的功能弄坏。"""

    def test_new_loop_returns_proactor_on_windows(self):
        from app.core.win_loop import new_loop
        if sys.platform == "win32":
            import asyncio
            loop = new_loop()
            try:
                self.assertIsInstance(loop, asyncio.ProactorEventLoop)
            finally:
                loop.close()

    def test_new_loop_takes_no_arguments(self):
        """uvicorn 对自定义 --loop 是**零参调用**，签名不能变。"""
        import inspect
        from app.core.win_loop import new_loop
        self.assertEqual(0, len(inspect.signature(new_loop).parameters))


if __name__ == "__main__":
    unittest.main(verbosity=2)