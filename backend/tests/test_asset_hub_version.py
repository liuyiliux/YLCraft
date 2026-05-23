"""
资产中枢单元测试 - AssetVersion 版本管理
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from uuid import uuid4

from app.db.database import AsyncSessionLocal
from app.db.models.asset_hub import (
    AssetNode,
    AssetVersion,
    AssetRepresentation,
    AssetType,
)


@pytest_asyncio.fixture
async def db_session():
    """创建测试数据库会话"""
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_asset(db_session):
    """创建测试用的 AssetNode"""
    asset = AssetNode(
        id=str(uuid4()),
        name="test_character",
        asset_type=AssetType.CHARACTER,
    )
    db_session.add(asset)
    await db_session.commit()
    return asset


@pytest.mark.asyncio
async def test_create_version(db_session, test_asset):
    """测试创建资产版本"""
    version = AssetVersion(
        id=str(uuid4()),
        asset_node_id=test_asset.id,
        version_number=1,
        prompt_used="young swordsman, white clothes",
        model_used="SDXL",
        params_json={"steps": 30, "guidance_scale": 7.5},
    )

    db_session.add(version)
    await db_session.commit()
    await db_session.refresh(version)

    assert version.id is not None
    assert version.asset_node_id == test_asset.id
    assert version.version_number == 1
    assert version.prompt_used == "young swordsman, white clothes"


@pytest.mark.asyncio
async def test_create_multiple_versions(db_session, test_asset):
    """测试创建多个版本（角色多装扮场景）"""
    versions_data = [
        {
            "version_number": 1,
            "prompt_used": "young swordsman, white clothes",
            "model_used": "SDXL",
        },
        {
            "version_number": 2,
            "prompt_used": "adult swordsman, blue clothes",
            "model_used": "SDXL",
        },
        {
            "version_number": 3,
            "prompt_used": "battle mode, armor",
            "model_used": "SDXL",
        },
    ]

    for data in versions_data:
        version = AssetVersion(
            id=str(uuid4()),
            asset_node_id=test_asset.id,
            **data,
        )
        db_session.add(version)

    await db_session.commit()

    # 验证所有版本创建成功
    versions = (
        await db_session.query(AssetVersion)
        .filter(AssetVersion.asset_node_id == test_asset.id)
        .all()
    )
    assert len(versions) == 3


@pytest.mark.asyncio
async def test_version_with_lineage(db_session, test_asset):
    """测试版本谱系信息"""
    version = AssetVersion(
        id=str(uuid4()),
        asset_node_id=test_asset.id,
        version_number=1,
        lineage_json={
            "chain": [
                {"asset_id": "prompt_001", "type": "text", "role": "positive_prompt"},
                {"asset_id": "model_sdxl", "type": "model", "role": "checkpoint"},
                {"asset_id": "lora_cyber", "type": "model", "role": "lora", "weight": 0.8},
            ],
            "compute": {
                "engine": "ComfyUI",
                "workflow_id": "wf_001",
                "gpu": "RTX 4090",
                "duration_seconds": 12.5,
            },
        },
    )

    db_session.add(version)
    await db_session.commit()
    await db_session.refresh(version)

    assert len(version.lineage_json["chain"]) == 3
    assert version.lineage_json["compute"]["engine"] == "ComfyUI"


@pytest.mark.asyncio
async def test_version_with_representations(db_session, test_asset):
    """测试版本包含多个文件表示"""
    version = AssetVersion(
        id=str(uuid4()),
        asset_node_id=test_asset.id,
        version_number=1,
    )
    db_session.add(version)
    await db_session.commit()

    # 添加多个 Representation
    representations = [
        {
            "file_path": "/data/original.png",
            "mime_type": "image/png",
            "file_size": 4096000,
            "width": 4096,
            "height": 4096,
        },
        {
            "file_path": "/data/preview.webp",
            "mime_type": "image/webp",
            "file_size": 512000,
            "width": 512,
            "height": 512,
        },
        {
            "file_path": "/data/thumbnail.jpg",
            "mime_type": "image/jpeg",
            "file_size": 51200,
            "width": 256,
            "height": 256,
        },
    ]

    for rep_data in representations:
        rep = AssetRepresentation(
            id=str(uuid4()),
            asset_version_id=version.id,
            **rep_data,
        )
        db_session.add(rep)

    await db_session.commit()

    # 验证所有表示创建成功
    reps = (
        await db_session.query(AssetRepresentation)
        .filter(AssetRepresentation.asset_version_id == version.id)
        .all()
    )
    assert len(reps) == 3

    # 验证尺寸
    original = next(r for r in reps if r.width == 4096)
    assert original.file_path == "/data/original.png"


@pytest.mark.asyncio
async def test_version_number_auto_increment(db_session, test_asset):
    """测试版本号自动递增逻辑"""
    # 获取当前最大版本号
    max_version = (
        await db_session.query(AssetVersion)
        .filter(AssetVersion.asset_node_id == test_asset.id)
        .order_by(AssetVersion.version_number.desc())
        .first()
    )

    next_version = (max_version.version_number + 1) if max_version else 1

    new_version = AssetVersion(
        id=str(uuid4()),
        asset_node_id=test_asset.id,
        version_number=next_version,
    )

    db_session.add(new_version)
    await db_session.commit()

    assert new_version.version_number == 1  # 第一个版本


@pytest.mark.asyncio
async def test_version_delete(db_session, test_asset):
    """测试删除版本"""
    version = AssetVersion(
        id=str(uuid4()),
        asset_node_id=test_asset.id,
        version_number=1,
    )

    db_session.add(version)
    await db_session.commit()

    # 删除
    await db_session.delete(version)
    await db_session.commit()

    # 验证已删除
    result = await db_session.get(AssetVersion, version.id)
    assert result is None
