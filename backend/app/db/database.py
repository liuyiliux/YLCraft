"""
YLCraft — 数据库模块

PostgreSQL + pgvector 异步数据库层（使用 asyncpg + SQLModel）。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator
import os

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session as SQLModelSession

# 异步数据库配置
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://ylcraft:ylcraft_dev@localhost:5432/ylcraft")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=10,
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# 同步数据库配置（用于 init_manager 等同步上下文）
SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "")
sync_engine = create_engine(
    SYNC_DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=10,
)

SessionLocal = sessionmaker(
    class_=SQLModelSession,
    autocommit=False, autoflush=False, bind=sync_engine
)


async def init_db():
    """初始化数据库表"""
    from app.db.models.asset import Asset, AssetCollection, AssetTag
    from app.db.models.character import Character, CharacterStoryLink
    from app.db.models.live2d import Live2DModel, Live2DBone, Live2DMotion
    from app.db.models.api_key import ApiKey
    from app.db.models.agent import AgentSession, AgentMemory, AgentSkill, AgentToolCall
    from app.db.models.platform_connection import PlatformConnection  # 统一凭证模型
    from app.db.models.ai_connector import AIConnector, AIUsageLog  # AI 连接器
    from app.db.models.comfyui import WorkflowTemplate, WorkflowPreset, ComfyUITask, ComfyUINode
    from app.db.models.book_source import BookSource  # 书源表
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """获取异步数据库会话（用于需要 async 的场景）"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_session():
    """获取同步数据库会话（用于 SQLModel 同步操作）"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
