"""Shared test isolation for database-backed legacy tests."""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy import JSON, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from pgvector.sqlalchemy import Vector
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.asset_hub import (
    AIModel,
    AssetEmbedding,
    AssetNode,
    AssetRelation,
    AssetRepresentation,
    AssetTagLink,
    AssetVersion,
    Tag,
)


class _LegacyQuery:
    """Small SQLAlchemy 1.x query adapter for unchanged legacy tests."""

    def __init__(self, session, model):
        self.session = session
        self.statement = select(model)

    def filter(self, *conditions):
        self.statement = self.statement.where(*conditions)
        return self

    def order_by(self, *expressions):
        self.statement = self.statement.order_by(*expressions)
        return self

    async def all(self):
        result = await self.session.execute(self.statement)
        return result.scalars().all()

    async def first(self):
        result = await self.session.execute(self.statement.limit(1))
        return result.scalars().first()


class _AssetHubTestSession(AsyncSession):
    def query(self, model):
        return _LegacyQuery(self, model)


@pytest_asyncio.fixture(autouse=True)
async def isolated_asset_hub_database(request, tmp_path, monkeypatch):
    """Run the four legacy Asset Hub CRUD modules against disposable SQLite.

    Those tests historically imported the production session factory directly.
    Keeping the override scoped by module prevents them from touching the remote
    PostgreSQL database while leaving application configuration unchanged.
    """
    database_modules = {
        "tests.test_asset_hub_node",
        "tests.test_asset_hub_relation",
        "tests.test_asset_hub_tags",
        "tests.test_asset_hub_version",
        "tests.test_service_delete_cascades",
    }
    if request.module.__name__ not in database_modules:
        yield
        return

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'asset-hub.db'}")
    tables = (
        AssetNode.__table__,
        AssetVersion.__table__,
        AssetRepresentation.__table__,
        AssetEmbedding.__table__,
        AssetRelation.__table__,
        AIModel.__table__,
        Tag.__table__,
        AssetTagLink.__table__,
    )
    original_types = {}
    for table in tables:
        for column in table.columns:
            original_types[column] = column.type
            # 说明：UUID 列已改用跨方言的 GUID（见 app/db/types.py），
            # Python 侧统一吃 str，SQLite 落 CHAR(36)，因此这里**不再**替换 UUID 列。
            # 此前用「临时把列类型改成 String(36)」绕过，会让"替换前已编译过的语句"
            # 继续用旧类型（Uuid 的 value.hex），表现为单独跑通过、与其它模块一起跑失败。
            # JSONB / Vector 在 SQLite 上没有对应实现，仍需临时降级为 JSON。
            if column.name in {
                "metadata_json",
                "tags_json",
                "params_json",
                "lineage_json",
                "context_json",
                "extra_json",
            } or isinstance(column.type, JSONB):
                column.type = JSON()
            elif isinstance(column.type, Vector):
                column.type = JSON()

    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: AssetNode.metadata.create_all(
                sync_connection, tables=list(tables)
            )
        )

    session_factory = sessionmaker(
        engine,
        class_=_AssetHubTestSession,
        expire_on_commit=False,
    )
    monkeypatch.setattr(request.module, "AsyncSessionLocal", lambda: session_factory())
    try:
        yield
    finally:
        for column, column_type in original_types.items():
            column.type = column_type
        await engine.dispose()
