"""
YLCraft — 数据库模块

SQLite 异步数据库层（使用 aiosqlite + SQLModel）。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from sqlmodel import SQLModel

# 动态数据库路径（兼容 Windows / Linux / macOS）
_DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_DB_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _DB_DIR / "ylcraft.db"

# 异步数据库配置
DATABASE_URL = f"sqlite+aiosqlite:///{_DB_PATH}"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# 同步数据库配置（用于 init_manager 等同步上下文）
SYNC_DATABASE_URL = f"sqlite:///{_DB_PATH}"
sync_engine = create_engine(
    SYNC_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=sync_engine
)


async def init_db():
    """初始化数据库表"""
    from app.db.models.asset import Asset, AssetCollection, AssetTag
    from app.db.models.character import Character, CharacterStoryLink
    from app.db.models.live2d import Live2DModel, Live2DBone, Live2DMotion
    from app.db.models.api_key import ApiKey
    from app.db.models.agent import AgentSession, AgentMemory, AgentSkill, AgentToolCall
    from app.db.models.platform_connection import PlatformConnection  # 旧版（兼容）
    from app.db.models.ai_connector import AIConnector, AIUsageLog  # 新版 AI 连接器
    from app.db.models.social_media_connector import SocialMediaConnector  # 新版社交媒体连接器
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
