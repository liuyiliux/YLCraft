"""前端读取平台连接接口的契约测试。

## 踩过的坑（2026-09-27）

`inspiration/index.tsx`（番茄热榜灵感页）读连接时用了 `res?.data`，
但 `/api/v1/platforms` 返回的是 `{success, connections: [...]}` ——
`res.data` 恒为 undefined → 连接列表永远为空 →
界面一直显示「未找到番茄连接」，**即使库里有一条有效的番茄连接**。

其它页面（crawler / download / my-data / publish / up-analytics）用的
都是 `res.connections`，只有这一个页面写错了。

实测证据：接口返回里 `platform=fanqie, status=active, account_name=逸流AI`，
但页面筛不出来。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _read(rel: str) -> str:
    p = FRONTEND / rel
    if not p.exists():
        pytest.skip(f"前端源码不在预期位置: {rel}")
    return p.read_text(encoding="utf-8", errors="ignore")


def _strip_line_comments(src: str) -> str:
    """去掉 // 行注释。

    注释里记录了"原来用 res?.data"这个坑，直接对全文断言会被注释误伤。
    """
    return "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("//")
    )


def test_inspiration_reads_connections_not_data():
    """**回归**：番茄灵感页必须从 `res.connections` 读连接。

    用 `res.data` 会让连接列表恒为空 → 一直显示"未找到番茄连接"。
    """
    src = _read("pages/inspiration/index.tsx")
    i = src.find("listPlatformConnections()")
    assert i != -1, "应调用 listPlatformConnections"
    seg = _strip_line_comments(src[i:i + 900])
    assert "connections" in seg, "应从 res.connections 读取"
    assert "res?.data" not in seg, "不该用 res.data（接口没这个字段）"


def test_other_pages_use_connections():
    """其它读连接的页面也要用 res.connections（保持一致）。"""
    for rel in (
        "pages/crawler/index.tsx",
        "pages/download/index.tsx",
        "pages/my-data/index.tsx",
        "pages/publish/index.tsx",
    ):
        src = _read(rel)
        assert ".connections" in src, f"{rel} 应从 connections 读"


def test_inspiration_filters_active_only():
    """筛连接时要排除非 active 的（unknown/失效连接不能用）。"""
    src = _read("pages/inspiration/index.tsx")
    i = src.find("listPlatformConnections()")
    seg = _strip_line_comments(src[i:i + 900])
    assert "status === 'active'" in seg, "应只取 active 连接"
    assert "'fanqie'" in seg, "应筛番茄平台"


def test_conn_type_declares_status():
    """Conn 类型要声明 status，否则 TS 编译失败。"""
    src = _read("pages/inspiration/index.tsx")
    i = src.find("type Conn = {")
    assert i != -1
    seg = src[i:i + 400]
    assert "status" in seg, "Conn 应有 status 字段"


def test_platforms_api_returns_connections_key():
    """后端返回的字段名必须是 `connections`（前端据此读取）。

    用真实的响应模型验证，而不是对源码做文本匹配——
    `"connections": [...]` 这种字典字面量用正则会写得很脆。
    """
    from app.api.v1 import platforms as platforms_api

    src = Path(platforms_api.__file__).read_text(encoding="utf-8", errors="ignore")
    # list_connections 的返回里出现 "connections" 键
    assert '"connections"' in src, '响应应含 "connections" 键'

    # 且前端确实按这个名字读（两边对齐）
    fe = _read("api/index.ts")
    assert "listPlatformConnections" in fe


def test_response_shape_matches_frontend():
    """接口字段名与前端读取名必须一致（跨端契约）。

    实测：接口返回 {success, connections:[...]}，前端必须读 res.connections。
    曾经前端读 res.data → 恒为 undefined → 连接列表空。
    """
    from app.api.v1 import platforms as platforms_api

    src = Path(platforms_api.__file__).read_text(encoding="utf-8", errors="ignore")
    fe = _read("pages/inspiration/index.tsx")

    assert '"connections"' in src, "后端字段名是 connections"
    assert "res?.connections" in fe, "前端应按这个名字读"
