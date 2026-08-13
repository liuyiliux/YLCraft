"""YLCraft database layer.

PostgreSQL + pgvector async database access using asyncpg and SQLModel.
Schema changes belong to Alembic; startup and request paths are read-only.
"""

from __future__ import annotations

import contextlib
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session as SQLModelSession
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

logger = logging.getLogger("ylcraft.db")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://ylcraft:ylcraft_dev@localhost:5432/ylcraft",
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=5,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True,
    pool_reset_on_return="rollback",
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=SQLModelAsyncSession,
    expire_on_commit=False,
)

SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "")
sync_engine = create_engine(
    SYNC_DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=5,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True,
    pool_reset_on_return="rollback",
)

SessionLocal = sessionmaker(
    class_=SQLModelSession,
    autocommit=False,
    autoflush=False,
    bind=sync_engine,
)


def _rollback_on_invalidate(dbapi_connection, connection_record, exception):
    """Clear DBAPI transaction state before an invalidated connection is discarded."""
    try:
        dbapi_connection.rollback()
    except Exception:
        pass


event.listen(engine.sync_engine, "invalidate", _rollback_on_invalidate)
event.listen(sync_engine, "invalidate", _rollback_on_invalidate)


async def init_db():
    """Report Alembic state at startup without mutating the schema."""
    try:
        async with engine.connect() as conn:
            revision = (
                await conn.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one_or_none()
    except Exception as error:
        logger.error(
            "Database migration state unavailable; run Alembic upgrade head: %s",
            error,
        )
        return

    expected = "011_add_model3d_generation_tasks"
    if revision == expected:
        logger.info("Database migration state is current: %s", revision)
    else:
        logger.warning(
            "Database revision is %s; expected %s. No schema changes were applied.",
            revision or "<none>",
            expected,
        )


async def ensure_agent_tables():
    """Deprecated non-mutating compatibility hook for legacy callers."""
    return None


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[SAAsyncSession, None]:
    """Yield an async session and roll back safely if the caller fails."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            with contextlib.suppress(Exception):
                await session.rollback()
            raise


async def get_async_session_dependency() -> AsyncGenerator[SAAsyncSession, None]:
    """FastAPI dependency wrapper for the async session context manager."""
    async with get_async_session() as session:
        yield session


def get_session():
    """Yield a synchronous session and roll back safely if the caller fails."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        with contextlib.suppress(Exception):
            db.rollback()
        raise
    finally:
        db.close()
