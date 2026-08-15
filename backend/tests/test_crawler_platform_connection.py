from __future__ import annotations

import pytest

from app.api.v1 import crawler


@pytest.mark.asyncio
async def test_enhanced_search_uses_connection_cookie_only_for_platform_call(monkeypatch):
    captured: dict[str, object] = {}

    class Service:
        async def search_videos(self, **kwargs):
            captured.update(kwargs)
            return []

    monkeypatch.setattr(crawler, "get_crawler_service", lambda: Service())
    monkeypatch.setattr(crawler, "_get_conn_cookie", lambda conn_id: "private-cookie" if conn_id == "conn-1" else "")

    response = await crawler.search_enhanced(crawler.SearchEnhancedRequest(
        platform="xhs", keyword="reference", conn_id="conn-1", max_results=5,
    ))

    assert response.success is True
    assert captured["cookie"] == "private-cookie"
    assert captured["platform"] == "xhs"
    assert "cookie" not in response.model_dump()


@pytest.mark.asyncio
async def test_enhanced_search_without_connection_uses_empty_cookie(monkeypatch):
    captured: dict[str, object] = {}

    class Service:
        async def search_videos(self, **kwargs):
            captured.update(kwargs)
            return []

    monkeypatch.setattr(crawler, "get_crawler_service", lambda: Service())
    monkeypatch.setattr(crawler, "_get_conn_cookie", lambda _conn_id: pytest.fail("cookie lookup should not run"))

    await crawler.search_enhanced(crawler.SearchEnhancedRequest(platform="dy", keyword="reference"))

    assert captured["cookie"] == ""
