"""
YLCraft — 数据库模块

PostgreSQL + pgvector 异步数据库层（使用 asyncpg + SQLModel）。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator
import logging
import os

logger = logging.getLogger("ylcraft.db")

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession as SAAsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, text
from sqlmodel import SQLModel, Session as SQLModelSession
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

# 异步数据库配置
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://ylcraft:ylcraft_dev@localhost:5432/ylcraft")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=5,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True,
)

AsyncSessionLocal = sessionmaker(
    engine, class_=SQLModelAsyncSession, expire_on_commit=False
)

# 同步数据库配置（用于 init_manager 等同步上下文）
SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "")
sync_engine = create_engine(
    SYNC_DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=5,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    class_=SQLModelSession,
    autocommit=False, autoflush=False, bind=sync_engine
)


async def init_db():
    """初始化数据库表"""
    from app.db.models.asset import Asset, AssetCollection, AssetTag
    from app.db.models.torrent import TorrentDownload
    from app.db.models.character import Character, CharacterStoryLink
    from app.db.models.live2d import Live2DModel, Live2DBone, Live2DMotion
    from app.db.models.api_key import ApiKey
    from app.db.models.agent import AgentSession, AgentMemory, AgentSkill, AgentToolCall
    from app.db.models.platform_connection import PlatformConnection  # 统一凭证模型
    from app.db.models.ai_connector import AIConnector, AIUsageLog  # AI 连接器
    from app.db.models.comfyui import WorkflowTemplate, WorkflowPreset, ComfyUITask, ComfyUINode
    from app.db.models.book_source import BookSource  # 书源表
    from app.db.models.book_source_cookie import BookSourceCookie

    # 0. 同步 PG 枚举（在 create_all 之前；ADD VALUE 不能在事务内执行，所以用独立连接）
    if DATABASE_URL.startswith("postgresql"):
        await _sync_pg_enums()

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        if DATABASE_URL.startswith("postgresql"):
            await conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'assets'
                          AND column_name = 'file_size'
                          AND data_type <> 'bigint'
                    ) THEN
                        ALTER TABLE assets ALTER COLUMN file_size TYPE BIGINT;
                    END IF;
                END $$;
            """))


# 平台/认证/状态/获取方式枚举需要与 SQLModel 同步
# 键是 PG 枚举类型名（小写），值是所有合法的枚举值（小写）
_PG_ENUM_VALUES: dict[str, list[str]] = {
    "platformtype": [
        "xhs", "douyin", "kuaishou", "bilibili", "weibo", "zhihu",
        "youtube", "tiktok", "twitter", "telegram", "wechat_mp",
        "openai", "anthropic", "minimax", "google", "webdav", "s3", "ftp",
    ],
    "authtype": ["cookie", "api_key", "oauth2", "password", "none"],
    "connectionstatus": ["active", "expired", "failed", "unknown"],
    "acquisitionmethod": ["manual", "playwright", "qrcode"],
}


async def _sync_pg_enums():
    """
    同步 PostgreSQL 枚举类型与 SQLModel 定义。

    对于 _PG_ENUM_VALUES 中列出的每个枚举类型：
    1. 如果类型不存在 → CREATE TYPE（包含全部值）
    2. 如果类型已存在 → 对比已有值，ALTER TYPE ADD VALUE 补齐缺失值

    PG 限制：ALTER TYPE ADD VALUE 不能在事务块内执行；
    所以本函数使用 SQLAlchemy 的 AUTOCOMMIT 隔离级别。
    """
    # 用 autocommit 隔离级别避开事务限制
    # SQLAlchemy 2.0+ 语法：先获取连接，再设置 isolation_level
    conn = await engine.connect()
    try:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await _do_sync_pg_enums(conn)
    finally:
        await conn.close()


async def _do_sync_pg_enums(conn):
    for type_name, values in _PG_ENUM_VALUES.items():
        # 1. 检查类型是否存在
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_type WHERE typname = :t"),
            {"t": type_name},
        )
        if not exists:
            # 2a. 创建类型
            values_sql = ", ".join(f"'{v}'" for v in values)
            await conn.execute(
                text(f"CREATE TYPE {type_name} AS ENUM ({values_sql})")
            )
            logger.info(f"[init_db] Created enum type {type_name} with {len(values)} values")
            continue

        # 2b. 类型已存在 → 补齐缺失值
        existing = {
            r[0]
            for r in await conn.execute(
                text(
                    "SELECT enumlabel FROM pg_enum "
                    "WHERE enumtypid = (:t)::regtype ORDER BY enumsortorder"
                ),
                {"t": type_name},
            )
        }
        missing = [v for v in values if v not in existing]
        for v in missing:
            # IF NOT EXISTS 在 PG 12+ 支持
            await conn.execute(
                text(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{v}'")
            )
            logger.info(f"[init_db] Added enum value {type_name}.{v}")


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[SAAsyncSession, None]:
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
