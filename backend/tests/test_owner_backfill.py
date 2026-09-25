from __future__ import annotations

import pytest
from sqlalchemy import Boolean, Column, Integer, MetaData, String, Table, create_engine, func, insert, select
from sqlalchemy.orm import Session

from app.services.ownership.backfill import (
    OWNER_BACKFILL_TABLES,
    OwnerBackfillInactiveUser,
    OwnerBackfillUserNotFound,
    backfill_owner_user_id,
)


@pytest.fixture()
def schema():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    users = Table(
        "users",
        metadata,
        Column("id", String, primary_key=True),
        Column("username", String, unique=True, nullable=False),
        Column("is_active", Boolean, nullable=False, default=True),
    )
    tables = {}
    for table_name in OWNER_BACKFILL_TABLES:
        tables[table_name] = Table(
            table_name,
            metadata,
            Column("id", Integer, primary_key=True),
            Column("owner_user_id", String, nullable=True),
        )
    metadata.create_all(engine)
    return engine, users, tables


@pytest.fixture()
def session(schema):
    engine, _users, _tables = schema
    with Session(engine) as db:
        yield db


def _seed(schema, session: Session, *, inactive: bool = False) -> None:
    _engine, users, tables = schema
    session.execute(
        insert(users).values(
            id="root-id",
            username="root",
            is_active=not inactive,
        )
    )
    for table_name in OWNER_BACKFILL_TABLES:
        table = tables[table_name]
        session.execute(insert(table).values(id=1, owner_user_id=None))
        session.execute(insert(table).values(id=2, owner_user_id="already-owned"))
    session.commit()


def _null_count(schema, session: Session, table_name: str) -> int:
    _engine, _users, tables = schema
    table = tables[table_name]
    return int(
        session.execute(
            select(func.count()).select_from(table).where(table.c.owner_user_id.is_(None))
        ).scalar_one()
    )


def test_dry_run_reports_null_rows_without_writing(schema, session: Session) -> None:
    _seed(schema, session)

    result = backfill_owner_user_id(session, username="root", apply=False)

    assert result.applied is False
    assert result.total_null_before == len(OWNER_BACKFILL_TABLES)
    assert result.total_updated == 0
    assert result.total_remaining == len(OWNER_BACKFILL_TABLES)
    assert all(_null_count(schema, session, table) == 1 for table in OWNER_BACKFILL_TABLES)


def test_apply_updates_only_null_rows_and_is_idempotent(schema, session: Session) -> None:
    _seed(schema, session)

    first = backfill_owner_user_id(session, username="root", apply=True)
    second = backfill_owner_user_id(session, username="root", apply=True)

    assert first.total_updated == len(OWNER_BACKFILL_TABLES)
    assert first.total_remaining == 0
    assert second.total_null_before == 0
    assert second.total_updated == 0
    _engine, _users, tables = schema
    for table_name in OWNER_BACKFILL_TABLES:
        table = tables[table_name]
        rows = session.execute(select(table).order_by(table.c.id)).mappings().all()
        assert rows[0]["owner_user_id"] == "root-id"
        assert rows[1]["owner_user_id"] == "already-owned"


def test_missing_user_fails_before_updating(schema, session: Session) -> None:
    _seed(schema, session)

    with pytest.raises(OwnerBackfillUserNotFound):
        backfill_owner_user_id(session, username="missing", apply=True)

    assert all(_null_count(schema, session, table) == 1 for table in OWNER_BACKFILL_TABLES)


def test_inactive_user_fails_before_updating(schema, session: Session) -> None:
    _seed(schema, session, inactive=True)

    with pytest.raises(OwnerBackfillInactiveUser):
        backfill_owner_user_id(session, username="root", apply=True)

    assert all(_null_count(schema, session, table) == 1 for table in OWNER_BACKFILL_TABLES)
