"""番茄草稿箱端点的契约测试。

2026-09-26 实测背景：番茄的**草稿**与**章节**是同一份数据的两个阶段——
未发布的草稿只出现在草稿箱，**不会**出现在 `chapter_list`；点「下一步 → 发布」
后才进入章节列表。因此只查章节列表会看不到草稿，「发布到草稿」拿不到目标 item_id。

真实路径是靠 Patchright 复用已保存 Cookie 抓包得到的：
    GET /api/author/chapter/draft_list/v1?book_id=...&page_index=0&page_count=15

两个曾经踩过的坑（都用测试钉住）：
1. 路径不能按命名习惯猜。`draft/list/v1`、`article/draft_list/v0/` 实测均 **404**，
   真实的是 `chapter/draft_list/v1`。
2. 响应字段是 `draft_list[]`，**不是** `item_list[]`（章节列表才用后者）。
   按 `item_list` 取值会静默得到空数组，看起来像"没有草稿"。
"""

from __future__ import annotations

import inspect

import pytest


def test_draft_list_endpoint_constant_is_the_captured_one():
    """端点常量必须是抓包确认的 chapter/draft_list/v1。"""
    from app.services.platforms.fanqie.apis import CHAPTER_DRAFT_LIST

    assert CHAPTER_DRAFT_LIST == "/api/author/chapter/draft_list/v1"


def test_client_has_get_book_drafts():
    from app.services.platforms.fanqie.client import FanqieClient

    assert hasattr(FanqieClient, "get_book_drafts")


def test_get_book_drafts_uses_zero_based_paging_and_draft_endpoint():
    """分页与 chapter_list 一致是 0-based；且必须打 draft_list 端点。"""
    from app.services.platforms.fanqie.client import FanqieClient

    source = inspect.getsource(FanqieClient.get_book_drafts)
    assert "CHAPTER_DRAFT_LIST" in source, "必须调用草稿箱端点常量"
    # page=1 -> page_index=0
    assert "max(page - 1, 0)" in source, "对外 1 起页码应转换为番茄 0 起 page_index"


@pytest.mark.asyncio
async def test_get_book_drafts_returns_draft_list_shape(monkeypatch):
    """返回值应原样透传 data（含 draft_list），不得改名为 item_list。"""
    from app.services.platforms.fanqie.client import FanqieClient
    from app.services.platforms.types import ClientConfig, ClientMode

    client = FanqieClient(
        ClientConfig(platform="fanqie", mode=ClientMode.API, cookie="ignored")
    )
    captured: dict = {}

    async def fake_call(method, endpoint, **kwargs):
        captured["method"] = method
        captured["endpoint"] = endpoint
        captured["params"] = kwargs.get("params")
        return {
            "code": 0,
            "data": {
                "total_count": 1,
                "draft_list": [
                    {"item_id": "123", "title": "草稿A", "word_number": 10, "index": -1}
                ],
            },
        }

    monkeypatch.setattr(client, "_call", fake_call)

    data = await client.get_book_drafts("book-1", page=2, size=30)

    assert captured["endpoint"] == "/api/author/chapter/draft_list/v1"
    assert captured["method"] == "GET"
    assert captured["params"]["page_index"] == "1", "page=2 应转成 0 起的 1"
    assert captured["params"]["page_count"] == "30"
    assert "draft_list" in data
    assert data["draft_list"][0]["item_id"] == "123"


def test_route_registered():
    """/api/v1/fanqie/book/{book_id}/drafts 必须已挂载。"""
    import asyncio

    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/v1/fanqie/book/{book_id}/drafts" in paths
