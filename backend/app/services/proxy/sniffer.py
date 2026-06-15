"""
代理抓包引擎 — 基于标准库实现轻量 HTTP 代理

监听本地端口，拦截 HTTP/HTTPS 请求，记录捕获到的请求详情。
提供启动/停止/状态查询等生命周期管理。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from typing import Optional, Callable
from urllib.parse import urlparse

logger = logging.getLogger("ylcraft.proxy.sniffer")


class ProxySniffer:
    """
    轻量 HTTP 代理抓包引擎

    监听本地端口，拦截并记录 HTTP 请求。
    """

    def __init__(self):
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[Thread] = None
        self._running: bool = False
        self._session_id: str = ""
        self._port: int = 8080
        self._captured_requests: list[dict] = []
        self._filter_domains: list[str] = []
        self._started_at: Optional[datetime] = None
        self._on_capture: Optional[Callable] = None

    # ── 生命周期 ──────────────────────────────────────────────

    def start(
        self,
        port: int = 8080,
        filter_domains: Optional[list[str]] = None,
        on_capture: Optional[Callable] = None,
    ) -> dict:
        """
        启动抓包代理

        Returns:
            { session_id, port, status }
        """
        if self._running:
            return {"session_id": self._session_id, "port": self._port, "status": "already_running"}

        self._session_id = str(uuid.uuid4())
        self._port = port
        self._filter_domains = filter_domains or []
        self._on_capture = on_capture
        self._captured_requests.clear()
        self._started_at = datetime.now(timezone.utc).replace(tzinfo=None)

        sniffer = self

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                sniffer._handle_request(self, "GET")
            def do_POST(self):
                sniffer._handle_request(self, "POST")
            def do_PUT(self):
                sniffer._handle_request(self, "PUT")
            def do_DELETE(self):
                sniffer._handle_request(self, "DELETE")
            def do_HEAD(self):
                sniffer._handle_request(self, "HEAD")
            def log_message(self, format, *args):
                pass  # 静默日志

        try:
            self._server = HTTPServer(("127.0.0.1", port), _Handler)
            self._server.timeout = 1.0
            self._running = True

            def _run():
                while self._running:
                    self._server.handle_request()

            self._thread = Thread(target=_run, daemon=True)
            self._thread.start()
            logger.info(f"[ProxySniffer] 已启动: 127.0.0.1:{port} session={self._session_id}")
            return {"session_id": self._session_id, "port": port, "status": "running"}
        except Exception as e:
            self._running = False
            logger.error(f"[ProxySniffer] 启动失败: {e}")
            return {"error": str(e)}

    def stop(self) -> dict:
        """停止抓包代理"""
        if not self._running:
            return {"status": "not_running"}

        self._running = False
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                pass
            self._server = None
        self._thread = None
        logger.info(f"[ProxySniffer] 已停止 session={self._session_id}")
        return {"status": "stopped", "total_captured": len(self._captured_requests)}

    def _handle_request(self, handler: BaseHTTPRequestHandler, method: str):
        """处理拦截的请求"""
        try:
            url = handler.path
            host = handler.headers.get("Host", "")
            content_type = handler.headers.get("Content-Type", "")
            user_agent = handler.headers.get("User-Agent", "")

            # 域名过滤
            if self._filter_domains:
                matches = any(d in host for d in self._filter_domains)
                if not matches:
                    handler.send_response(200)
                    handler.end_headers()
                    handler.wfile.write(b"OK")
                    return

            captured = {
                "id": str(uuid.uuid4())[:8],
                "method": method,
                "url": url,
                "host": host,
                "content_type": content_type,
                "user_agent": user_agent,
                "headers": dict(handler.headers),
                "timestamp": int(time.time() * 1000),
                "captured_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            }

            # 读取请求体
            content_length = int(handler.headers.get("Content-Length", 0))
            if content_length and content_length < 1024 * 1024:  # 最大 1MB
                body = handler.rfile.read(content_length)
                captured["body"] = body.decode("utf-8", errors="replace")[:10000]

            self._captured_requests.append(captured)

            if self._on_capture:
                try:
                    self._on_capture(captured)
                except Exception:
                    pass

            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Access-Control-Allow-Origin", "*")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "captured"}).encode())

        except Exception as e:
            logger.debug(f"[ProxySniffer] 处理请求异常: {e}")

    # ── 状态查询 ──────────────────────────────────────────────

    def get_status(self) -> dict:
        """获取当前抓包状态"""
        elapsed = 0
        if self._started_at:
            elapsed = int((datetime.now(timezone.utc).replace(tzinfo=None) - self._started_at).total_seconds())

        return {
            "session_id": self._session_id,
            "running": self._running,
            "port": self._port,
            "started_at": self._started_at.isoformat() if self._started_at else "",
            "elapsed_seconds": elapsed,
            "total_captured": len(self._captured_requests),
            "filter_domains": self._filter_domains,
            "captured_requests": self._captured_requests[-100:],  # 最近 100 条
        }

    def clear(self):
        """清空已捕获的请求"""
        self._captured_requests.clear()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def captured_count(self) -> int:
        return len(self._captured_requests)
