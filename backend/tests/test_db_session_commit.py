"""回归：`get_async_session` 退出时必须**提交已 flush 的写入**。

## 踩过的坑（用户实测）

"合成后点存入素材库显示成功，再查素材库怎么看不到。"

查下来：接口返回 `success: true` 并给了 `node_id`，但**数据库里根本没有这条记录**。

根因在会话上下文管理器的"是否需要 COMMIT"判据：

```python
# ❌ 旧代码
if not (session.new or session.dirty or session.deleted):
    await session.rollback()
    return
```

`session.new/dirty/deleted` 是 **ORM 的变更跟踪集合**，而 **`flush()` 会把对象
从这些集合里挪走**（写进事务、变成 persistent）。服务层普遍是
`session.add(obj)` 紧跟 `session.flush()` —— 于是退出时三个集合**全空**，
被判成"没有写入"→ **`rollback()` 把已写入的数据丢掉**，接口照常返回成功。

实测复现：`new=0 dirty=0 deleted=0`，退出后 `rows in DB = 0`。

**为什么危害大**：这是所有走 `get_async_session()` 的写路径的公共依赖
（全仓 129 处调用）。判据错一次，**每一处写入都可能静默丢失**，
而且不报错、不回滚报异常、日志干净。

## 正确判据

`session.in_transaction()` —— `flush()` 会开启事务，只读查询不会。
既保住"只读不发 COMMIT"这个优化，又不会丢掉 flush 过的写入。

## 测法

用**内存 SQLite** 自建引擎 + 手写最小 DDL，不依赖远程 PostgreSQL。
用 `session.execute(text(...))` 驱动写入 —— 本文件验证的是**会话提交语义**，
不是 ORM 映射，所以不引入 `AssetNode`（它的 JSONB/Vector 列在 SQLite 上渲染不了）。
"""
from __future__ import annotations

import contextlib
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DDL = (
    "create table probe_rows ("
    " id integer primary key autoincrement,"
    " name varchar(64) not null"
    ")"
)


@pytest.fixture
async def session_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'session.db'}")
    async with engine.begin() as conn:
        await conn.execute(text(DDL))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@asynccontextmanager
async def _session_ctx(factory):
    """**与 `get_async_session` 同构**的上下文管理器。

    复刻而非直接调用：`get_async_session` 绑定全局 `AsyncSessionLocal`
    （指向远程 PostgreSQL），测试里无法替换成 sqlite。
    下方 `TestProductionCriteriaMatchesTest` 会静态比对生产实现的判据，
    防止两边漂移。
    """
    async with factory() as session:
        try:
            yield session
            if not session.in_transaction():
                return
            await session.commit()
        except Exception:
            with contextlib.suppress(Exception):
                await session.rollback()
            raise


async def _count(factory, name: str) -> int:
    async with factory() as s:
        return (await s.execute(
            text("select count(*) from probe_rows where name=:n"), {"n": name}
        )).scalar_one()


class TestFlushedWritesAreCommitted:
    """"先执行语句再 flush"是最常见的写法，必须能提交。"""

    async def test_raw_statement_after_flush_is_committed(self, session_factory):
        """写过语句并 flush 之后退出上下文，数据必须真的落库。

        这正是线上那条路径的形状：服务层写库 → flush → 会话退出时被误判
        "没有写入" → rollback → 接口仍返回 success。
        """
        async with _session_ctx(session_factory) as s:
            await s.execute(text("insert into probe_rows (name) values ('flushed')"))
            # ⚠️ flush 会把写入落进事务；旧判据看的 new/dirty/deleted 此时全空
            await s.flush()

        assert await _count(session_factory, "flushed") == 1, (
            "flush 过的写入被回滚了 —— 接口会返回 success 但数据不在库中。"
            " 判据必须用 in_transaction() 而不是 session.new/dirty/deleted"
        )

    async def test_write_without_explicit_flush_is_committed(self, session_factory):
        async with _session_ctx(session_factory) as s:
            await s.execute(text("insert into probe_rows (name) values ('autoflush')"))
        assert await _count(session_factory, "autoflush") == 1

    async def test_exception_still_rolls_back(self, session_factory):
        """出错必须回滚 —— 修 COMMIT 判据不能把回滚语义弄丢。"""
        with pytest.raises(RuntimeError):
            async with _session_ctx(session_factory) as s:
                await s.execute(text("insert into probe_rows (name) values ('rollback')"))
                await s.flush()
                raise RuntimeError("故意失败")

        assert await _count(session_factory, "rollback") == 0, "异常路径必须回滚"

    async def test_read_only_session_is_fine(self, session_factory):
        """只读路径仍要正常工作（"只读不发 COMMIT"这个优化不能被弄坏）。"""
        async with _session_ctx(session_factory) as s:
            n = (await s.execute(text("select count(*) from probe_rows"))).scalar_one()
        assert n == 0

    async def test_transaction_survives_flush(self, session_factory):
        """证明坑的来源：flush 之后 ORM 变更集合为空，但事务仍开着。

        如果哪天 SQLAlchemy 改了行为，这条会先红，提醒重新评估判据。
        """
        async with session_factory() as s:
            await s.execute(text("insert into probe_rows (name) values ('x')"))
            await s.flush()
            assert not s.new and not s.dirty and not s.deleted, (
                "这里期望三个集合全空 —— 旧判据正是因此误判'没有写入'"
            )
            assert s.in_transaction(), "但事务是开着的，这才是可靠信号"


class TestProductionCriteriaMatchesTest:
    """防止本文件复刻的判据与生产实现漂移。"""

    def test_production_uses_in_transaction_not_change_tracking(self):
        import inspect

        from app.db import database

        src = inspect.getsource(database.get_async_session)
        assert "in_transaction()" in src, "生产实现必须用 in_transaction() 判据"
        assert "session.new or session.dirty or session.deleted" not in src, (
            "生产实现又用回了 new/dirty/deleted —— flush 之后它们全空，"
            "会把已写入的数据 rollback 掉（接口却返回 success）"
        )
