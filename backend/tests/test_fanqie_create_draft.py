"""番茄「自动建草稿」契约测试。

2026-09-26 实测背景：**更正此前结论**。

早前记录过「番茄没有创建章节的接口」，并据此让用户每次手动建章。那是**误判**：
当时只抓了「新建章节」入口（`?enter_from=newchapter`，实测确实是纯前端路由、
零 author API 调用），漏掉了「新建草稿」入口（`?enter_from=newdraft`）——
后者会真实调用：

    POST /api/author/article/new_article/v0/
    => {"code":0,"data":{"item_id":"<新草稿ID>","volume_id":"...","latest_version":0,...}}

拿到 `item_id` 后即可交给 `save_draft` 写正文，因此「自动建章」是可行的，
不需要用户先去番茄网页手动创建。

实测闭环：create_draft → item_id 7689533897855468056；
save_draft → latest_version: 1；edit_article 回读标题与正文均正确。
"""

from __future__ import annotations

import inspect

import pytest


def test_new_article_endpoint_constant():
    from app.services.platforms.fanqie.apis import NEW_ARTICLE

    assert NEW_ARTICLE == "/api/author/article/new_article/v0/"


def test_client_has_create_draft():
    from app.services.platforms.fanqie.client import FanqieClient

    assert hasattr(FanqieClient, "create_draft")


def test_create_draft_is_a_write_that_documents_non_idempotency():
    """create_draft 是写入操作：docstring 必须写明不幂等，避免被静默重试。"""
    from app.services.platforms.fanqie.client import FanqieClient

    doc = inspect.getsource(FanqieClient.create_draft)
    assert "幂等" in doc, "应说明重复调用会生成多个草稿（非幂等）"
    assert "NEW_ARTICLE" in doc


@pytest.mark.asyncio
async def test_create_draft_posts_to_new_article_and_returns_item_id(monkeypatch):
    """必须 POST 到 new_article 端点，并把 data.item_id 原样带出。"""
    from app.services.platforms.fanqie.client import FanqieClient
    from app.services.platforms.types import ClientConfig, ClientMode

    client = FanqieClient(
        ClientConfig(platform="fanqie", mode=ClientMode.API, cookie="ignored")
    )
    captured: dict = {}

    async def fake_call(method, endpoint, **kwargs):
        captured["method"] = method
        captured["endpoint"] = endpoint
        captured["data"] = kwargs.get("data")
        return {
            "code": 0,
            "data": {
                "item_id": "999",
                "volume_id": "vol-1",
                "latest_version": 0,
            },
        }

    monkeypatch.setattr(client, "_call", fake_call)

    data = await client.create_draft("book-1")

    assert captured["method"] == "POST"
    assert captured["endpoint"] == "/api/author/article/new_article/v0/"
    assert captured["data"]["book_id"] == "book-1"
    assert data["item_id"] == "999"


def test_route_requires_explicit_confirm():
    """HTTP 层必须要求 confirm=true——这是写入操作，不能默认执行。"""
    from app.services.platforms.fanqie import routes

    source = inspect.getsource(routes.create_book_draft)
    assert "confirm" in source, "应要求显式 confirm 参数"
    assert "confirm=true" in source or "confirm=true" in inspect.getsource(
        routes
    ), "错误提示应说明需要 confirm=true"


def test_route_registered():
    """GET（列表）与 POST（新建）必须同时挂载在同一路径上。

    注意：两条路由路径相同、方法不同；只取第一条匹配会漏判，
    所以这里收集全部匹配再断言。
    """
    from app.main import app

    methods: set[str] = set()
    for route in app.routes:
        if getattr(route, "path", "") == "/api/v1/fanqie/book/{book_id}/drafts":
            methods |= set(getattr(route, "methods", None) or set())

    assert "GET" in methods, "缺少草稿箱列表路由"
    assert "POST" in methods, "缺少新建草稿路由"
