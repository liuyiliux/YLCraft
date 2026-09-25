"""Cookie 获取端点的前缀一致性回归测试。

真机故障（2026-09-25）：账号中心点「启动浏览器」后，HTTP `POST .../start` 返回 200，
但紧接着的 WebSocket 握手返回 **403**（连接被拒绝），弹窗永远停在加载态。

根因不是鉴权，是**路径前缀漂移**：
- 提交 `0e5690ec` 把 `cookie_acquisition.router` 挂在 `/api/v1/platforms`
- 提交 `d23227eb` 改挂到 `/api/v1`，并同步了 qrcode 的 WebSocket 地址，
  但**漏改 playwright 的两处 WebSocket**
- 于是前端仍在请求 `/api/v1/platforms/acquire/playwright/{sid}/ws`（不存在）

HTTP 之所以还能 200：前端 `api/index.ts` 用的是相对路径 `/acquire/...`
（base 是 `/api/v1`），与后端一致；只有手写绝对 URL 的 WebSocket 落下了。

下面把「代码真实挂载路径」与「前端实际请求路径」钉在一起，任一侧漂移即失败。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
FRONTEND_ACCOUNTS = REPO_ROOT / "frontend" / "src" / "pages" / "accounts" / "index.tsx"
MAIN_PY = BACKEND_DIR / "app" / "main.py"


def test_router_mounted_without_platforms_prefix():
    """`cookie_acquisition` 必须挂在 /api/v1（挂 /api/v1/platforms 会让 WS 403）。"""
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/v1/acquire/playwright/start" in paths, (
        "缺少 /api/v1/acquire/playwright/start；"
        "若路由挂在 /api/v1/platforms 下，前端 WebSocket 会 403"
    )
    assert not any("/api/v1/platforms/acquire" in p for p in paths), (
        "不应存在 /api/v1/platforms/acquire 路由（与前端 WS 地址不一致会 403）"
    )


def test_websocket_route_matches_frontend_url():
    """前端 WebSocket 的绝对 URL 必须命中后端真实路由。

    这是本次故障的直接断言：前端写死的是绝对地址，漂移后 HTTP 仍 200，
    只有 WS 静默失败，极难发现。
    """
    from app.main import app

    ws_routes = {
        getattr(r, "path", "")
        for r in app.routes
        if getattr(r, "path", "").endswith("/ws")
    }
    assert "/api/v1/acquire/playwright/{session_id}/ws" in ws_routes

    if not FRONTEND_ACCOUNTS.exists():
        pytest.skip("accounts page not present")

    source = FRONTEND_ACCOUNTS.read_text(encoding="utf-8", errors="ignore")
    # 模板串里 ${sid} 是占位符，保留原文以便与后端 {session_id} 对齐比较
    frontend_urls = set(
        re.findall(r"/api/v1/[^`'\"\s]*?\$\{sid\}/ws", source)
    )
    assert frontend_urls, "前端未找到 acquire WebSocket 地址"

    expected = {p.replace("{session_id}", "${sid}") for p in ws_routes}
    stale = frontend_urls - expected
    assert not stale, (
        f"前端 WS 地址与后端路由不一致（会导致握手 403）：{sorted(stale)}\n"
        f"后端实际：{sorted(ws_routes)}"
    )


def test_documented_paths_match_runtime():
    """对外文档不得残留已废弃的 /api/v1/platforms/acquire。

    B站指南与 Nginx 示例曾长期保留旧前缀，照抄即踩坑。
    """
    docs = [
        REPO_ROOT / "docs" / "platform" / "BILIBILI_GUIDE.md",
        REPO_ROOT / "docs" / "architecture" / "API_SURFACE.md",
    ]
    for doc in docs:
        if not doc.exists():
            continue
        text = doc.read_text(encoding="utf-8", errors="ignore")
        assert "/api/v1/platforms/acquire" not in text, (
            f"{doc.name} 仍残留废弃前缀 /api/v1/platforms/acquire"
        )
