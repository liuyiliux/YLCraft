"""服务层删除路径的外键级联回归测试。

背景：主/子表之间没有 relationship() 时，SQLAlchemy UoW 的跨表读写顺序不可靠
（实测：DELETE 可能先发主行、INSERT 的关联行可能先于被引用行发出），
PG（FK = NO ACTION）上表现为 IntegrityError → 接口 500。

服务侧修复 = 分层 flush（引用行先落库再删/插主行）；这里的测试固定该行为：
标签部分走 conftest 的隔离夹具（sqlite + 类型替换），角色部分用独立内存库并
显式开启 PRAGMA foreign_keys 复现同一约束。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.db.database import AsyncSessionLocal
from app.db.models.asset_hub import (
    AssetNode,
    AssetTagLink,
    AssetType,
    Tag,
)


@pytest_asyncio.fixture
async def db_session():
    """conftest 的隔离夹具会替换本模块的 AsyncSessionLocal（sqlite + 类型替换）。"""
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# 角色删除：character_relationships 双向外键（独立内存库 + FK 强制）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_character_delete_removes_relationships_both_directions(tmp_path):
    from app.db.models.character import Character, CharacterRelationship
    from app.services.character.service import CharacterService

    engine = create_async_engine("sqlite+aiosqlite://")

    @event.listens_for(engine.sync_engine, "connect")
    def _turn_on_fk(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sc: Character.metadata.create_all(
                sc, tables=[Character.__table__, CharacterRelationship.__table__]
            )
        )
    factory = sessionmaker(
        engine, class_=SQLModelAsyncSession, expire_on_commit=False
    )
    try:
        async with factory() as session:
            session.add_all(
                [
                    Character(id="char-a", name="福贵"),
                    Character(id="char-b", name="家珍"),
                    Character(id="char-c", name="龙二"),
                    CharacterRelationship(
                        id=str(uuid4()), character_id="char-a", related_character_id="char-b"
                    ),
                    CharacterRelationship(
                        id=str(uuid4()), character_id="char-c", related_character_id="char-a"
                    ),
                ]
            )
            await session.commit()

        async with factory() as session:
            service = CharacterService(session)
            assert await service.delete("char-a") is True
            await session.commit()  # 服务只负责 flush，提交由调用方完成

        async with factory() as session:
            rows = (
                (
                    await session.execute(
                        select(CharacterRelationship).where(
                            (CharacterRelationship.character_id == "char-a")
                            | (CharacterRelationship.related_character_id == "char-a")
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert rows == []  # 双向关系都被清理
            assert await session.get(Character, "char-a") is None
            assert await session.get(Character, "char-b") is not None
            assert await session.get(Character, "char-c") is not None
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# 标签删除：asset_tag_links.tag_id 外键（级联清后代链接；非级联清自身链接）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tag_cascade_delete_removes_descendant_links(db_session):
    """级联删除标签：自身与后代的关联行都要先清（FK NO ACTION）。"""
    parent = Tag(id=str(uuid4()), name="风格", level=0, path="root/风格")
    child = Tag(id=str(uuid4()), name="水墨", level=1, path="root/风格/水墨", parent_id=parent.id)
    node = AssetNode(id=str(uuid4()), name="n", asset_type=AssetType.IMAGE)
    # 分层写入：先父行 flush 再插关联行（跨表插入顺序对无 relationship 的表不可靠）
    db_session.add_all([parent, child, node])
    await db_session.flush()
    db_session.add_all(
        [
            AssetTagLink(id=str(uuid4()), tag_id=child.id, asset_node_id=node.id),
            AssetTagLink(id=str(uuid4()), tag_id=parent.id, asset_node_id=node.id),
        ]
    )
    await db_session.commit()

    from app.services.tag.service import TagService

    service = TagService(db_session)
    assert await service.delete_tag(parent.id, cascade=True) is True
    await db_session.commit()

    links = (await db_session.execute(select(AssetTagLink))).scalars().all()
    assert links == []  # 父与子标签的关联行都被清理
    tags = (await db_session.execute(select(Tag))).scalars().all()
    assert tags == []  # 父与子标签都被删除


@pytest.mark.asyncio
async def test_tag_non_cascade_delete_removes_own_link_and_reroots_child(db_session):
    """非级联删除：自身关联行清理、子标签变根。"""
    parent = Tag(id=str(uuid4()), name="风格", level=0, path="root/风格")
    child = Tag(id=str(uuid4()), name="水墨", level=1, path="root/风格/水墨", parent_id=parent.id)
    node = AssetNode(id=str(uuid4()), name="n", asset_type=AssetType.IMAGE)
    db_session.add_all([parent, child, node])
    await db_session.flush()
    db_session.add_all(
        [
            AssetTagLink(id=str(uuid4()), tag_id=parent.id, asset_node_id=node.id),
        ]
    )
    await db_session.commit()

    from app.services.tag.service import TagService

    service = TagService(db_session)
    assert await service.delete_tag(parent.id, cascade=False) is True
    await db_session.commit()

    links = (await db_session.execute(select(AssetTagLink))).scalars().all()
    assert links == []  # 被删标签自身的关联行已清理
    child = (await db_session.execute(select(Tag))).scalars().first()
    assert child is not None and child.parent_id is None  # 子标签变根
