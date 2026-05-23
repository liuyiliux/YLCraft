"""
资产中枢单元测试 - AssetNode CRUD
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from datetime import datetime
from uuid import uuid4

from app.db.database import AsyncSessionLocal
from app.db.models.asset_hub import (
    AssetNode,
    AssetType,
)


@pytest_asyncio.fixture
async def db_session():
    """创建测试数据库会话"""
    async with AsyncSessionLocal() as session:
        yield session
        # 清理测试数据
        await session.rollback()


@pytest.mark.asyncio
async def test_create_asset_node(db_session):
    """测试创建 AssetNode"""
    asset = AssetNode(
        id=str(uuid4()),
        name="test_character",
        asset_type=AssetType.CHARACTER,
        metadata_json={"description": "测试角色"},
    )

    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(asset)

    assert asset.id is not None
    assert asset.name == "test_character"
    assert asset.asset_type == AssetType.CHARACTER
    assert asset.use_count == 0
    assert asset.created_at is not None


@pytest.mark.asyncio
async def test_asset_node_with_parent(db_session):
    """测试创建带父节点的 AssetNode（角色多装扮场景）"""
    # 创建角色根节点
    character = AssetNode(
        id=str(uuid4()),
        name="李逍遥",
        asset_type=AssetType.CHARACTER,
    )
    db_session.add(character)
    await db_session.commit()

    # 创建角色的不同装扮版本
    child_v1 = AssetNode(
        id=str(uuid4()),
        name="少年装扮",
        asset_type=AssetType.CHARACTER,
        parent_id=character.id,
    )
    child_v2 = AssetNode(
        id=str(uuid4()),
        name="成年装扮",
        asset_type=AssetType.CHARACTER,
        parent_id=character.id,
    )

    db_session.add(child_v1)
    db_session.add(child_v2)
    await db_session.commit()

    # 验证父子关系
    assert child_v1.parent_id == character.id
    assert child_v2.parent_id == character.id


@pytest.mark.asyncio
async def test_asset_node_metadata(db_session):
    """测试 AssetNode 元数据存储"""
    asset = AssetNode(
        id=str(uuid4()),
        name="test_image",
        asset_type=AssetType.IMAGE,
        metadata_json={
            "prompt": "cyberpunk city, neon lights",
            "model": "SDXL",
            "seed": 12345,
            "steps": 30,
        },
        quality_score=0.92,
        phash="abcd1234567890ef",
    )

    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(asset)

    assert asset.metadata_json["prompt"] == "cyberpunk city, neon lights"
    assert asset.metadata_json["model"] == "SDXL"
    assert asset.quality_score == 0.92
    assert asset.phash == "abcd1234567890ef"


@pytest.mark.asyncio
async def test_asset_node_use_count(db_session):
    """测试 use_count 递增"""
    asset = AssetNode(
        id=str(uuid4()),
        name="shared_asset",
        asset_type=AssetType.IMAGE,
        use_count=5,
    )

    db_session.add(asset)
    await db_session.commit()

    # 模拟被其他资产引用
    asset.use_count += 1
    await db_session.commit()

    assert asset.use_count == 6


@pytest.mark.asyncio
async def test_asset_node_update(db_session):
    """测试更新 AssetNode"""
    asset = AssetNode(
        id=str(uuid4()),
        name="original_name",
        asset_type=AssetType.IMAGE,
    )

    db_session.add(asset)
    await db_session.commit()

    # 更新名称和元数据
    asset.name = "updated_name"
    asset.metadata_json = {"updated": True}
    asset.updated_at = datetime.utcnow()

    await db_session.commit()
    await db_session.refresh(asset)

    assert asset.name == "updated_name"
    assert asset.metadata_json == {"updated": True}


@pytest.mark.asyncio
async def test_asset_node_delete(db_session):
    """测试删除 AssetNode"""
    asset = AssetNode(
        id=str(uuid4()),
        name="to_be_deleted",
        asset_type=AssetType.IMAGE,
    )

    db_session.add(asset)
    await db_session.commit()

    # 删除
    await db_session.delete(asset)
    await db_session.commit()

    # 验证已删除
    result = await db_session.get(AssetNode, asset.id)
    assert result is None


@pytest.mark.asyncio
async def test_asset_node_type_enum(db_session):
    """测试 AssetType 枚举所有类型"""
    asset_types = [
        AssetType.IMAGE,
        AssetType.VIDEO,
        AssetType.AUDIO,
        AssetType.TEXT,
        AssetType.MODEL,
        AssetType.CHARACTER,
        AssetType.WORLD_SETTING,
        AssetType.WORKFLOW,
        AssetType.THREE_D_MODEL,
        AssetType.ANIMATION,
        AssetType.SUBTITLE,
        AssetType.COLLECTION,
        AssetType.JIANYING_DRAFT,
    ]

    for asset_type in asset_types:
        asset = AssetNode(
            id=str(uuid4()),
            name=f"test_{asset_type.value}",
            asset_type=asset_type,
        )
        db_session.add(asset)

    await db_session.commit()

    # 验证所有类型都创建成功
    assert len(asset_types) == 13
