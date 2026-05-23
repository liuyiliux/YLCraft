"""
资产中枢单元测试 - 资产关系和谱系
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from uuid import uuid4

from app.db.database import AsyncSessionLocal
from app.db.models.asset_hub import (
    AssetNode,
    AssetType,
    AssetRelation,
    RelationType,
)


@pytest_asyncio.fixture
async def db_session():
    """创建测试数据库会话"""
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.mark.asyncio
async def test_create_asset_relation(db_session):
    """测试创建资产关系"""
    # 创建源资产
    source = AssetNode(
        id=str(uuid4()),
        name="prompt_text",
        asset_type=AssetType.TEXT,
    )
    db_session.add(source)

    # 创建目标资产
    target = AssetNode(
        id=str(uuid4()),
        name="generated_image",
        asset_type=AssetType.IMAGE,
    )
    db_session.add(target)

    await db_session.commit()

    # 创建关系
    relation = AssetRelation(
        id=str(uuid4()),
        source_id=source.id,
        target_id=target.id,
        relation_type=RelationType.DERIVED_FROM,
    )
    db_session.add(relation)
    await db_session.commit()

    assert relation.source_id == source.id
    assert relation.target_id == target.id
    assert relation.relation_type == RelationType.DERIVED_FROM


@pytest.mark.asyncio
async def test_lineage_chain(db_session):
    """测试谱系链（Prompt → Model → Output）"""
    # 创建谱系链
    # prompt → model → lora → output_image

    prompt = AssetNode(
        id=str(uuid4()),
        name="cyberpunk_city_prompt",
        asset_type=AssetType.TEXT,
    )
    db_session.add(prompt)

    model = AssetNode(
        id=str(uuid4()),
        name="SDXL_Checkpoint",
        asset_type=AssetType.MODEL,
    )
    db_session.add(model)

    lora = AssetNode(
        id=str(uuid4()),
        name="Cyberpunk_LoRA",
        asset_type=AssetType.MODEL,
    )
    db_session.add(lora)

    output = AssetNode(
        id=str(uuid4()),
        name="cyberpunk_city_v1",
        asset_type=AssetType.IMAGE,
    )
    db_session.add(output)

    await db_session.commit()

    # 创建关系链
    relations = [
        AssetRelation(
            id=str(uuid4()),
            source_id=model.id,
            target_id=output.id,
            relation_type=RelationType.USES,
            context_json={"role": "checkpoint"},
        ),
        AssetRelation(
            id=str(uuid4()),
            source_id=lora.id,
            target_id=output.id,
            relation_type=RelationType.USES,
            context_json={"role": "lora", "weight": 0.8},
        ),
        AssetRelation(
            id=str(uuid4()),
            source_id=prompt.id,
            target_id=output.id,
            relation_type=RelationType.DERIVED_FROM,
        ),
    ]

    for rel in relations:
        db_session.add(rel)

    await db_session.commit()

    # 验证关系数量
    output_relations = (
        await db_session.query(AssetRelation)
        .filter(AssetRelation.target_id == output.id)
        .all()
    )
    assert len(output_relations) == 3


@pytest.mark.asyncio
async def test_relation_with_context(db_session):
    """测试带上下文的关系"""
    source = AssetNode(
        id=str(uuid4()),
        name="background_video",
        asset_type=AssetType.VIDEO,
    )
    db_session.add(source)

    target = AssetNode(
        id=str(uuid4()),
        name="final_composite",
        asset_type=AssetType.VIDEO,
    )
    db_session.add(target)

    relation = AssetRelation(
        id=str(uuid4()),
        source_id=source.id,
        target_id=target.id,
        relation_type=RelationType.USES,
        context_json={
            "timerange": "0:00-0:30",
            "opacity": 0.5,
            "effects": ["fade_in", "color_correction"],
        },
    )
    db_session.add(relation)
    await db_session.commit()

    assert relation.context_json["timerange"] == "0:00-0:30"
    assert relation.context_json["opacity"] == 0.5


@pytest.mark.asyncio
async def test_all_relation_types(db_session):
    """测试所有关系类型"""
    source = AssetNode(
        id=str(uuid4()),
        name="source_asset",
        asset_type=AssetType.IMAGE,
    )
    db_session.add(source)
    await db_session.commit()

    relation_types = [
        RelationType.DERIVED_FROM,
        RelationType.USES,
        RelationType.REFERENCES,
        RelationType.CONTAINS,
        RelationType.VARIANT_OF,
    ]

    for rel_type in relation_types:
        target = AssetNode(
            id=str(uuid4()),
            name=f"target_{rel_type.value}",
            asset_type=AssetType.IMAGE,
        )
        db_session.add(target)
        await db_session.commit()

        relation = AssetRelation(
            id=str(uuid4()),
            source_id=source.id,
            target_id=target.id,
            relation_type=rel_type,
        )
        db_session.add(relation)

    await db_session.commit()

    # 验证所有关系类型
    relations = (
        await db_session.query(AssetRelation)
        .filter(AssetRelation.source_id == source.id)
        .all()
    )
    assert len(relations) == 5


@pytest.mark.asyncio
async def test_upstream_query(db_session):
    """测试上游查询（查找资产的所有祖先）"""
    # 创建链：prompt → model → output
    prompt = AssetNode(id=str(uuid4()), name="prompt", asset_type=AssetType.TEXT)
    model = AssetNode(id=str(uuid4()), name="model", asset_type=AssetType.MODEL)
    output = AssetNode(id=str(uuid4()), name="output", asset_type=AssetType.IMAGE)

    db_session.add_all([prompt, model, output])
    await db_session.commit()

    # 创建关系
    rel1 = AssetRelation(id=str(uuid4()), source_id=model.id, target_id=output.id, relation_type=RelationType.USES)
    rel2 = AssetRelation(id=str(uuid4()), source_id=prompt.id, target_id=output.id, relation_type=RelationType.DERIVED_FROM)

    db_session.add_all([rel1, rel2])
    await db_session.commit()

    # 查询 output 的所有上游
    upstream = (
        await db_session.query(AssetRelation)
        .filter(AssetRelation.target_id == output.id)
        .all()
    )

    assert len(upstream) == 2
    upstream_ids = [r.source_id for r in upstream]
    assert model.id in upstream_ids
    assert prompt.id in upstream_ids


@pytest.mark.asyncio
async def test_downstream_query(db_session):
    """测试下游查询（查找资产的所有后代）"""
    # 创建链：base → variant1, variant2
    base = AssetNode(id=str(uuid4()), name="base_asset", asset_type=AssetType.IMAGE)
    db_session.add(base)
    await db_session.commit()

    variant1 = AssetNode(id=str(uuid4()), name="variant_1", asset_type=AssetType.IMAGE)
    variant2 = AssetNode(id=str(uuid4()), name="variant_2", asset_type=AssetType.IMAGE)

    db_session.add_all([variant1, variant2])
    await db_session.commit()

    # 创建关系
    rel1 = AssetRelation(id=str(uuid4()), source_id=base.id, target_id=variant1.id, relation_type=RelationType.VARIANT_OF)
    rel2 = AssetRelation(id=str(uuid4()), source_id=base.id, target_id=variant2.id, relation_type=RelationType.VARIANT_OF)

    db_session.add_all([rel1, rel2])
    await db_session.commit()

    # 查询 base 的所有下游
    downstream = (
        await db_session.query(AssetRelation)
        .filter(AssetRelation.source_id == base.id)
        .all()
    )

    assert len(downstream) == 2


@pytest.mark.asyncio
async def test_character_variants(db_session):
    """测试角色变体（同一角色的不同装扮）"""
    # 创建角色根节点
    character = AssetNode(
        id=str(uuid4()),
        name="李逍遥",
        asset_type=AssetType.CHARACTER,
    )
    db_session.add(character)
    await db_session.commit()

    # 创建不同装扮版本
    young = AssetNode(id=str(uuid4()), name="少年装扮", asset_type=AssetType.IMAGE)
    adult = AssetNode(id=str(uuid4()), name="成年装扮", asset_type=AssetType.IMAGE)
    battle = AssetNode(id=str(uuid4()), name="战斗形态", asset_type=AssetType.IMAGE)

    db_session.add_all([young, adult, battle])
    await db_session.commit()

    # 创建关系
    relations = [
        AssetRelation(id=str(uuid4()), source_id=character.id, target_id=young.id, relation_type=RelationType.CONTAINS),
        AssetRelation(id=str(uuid4()), source_id=character.id, target_id=adult.id, relation_type=RelationType.CONTAINS),
        AssetRelation(id=str(uuid4()), source_id=character.id, target_id=battle.id, relation_type=RelationType.CONTAINS),
    ]

    for rel in relations:
        db_session.add(rel)

    await db_session.commit()

    # 查询角色的所有装扮
    costumes = (
        await db_session.query(AssetRelation)
        .filter(AssetRelation.source_id == character.id, AssetRelation.relation_type == RelationType.CONTAINS)
        .all()
    )

    assert len(costumes) == 3
