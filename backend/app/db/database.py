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
from sqlalchemy.exc import DBAPIError
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

    expected = "046_add_user_email_reservation"
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
    """Yield an async session and roll back safely if the caller fails.

    提交只在会话确实动过数据库时发生；只读请求（含 422 校验失败这种在进入
    处理函数前就中断的请求）不往连接上发无意义的 COMMIT。远程数据库偶发
    断连时，提交阶段的连接错误不再盖掉处理函数本身的结果或真正的异常。

    ⚠️ **判据必须是 `in_transaction()`，不能用 `session.new/dirty/deleted`。**
    踩过的坑（用户实测："存入素材库显示成功，再查素材库怎么看不到"）：
    服务层普遍会 `session.add(obj)` 后紧跟 `session.flush()` —— flush 会把对象
    从 `new` 挪走、写进事务，于是退出时三个集合**全空**，
    旧代码据此判定"没有写入"→ **执行 `rollback()` 把已写入的数据丢掉**，
    而接口照常返回 `success: true`。表现为**存了但查不到**，且不报任何错。

    实测复现：`inside: new=0 dirty=0 deleted=0` + `AFTER: rows in DB = 0`。
    正确判据：**只要事务开着就说明有未提交的语句**（`flush` 会开启事务），
    只读查询不会开事务，所以"只读不发 COMMIT"这个优化依然成立。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            # 没有活动事务 = 这次只跑了查询（或什么都没做），无需 COMMIT。
            if not session.in_transaction():
                return
            try:
                await session.commit()
            except (DBAPIError, OSError):
                # 连接在提交途中被断开：回滚并重新抛出让上层看到真实错误
                with contextlib.suppress(Exception):
                    await session.rollback()
                raise
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
