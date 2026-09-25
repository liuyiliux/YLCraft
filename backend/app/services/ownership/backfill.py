"""Idempotent backfill for legacy NULL ``owner_user_id`` rows.

The service deliberately does not commit.  The caller owns the transaction so
an operator command can either roll back a dry run or commit all tables as one
unit of work.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session


OWNER_BACKFILL_TABLES = (
    "creative_projects",
    "asset_nodes",
    "project_task_records",
    "video_generation_tasks",
    "model3d_generation_tasks",
)


class OwnerBackfillError(RuntimeError):
    """Base error with a message safe to show to an operator."""


class OwnerBackfillUserNotFound(OwnerBackfillError):
    """Raised when the requested owner account does not exist."""


class OwnerBackfillInactiveUser(OwnerBackfillError):
    """Raised when the requested owner account is disabled."""


class OwnerBackfillSchemaError(OwnerBackfillError):
    """Raised when a target table or owner column is missing."""


@dataclass(frozen=True)
class OwnerBackfillTableResult:
    table: str
    null_before: int
    updated: int
    remaining: int


@dataclass(frozen=True)
class OwnerBackfillResult:
    username: str
    user_id: str
    applied: bool
    tables: tuple[OwnerBackfillTableResult, ...]

    @property
    def total_null_before(self) -> int:
        return sum(item.null_before for item in self.tables)

    @property
    def total_updated(self) -> int:
        return sum(item.updated for item in self.tables)

    @property
    def total_remaining(self) -> int:
        return sum(item.remaining for item in self.tables)


def _validate_schema(session: Session) -> None:
    inspector = inspect(session.connection())
    existing_tables = set(inspector.get_table_names())
    missing_tables = [table for table in OWNER_BACKFILL_TABLES if table not in existing_tables]
    if missing_tables:
        raise OwnerBackfillSchemaError(
            "missing target table(s): " + ", ".join(missing_tables)
        )

    missing_columns = []
    for table in OWNER_BACKFILL_TABLES:
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "owner_user_id" not in columns:
            missing_columns.append(f"{table}.owner_user_id")
    if missing_columns:
        raise OwnerBackfillSchemaError(
            "missing owner column(s): " + ", ".join(missing_columns)
        )


def _resolve_user(session: Session, username: str) -> tuple[str, bool]:
    row = session.execute(
        text("SELECT id, is_active FROM users WHERE username = :username"),
        {"username": username},
    ).mappings().first()
    if row is None:
        raise OwnerBackfillUserNotFound(f"owner account not found: {username}")
    return str(row["id"]), bool(row["is_active"])


def _count_null_owners(session: Session, table: str) -> int:
    return int(
        session.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE owner_user_id IS NULL")
        ).scalar_one()
    )


def backfill_owner_user_id(
    session: Session,
    *,
    username: str = "root",
    apply: bool = False,
) -> OwnerBackfillResult:
    """Report or apply the legacy owner backfill without committing.

    ``apply=False`` is a strict dry run: every table is counted and no UPDATE is
    sent.  ``apply=True`` updates only NULL owners and keeps every existing
    owner value unchanged.
    """

    normalized_username = username.strip()
    if not normalized_username:
        raise OwnerBackfillUserNotFound("owner account not found: <empty>")

    _validate_schema(session)
    user_id, is_active = _resolve_user(session, normalized_username)
    if not is_active:
        raise OwnerBackfillInactiveUser(
            f"owner account is inactive: {normalized_username}"
        )

    results: list[OwnerBackfillTableResult] = []
    for table in OWNER_BACKFILL_TABLES:
        null_before = _count_null_owners(session, table)
        updated = 0
        if apply and null_before:
            update_result = session.execute(
                text(
                    f"UPDATE {table} SET owner_user_id = :owner_user_id "
                    "WHERE owner_user_id IS NULL"
                ),
                {"owner_user_id": user_id},
            )
            rowcount = getattr(update_result, "rowcount", -1)
            updated = int(rowcount) if rowcount is not None and rowcount >= 0 else null_before
        remaining = _count_null_owners(session, table) if apply else null_before
        results.append(
            OwnerBackfillTableResult(
                table=table,
                null_before=null_before,
                updated=updated,
                remaining=remaining,
            )
        )

    return OwnerBackfillResult(
        username=normalized_username,
        user_id=user_id,
        applied=apply,
        tables=tuple(results),
    )
