"""画布「平台搜索」节点的登录态契约测试。

## 用户反馈（2026-09-27）

画布本来就有 `platform_search` 节点（平台选项含 bili/xhs/douyin），
所以"博主中心接入画布"其实是**重复功能**——但实测发现画布搜**抖音恒为 0**，
而小红书/B站正常。这就是真 bug。

## 根因：两个搜索端点，只有一个传了 Cookie

    /crawler/search-enhanced   → 传 conn_id + cookie     ✅ 抖音能搜到
    /crawler/search            → **原本不传**             ❌ 抖音恒为 0

画布的 platform_search 节点走的是 **`/crawler/search`**。

不传 Cookie 时抖音返回 `status_code=2483`（游客态），
表现是"找到 0 条结果"——**看起来像关键词没内容，实际是没带登录态**。
而同一时刻 search_enhanced 能返回，所以很容易误判成"抖音又风控了"。

（这正是我在博主中心踩过的同一个坑，但画布这条路径一直没修。）

## 连带修复

  · `SearchRequest` 模型补 `conn_id`（前端传了但被模型丢弃）
  · 前端 `searchCrawler` 类型补 `conn_id`
  · 画布拿到连接列表，platform_search 节点可显式选连接
    （不填则自动用该平台第一个活跃连接）

## 一个教训：同名模型的陷阱

`SearchRequest` 有**两份**：`service.py` 和 `models.py`。
`services/crawler/__init__.py` 从 **service** 导出，所以路由用的是那份。

我第一次改了 models.py 那份 → 报
`AttributeError: 'SearchRequest' object has no attribute 'conn_id'`。
改成 `from service import` 想统一 → **循环导入**，整个 /api/v1/crawler
路由挂掉、全部 404（日志是 `Could not load crawler router`）。

现在保持两份独立定义但字段一致 —— 两份都要同步改。

## 实测

    修复前：/crawler/search?platform=douyin → total=0
    修复后：total=5（乡村厨房…/第一次吃成都冒菜…）
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _read(rel: str) -> str:
    p = FRONTEND / rel
    if not p.exists():
        pytest.skip(f"前端源码不在预期位置: {rel}")
    return p.read_text(encoding="utf-8", errors="ignore")


def _strip_line_comments(src: str) -> str:
    return "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("//")
    )


# =============================================================================
# 后端：/crawler/search 必须带登录态
# =============================================================================

def test_search_materials_passes_conn_id_and_cookie():
    """**回归**：`/crawler/search` 必须传 conn_id + cookie。

    原本不传 → 抖音游客态（2483）→ 结果恒为空。
    """
    from app.api.v1 import crawler as crawler_api

    src = inspect.getsource(crawler_api.search_materials)
    assert "conn_id=req.conn_id" in src, "应传 conn_id"
    assert "_get_conn_cookie" in src, "应据此取 Cookie"


def test_search_materials_documents_symptom():
    """要说明"0 结果 ≠ 没内容"，避免后人又误判成风控。"""
    from app.api.v1 import crawler as crawler_api

    doc = inspect.getdoc(crawler_api.search_materials) or ""
    assert "2483" in doc or "游客态" in doc, "应说明游客态症状"
    assert "0" in doc, "应说明表现为 0 条"


def test_both_search_request_models_have_conn_id():
    """**回归**：两份 SearchRequest 都要有 conn_id。

    路由用的是 service.py 那份，但 models.py 那份也要同步
    （曾经只改了 models → AttributeError）。
    """
    from app.services.crawler.models import SearchRequest as ModelsReq
    from app.services.crawler.service import SearchRequest as ServiceReq

    assert "conn_id" in ServiceReq.model_fields, "service 那份缺 conn_id（路由用它）"
    assert "conn_id" in ModelsReq.model_fields, "models 那份缺 conn_id"


def test_models_does_not_import_service():
    """**回归**：models.py 不能 import service.py（会循环导入）。

    实测踩过：import 后整个 /api/v1/crawler 路由挂掉、全部 404。
    """
    src = (
        Path(__file__).resolve().parents[1]
        / "app" / "services" / "crawler" / "models.py"
    ).read_text(encoding="utf-8")
    assert "from app.services.crawler.service import" not in src, (
        "models.py 不应 import service.py（循环导入会让 crawler 路由整体 404）"
    )


def test_crawler_router_still_loads():
    """**回归**：确保 crawler 路由真正挂载（防止再出现整体 404）。"""
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/v1/crawler/search" in paths, "crawler/search 未挂载"
    assert "/api/v1/crawler/search-enhanced" in paths, "search-enhanced 未挂载"


# =============================================================================
# 前端：画布 platform_search 节点
# =============================================================================

def test_canvas_passes_conn_id():
    """**回归**：画布 platform_search 运行时要传 conn_id。"""
    src = _read("pages/canvas/index.tsx")
    code = _strip_line_comments(src)
    assert "conn_id: connId" in code, "画布搜索应传 conn_id"


def test_canvas_loads_platform_connections():
    """画布要拿到连接列表（否则没得选）。"""
    src = _read("pages/canvas/index.tsx")
    assert "listPlatformConnections" in src, "应拉取连接列表"
    assert "platformConns" in src, "应有连接 state"


def test_canvas_reads_connections_not_data():
    """**回归**：从 res.connections 读（不是 res.data）。"""
    src = _read("pages/canvas/index.tsx")
    i = src.find("listPlatformConnections()")
    assert i != -1
    seg = _strip_line_comments(src[i:i + 700])
    assert "connections" in seg
    assert "res?.data" not in seg


def test_canvas_has_conn_selector_ui():
    """平台搜索节点要能显式选连接。"""
    src = _read("pages/canvas/index.tsx")
    assert "平台连接（不填则自动选）" in src, "应有连接选择器"


def test_canvas_falls_back_to_first_conn():
    """没显式选时，自动用该平台第一个活跃连接（降低使用门槛）。"""
    src = _read("pages/canvas/index.tsx")
    assert "platformConns.find" in src, "应有兜底选择"


def test_search_crawler_type_has_conn_id():
    src = _read("api/index.ts")
    i = src.find("export interface SearchCrawlerRequest")
    assert i != -1
    seg = _strip_line_comments(src[i:i + 400])
    assert "conn_id" in seg, "类型定义缺 conn_id（会导致 TS 报错）"


def test_canvas_warns_when_no_conn():
    """没有连接时要明确提示，而不是静默返回空。"""
    src = _read("pages/canvas/index.tsx")
    assert "没有可用的" in src and "连接" in src, "应提示缺少连接"
