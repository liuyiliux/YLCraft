import json
from types import SimpleNamespace

import pytest

from app.api.v1 import novels
from app.db.models.asset import Asset


class _FakeAsyncSession:
    def __init__(self, asset: Asset):
        self.asset = asset
        self.added = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, model, asset_id: str):
        return self.asset if model is Asset and asset_id == self.asset.id else None

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_archive_novel_download_to_asset_hub_writes_text_node_and_backfills_metadata(monkeypatch, tmp_path):
    merged_file = tmp_path / "novel.txt"
    merged_file.write_text("# Novel\n\ncontent", encoding="utf-8")
    asset = Asset(
        id="novel-asset-1",
        type="NOVEL",
        title="测试小说",
        author="作者",
        cover_url="https://example.test/cover.jpg",
        source_url="https://example.test/book",
        status="ready",
        metadata_json=json.dumps(
            {
                "novel_title": "测试小说",
                "chapter_count": 2,
                "downloaded_chapter_indices": [1, 2],
            },
            ensure_ascii=False,
        ),
    )
    fake_session = _FakeAsyncSession(asset)
    calls = []

    class FakeAssetHubFacade:
        def __init__(self, session):
            assert session is fake_session

        async def create_imported_file(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                node_id="hub-node-1",
                version_id="hub-version-1",
                representation_id="hub-rep-1",
            )

    monkeypatch.setattr(novels, "AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(novels, "AssetHubFacade", FakeAssetHubFacade)

    await novels._archive_novel_download_to_asset_hub(
        asset_id=asset.id,
        book_url="https://example.test/book",
        book_title="测试小说",
        author="作者",
        site="demo_source",
        chapters=[
            {"index": 1, "title": "第一章", "url": "https://example.test/1"},
            {"index": 2, "title": "第二章", "url": "https://example.test/2"},
        ],
        download_result={
            "file_path": str(merged_file),
            "total_chapters": 2,
            "success_count": 2,
            "failed_count": 0,
        },
    )

    assert fake_session.committed is True
    assert calls[0]["asset_type"] == novels.AssetType.TEXT
    assert calls[0]["source"] == "novel_download"
    assert calls[0]["file_path"] == str(merged_file)
    assert calls[0]["metadata"]["legacy_asset_id"] == asset.id
    assert calls[0]["lineage"]["chapter_indices"] == [1, 2]

    metadata = json.loads(asset.metadata_json)
    assert metadata["asset_hub_node_id"] == "hub-node-1"
    assert metadata["asset_hub_version_id"] == "hub-version-1"
    assert metadata["asset_hub_representation_id"] == "hub-rep-1"
    assert metadata["archived_in_hub"] is True
