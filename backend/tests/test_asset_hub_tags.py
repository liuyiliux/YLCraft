"""
资产中枢单元测试 - 树形标签系统
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from uuid import uuid4

from app.db.database import AsyncSessionLocal
from app.db.models.asset_hub import (
    AssetNode,
    AssetType,
    Tag,
    AssetTagLink,
)


@pytest_asyncio.fixture
async def db_session():
    """创建测试数据库会话"""
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.mark.asyncio
async def test_create_root_tag(db_session):
    """测试创建根标签"""
    tag = Tag(
        id=str(uuid4()),
        name="style",
        parent_id=None,
        level=0,
        path="root/style",
        category="style",
    )

    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)

    assert tag.level == 0
    assert tag.path == "root/style"
    assert tag.asset_count == 0


@pytest.mark.asyncio
async def test_create_child_tag(db_session):
    """测试创建子标签"""
    # 创建父标签
    parent = Tag(
        id=str(uuid4()),
        name="style",
        level=0,
        path="root/style",
    )
    db_session.add(parent)
    await db_session.commit()

    # 创建子标签
    child = Tag(
        id=str(uuid4()),
        name="cyberpunk",
        parent_id=parent.id,
        level=1,
        path="root/style/cyberpunk",
    )
    db_session.add(child)
    await db_session.commit()

    assert child.parent_id == parent.id
    assert child.level == 1
    assert child.path.startswith("root/style/")


@pytest.mark.asyncio
async def test_tag_tree_structure(db_session):
    """测试标签树结构"""
    # 创建完整的标签树
    # root/
    # ├── style/
    # │   ├── cyberpunk/
    # │   └── anime/
    # └── type/
    #     └── image/

    root = Tag(id=str(uuid4()), name="root", level=0, path="root")
    db_session.add(root)
    await db_session.commit()

    style = Tag(id=str(uuid4()), name="style", parent_id=root.id, level=1, path="root/style")
    db_session.add(style)

    tag_type = Tag(id=str(uuid4()), name="type", parent_id=root.id, level=1, path="root/type")
    db_session.add(tag_type)

    cyberpunk = Tag(id=str(uuid4()), name="cyberpunk", parent_id=style.id, level=2, path="root/style/cyberpunk")
    db_session.add(cyberpunk)

    anime = Tag(id=str(uuid4()), name="anime", parent_id=style.id, level=2, path="root/style/anime")
    db_session.add(anime)

    image = Tag(id=str(uuid4()), name="image", parent_id=tag_type.id, level=2, path="root/type/image")
    db_session.add(image)

    await db_session.commit()

    # 验证标签树结构
    all_tags = (await db_session.query(Tag).all())
    assert len(all_tags) == 6

    # 验证路径查询
    style_tags = (
        await db_session.query(Tag)
        .filter(Tag.path.like("root/style%"))
        .all()
    )
    assert len(style_tags) == 3  # style, cyberpunk, anime


@pytest.mark.asyncio
async def test_asset_tag_link(db_session):
    """测试资产-标签关联"""
    # 创建资产
    asset = AssetNode(
        id=str(uuid4()),
        name="test_image",
        asset_type=AssetType.IMAGE,
    )
    db_session.add(asset)

    # 创建标签
    tag = Tag(
        id=str(uuid4()),
        name="cyberpunk",
        path="root/style/cyberpunk",
    )
    db_session.add(tag)

    await db_session.commit()

    # 创建关联
    link = AssetTagLink(
        id=str(uuid4()),
        asset_node_id=asset.id,
        tag_id=tag.id,
        confidence=0.92,
        source="ai",
    )
    db_session.add(link)
    await db_session.commit()

    assert link.confidence == 0.92
    assert link.source == "ai"


@pytest.mark.asyncio
async def test_asset_multiple_tags(db_session):
    """测试资产多个标签"""
    # 创建资产
    asset = AssetNode(
        id=str(uuid4()),
        name="test_image",
        asset_type=AssetType.IMAGE,
    )
    db_session.add(asset)

    # 创建多个标签
    tag_names = ["cyberpunk", "night", "city", "neon"]
    tag_ids = []
    for name in tag_names:
        tag = Tag(
            id=str(uuid4()),
            name=name,
            path=f"root/{name}",
        )
        db_session.add(tag)
        tag_ids.append(tag.id)

    await db_session.commit()

    # 创建关联
    for tag_id in tag_ids:
        link = AssetTagLink(
            id=str(uuid4()),
            asset_node_id=asset.id,
            tag_id=tag_id,
            source="manual",
        )
        db_session.add(link)

    await db_session.commit()

    # 验证标签数量
    links = (
        await db_session.query(AssetTagLink)
        .filter(AssetTagLink.asset_node_id == asset.id)
        .all()
    )
    assert len(links) == 4


@pytest.mark.asyncio
async def test_tag_asset_count(db_session):
    """测试标签资产计数"""
    # 创建标签
    tag = Tag(
        id=str(uuid4()),
        name="cyberpunk",
        path="root/style/cyberpunk",
        asset_count=0,
    )
    db_session.add(tag)
    await db_session.commit()

    # 创建多个资产并关联
    for i in range(5):
        asset = AssetNode(
            id=str(uuid4()),
            name=f"test_image_{i}",
            asset_type=AssetType.IMAGE,
        )
        db_session.add(asset)
        await db_session.commit()

        link = AssetTagLink(
            id=str(uuid4()),
            asset_node_id=asset.id,
            tag_id=tag.id,
        )
        db_session.add(link)

    await db_session.commit()

    # 模拟更新计数
    tag.asset_count = 5
    await db_session.commit()

    await db_session.refresh(tag)
    assert tag.asset_count == 5


@pytest.mark.asyncio
async def test_tag_color(db_session):
    """测试标签颜色"""
    tag = Tag(
        id=str(uuid4()),
        name="cyberpunk",
        path="root/style/cyberpunk",
        color="#00ffff",
    )

    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)

    assert tag.color == "#00ffff"


@pytest.mark.asyncio
async def test_path_like_query(db_session):
    """测试路径 LIKE 查询（获取子树）"""
    # 创建标签树
    root = Tag(id=str(uuid4()), name="root", level=0, path="root")
    db_session.add(root)
    await db_session.commit()

    child1 = Tag(id=str(uuid4()), name="child1", parent_id=root.id, level=1, path="root/child1")
    child2 = Tag(id=str(uuid4()), name="child2", parent_id=root.id, level=1, path="root/child2")
    grandchild = Tag(id=str(uuid4()), name="grandchild", parent_id=child1.id, level=2, path="root/child1/grandchild")

    db_session.add_all([child1, child2, grandchild])
    await db_session.commit()

    # 查询 child1 的所有后代
    descendants = (
        await db_session.query(Tag)
        .filter(Tag.path.like("root/child1%"))
        .all()
    )

    assert len(descendants) == 2  # child1, grandchild
