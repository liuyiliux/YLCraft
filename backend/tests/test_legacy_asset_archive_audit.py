from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.asset import Asset
from app.db.models.asset_hub import AssetNode, AssetType
from app.services.asset.service import AssetService
from app.services.asset_hub.legacy_migration import (
    _asset_audit_item,
    _asset_missing_file,
    _duplicate_asset_paths,
    _safe_audit_url,
)


def test_archive_audit_detects_missing_local_files(tmp_path: Path):
    existing = tmp_path / "image.png"
    existing.write_bytes(b"demo")

    assert _asset_missing_file(Asset(id="a1", type="image", file_path=str(existing))) is False
    assert _asset_missing_file(Asset(id="a2", type="image", file_path=str(tmp_path / "missing.png"))) is True
    assert _asset_missing_file(Asset(id="a3", type="image", file_path="https://example.test/image.png")) is False


def test_archive_audit_reports_duplicate_paths():
    duplicate = "C:/tmp/demo.mp4"
    rows = [
        Asset(id="a1", type="video", file_path=duplicate),
        Asset(id="a2", type="video", file_path=duplicate),
        Asset(id="a3", type="video", file_path="C:/tmp/other.mp4"),
    ]

    result = _duplicate_asset_paths(rows)

    assert result == [{"file_path": duplicate, "asset_ids": ["a1", "a2"], "count": 2}]


def test_archive_audit_item_includes_archive_state_and_node_id():
    node = AssetNode(
        id="node-1",
        name="Migrated",
        asset_type=AssetType.IMAGE,
        metadata_json={"legacy_asset_id": "asset-1"},
    )
    asset = Asset(
        id="asset-1",
        type="image",
        title="Legacy",
        status="READY",
        source_type="ai_generated",
        file_path="C:/tmp/legacy.png",
        source_url="ylcraft://legacy.png",
    )

    item = _asset_audit_item(
        asset,
        {"asset_hub_archive_state": "archived_in_hub", "archived_in_hub": True},
        node,
    )

    assert item["asset_id"] == "asset-1"
    assert item["asset_hub_node_id"] == "node-1"
    assert item["archive_state"] == "archived_in_hub"
    assert item["archived_in_hub"] is True


def test_archive_audit_url_strips_signed_query():
    sanitized = _safe_audit_url("https://example.test/path/image.png?X-Amz-Signature=secret#frag")

    assert sanitized == "https://example.test/path/image.png"


@pytest.mark.asyncio
async def test_legacy_list_hides_migrated_images_but_keeps_courses(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'assets.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Asset.__table__.create)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        session.add_all(
            [
                Asset(
                    id="img-1",
                    type="image",
                    title="Migrated image",
                    status="READY",
                    source_url="ylcraft://image/img-1",
                    metadata_json='{"asset_hub_node_id":"node-image"}',
                ),
                Asset(
                    id="course-1",
                    type="COLLECTION",
                    title="Migrated course",
                    status="READY",
                    source_url="bilibili:paid_course:ss1",
                    metadata_json='{"asset_hub_node_id":"node-course","type":"paid_course"}',
                ),
            ]
        )
        await session.commit()

        service = AssetService(session)
        visible, total = await service.list_assets(page=1, page_size=20)
        all_rows, all_total = await service.list_assets(
            page=1,
            page_size=20,
            include_archived_legacy=True,
        )

    await engine.dispose()

    assert total == 1
    assert [asset.id for asset in visible] == ["course-1"]
    assert all_total == 2
    assert {asset.id for asset in all_rows} == {"img-1", "course-1"}
