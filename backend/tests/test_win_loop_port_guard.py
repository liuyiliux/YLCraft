# -*- coding: utf-8 -*-
"""端口自检（2026-10-06 用户实测踩到后加）。

## 故障

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

## 用户看到的是什么

界面点第 2 页 → **空白**。第一页正常（那是之前缓存在前端的结果）。
然后连 ``/api/v1/platforms`` 这种最简单的接口也超时。

## ⚠️ 最贵的一课

我当时只查了"8000 有没有人监听"，看到有，就报告 **"8000 已释放 ✓"** ——
**那是误判**。"端口在监听" ≠ "端口能用"。

所以这个检查**发真实请求探活**，不是查监听表。
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


class TestBrokenListenerIsCaught(unittest.TestCase):
    """⭐ 核心用例：连得上但不应答 = 坏监听器，必须**拦下来并说清楚**。"""

    def test_black_hole_port_raises_with_actionable_message(self):
        import socket as _s
        import threading

        # 造一个"只 accept、永远不应答"的黑洞 —— 正是被强杀后
        # 那个监听器的行为（监听器活着，但控制它的父进程没了）
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
                    c, _ = srv.accept()
                    # 关键：**不关闭、也不应答** —— 连接挂着但没有响应
                except OSError:
                    continue

        t = threading.Thread(target=accept_and_hang, daemon=True)
        t.start()
        try:
            with self.assertRaises(SystemExit) as ctx:
                check_port_is_usable(port)
            msg = str(ctx.exception)
            self.assertIn("坏掉", msg)
            self.assertIn(str(port), msg, "报错要说明是哪个端口")
            # 必须给出**能照做的**操作，不是只说"出错了"
            self.assertIn("Stop-Process", msg)
            self.assertIn(str(port + 1), msg,
                          "换端口的建议也要用**这个**端口号，不能写死 8000")
        finally:
            stop.set()
            srv.close()


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