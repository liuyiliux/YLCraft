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
    from app.db.models.torrent import TorrentDownload
    from app.db.models.creative_project import (
        CreativeProject,
        ProjectAssetLink,
        ProjectContent,
        ProjectGenerationLog,
    )
    from app.db.models.character import Character, CharacterStoryLink
    from app.db.models.live2d import Live2DModel, Live2DBone, Live2DMotion
    from app.db.models.api_key import ApiKey
    from app.db.models.agent import AgentSession, AgentThread, AgentMessage, AgentContextSnapshot, AgentMemory, AgentSkill, AgentToolCall, AgentRun, AgentRunStep, AgentMemorySnapshot, AgentProfile
    from app.db.models.platform_connection import PlatformConnection  # 统一凭证模型
    from app.db.models.ai_connector import AIConnector, AIUsageLog  # AI 连接器
    from app.db.models.platform_template import PlatformTemplate
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
                ALTER TABLE platform_templates
                ADD COLUMN IF NOT EXISTS system_template TEXT NOT NULL DEFAULT '';
            """))
            await conn.execute(text("""
                ALTER TABLE platform_templates
                ALTER COLUMN platform TYPE VARCHAR(80);
            """))
            await conn.execute(text("""
                ALTER TABLE character_story_links
                ADD COLUMN IF NOT EXISTS world_id TEXT NOT NULL DEFAULT '',
                ADD COLUMN IF NOT EXISTS world_name TEXT NOT NULL DEFAULT '',
                ADD COLUMN IF NOT EXISTS usage_role TEXT NOT NULL DEFAULT '',
                ADD COLUMN IF NOT EXISTS local_alias TEXT NOT NULL DEFAULT '',
                ADD COLUMN IF NOT EXISTS local_identity TEXT NOT NULL DEFAULT '',
                ADD COLUMN IF NOT EXISTS local_faction TEXT NOT NULL DEFAULT '',
                ADD COLUMN IF NOT EXISTS local_status TEXT NOT NULL DEFAULT 'active',
                ADD COLUMN IF NOT EXISTS local_costume TEXT NOT NULL DEFAULT '',
                ADD COLUMN IF NOT EXISTS local_prompt_tags TEXT NOT NULL DEFAULT '[]',
                ADD COLUMN IF NOT EXISTS ooc_notes TEXT NOT NULL DEFAULT '',
                ADD COLUMN IF NOT EXISTS off_model_notes TEXT NOT NULL DEFAULT '',
                ADD COLUMN IF NOT EXISTS bible_overrides_json TEXT NOT NULL DEFAULT '{}',
                ADD COLUMN IF NOT EXISTS visual_overrides_json TEXT NOT NULL DEFAULT '{}',
                ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();
            """))
            await conn.execute(text("""
                ALTER TABLE characters
                ADD COLUMN IF NOT EXISTS identity_json TEXT NOT NULL DEFAULT '{}',
                ADD COLUMN IF NOT EXISTS motivation_json TEXT NOT NULL DEFAULT '{}',
                ADD COLUMN IF NOT EXISTS speech_json TEXT NOT NULL DEFAULT '{}',
                ADD COLUMN IF NOT EXISTS behavior_json TEXT NOT NULL DEFAULT '{}',
                ADD COLUMN IF NOT EXISTS ability_json TEXT NOT NULL DEFAULT '{}',
                ADD COLUMN IF NOT EXISTS arc_json TEXT NOT NULL DEFAULT '{}';
            """))


async def ensure_agent_tables():
    """Create Agent Center tables on demand.

    This keeps the Agent page usable after code updates even when the server was
    started before the new AgentProfile model existed.
    """
    from app.db.models.agent import AgentSession, AgentThread, AgentMessage, AgentContextSnapshot, AgentMemory, AgentSkill, AgentToolCall, AgentRun, AgentRunStep, AgentMemorySnapshot, AgentProfile

    tables = [
        AgentSession.__table__,
        AgentThread.__table__,
        AgentMessage.__table__,
        AgentContextSnapshot.__table__,
        AgentMemory.__table__,
        AgentSkill.__table__,
        AgentToolCall.__table__,
        AgentRun.__table__,
        AgentRunStep.__table__,
        AgentMemorySnapshot.__table__,
        AgentProfile.__table__,
    ]
    async with engine.begin() as conn:
        for table in tables:
            await conn.run_sync(lambda sync_conn, t=table: t.create(sync_conn, checkfirst=True))
        if conn.dialect.name == "postgresql":
            for ddl in [
                "ALTER TABLE agent_profiles ADD COLUMN IF NOT EXISTS role_type VARCHAR(64) DEFAULT 'assistant'",
                "ALTER TABLE agent_profiles ADD COLUMN IF NOT EXISTS default_project_id VARCHAR(64) DEFAULT ''",
                "ALTER TABLE agent_profiles ADD COLUMN IF NOT EXISTS default_workflow VARCHAR(120) DEFAULT ''",
                "ALTER TABLE agent_profiles ADD COLUMN IF NOT EXISTS default_skill_ids_json TEXT DEFAULT '[]'",
            ]:
                await conn.execute(text(ddl))
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_agent_profiles_role_type "
                    "ON agent_profiles (role_type)"
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_agent_profiles_default_project_id "
                    "ON agent_profiles (default_project_id)"
                )
            )
        elif conn.dialect.name == "sqlite":
            columns = await conn.execute(text("PRAGMA table_info(agent_profiles)"))
            column_names = {row[1] for row in columns.fetchall()}
            sqlite_columns = {
                "role_type": "VARCHAR(64) DEFAULT 'assistant'",
                "default_project_id": "VARCHAR(64) DEFAULT ''",
                "default_workflow": "VARCHAR(120) DEFAULT ''",
                "default_skill_ids_json": "TEXT DEFAULT '[]'",
            }
            for column, column_type in sqlite_columns.items():
                if column not in column_names:
                    await conn.execute(text(f"ALTER TABLE agent_profiles ADD COLUMN {column} {column_type}"))


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


async def get_async_session_dependency() -> AsyncGenerator[SAAsyncSession, None]:
    """FastAPI dependency wrapper for async DB sessions.

    `get_async_session()` is an async context manager used throughout the codebase
    with `async with`. FastAPI Depends needs a plain async generator, otherwise it
    raises: '_AsyncGeneratorContextManager' object is not an async iterator.
    """
    async with get_async_session() as session:
        yield session


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
