from __future__ import annotations

import pytest

from app.api.v1.tags import _virtual_tag_counts


@pytest.mark.asyncio
async def test_virtual_tag_counts_unpacks_asset_hub_card_page(monkeypatch):
    class Service:
        session = object()

    async def fake_cards(session, **kwargs):
        assert kwargs["page"] == 1
        assert kwargs["page_size"] == 1000
        return ([{"type": "image", "title": "AI 角色立绘", "tags": [], "metadata": {}}], 1)

    monkeypatch.setattr("app.api.v1.tags._list_asset_hub_cards", fake_cards)

    counts = await _virtual_tag_counts(Service())

    assert counts["角色"] == 1
    assert counts["角色立绘"] == 1
