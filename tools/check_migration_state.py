#!/usr/bin/env python3
"""Report the Alembic state of a YLCraft PostgreSQL database without mutating it.

This is deliberately an operator diagnostic, not a migration runner.  It only
reads ``alembic_version`` and the local Alembic revision graph; it never calls
``upgrade``, ``stamp``, ``create_all`` or any schema DDL.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from alembic.config import Config
from alembic.script import ScriptDirectory
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError


REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
ALEMBIC_CONFIG = BACKEND_ROOT / "alembic.ini"


def redact_database_url(value: str) -> str:
    """Return a display-safe connection URL without a password or query secrets."""
    try:
        url: URL = make_url(value)
        return str(url.set(password="***")._replace(query={}))
    except Exception:
        parts = urlsplit(value)
        if not parts.scheme:
            return "<invalid database URL>"
        hostname = parts.hostname or ""
        username = f"{parts.username}@" if parts.username else ""
        port = f":{parts.port}" if parts.port else ""
        return urlunsplit((parts.scheme, f"{username}{hostname}{port}", parts.path, "", ""))


def get_local_heads() -> list[str]:
    """Read local revision heads without connecting to a database."""
    config = Config(str(ALEMBIC_CONFIG))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return sorted(ScriptDirectory.from_config(config).get_heads())


def read_database_revisions(database_url: str) -> list[str] | None:
    """Read Alembic's version table only; ``None`` means it is absent."""
    url = make_url(database_url)
    # The application uses asyncpg, while this intentionally synchronous
    # operator probe uses psycopg2 for one read-only SELECT.
    if url.drivername == "postgresql+asyncpg":
        url = url.set(drivername="postgresql+psycopg2")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            try:
                rows = connection.execute(text("SELECT version_num FROM alembic_version"))
            except SQLAlchemyError as error:
                message = str(error).lower()
                if "alembic_version" in message and (
                    "does not exist" in message or "undefined table" in message or "no such table" in message
                ):
                    return None
                raise
            return sorted(str(row[0]) for row in rows)
    finally:
        engine.dispose()


def build_report(database_url: str) -> dict[str, Any]:
    heads = get_local_heads()
    revisions = read_database_revisions(database_url)
    if revisions is None:
        state = "unversioned"
        guidance = "数据库没有 alembic_version；先确认这是空库或受控旧库，再由部署人员执行迁移。"
    elif revisions == heads:
        state = "current"
        guidance = "数据库 revision 已与本地 head 一致。"
    elif len(revisions) > 1:
        state = "multiple_revisions"
        guidance = "检测到多个数据库 revision；停止升级，先检查迁移历史和数据库备份。"
    else:
        state = "behind_or_diverged"
        guidance = "数据库 revision 与本地 head 不一致；备份并在审批后执行显式升级。"

    return {
        "state": state,
        "database": redact_database_url(database_url),
        "current_revisions": revisions,
        "local_heads": heads,
        "recommended_command": "cd backend && alembic upgrade head" if state != "current" else None,
        "guidance": guidance,
        "guarantees": [
            "本工具仅查询 alembic_version。",
            "本工具不会执行 upgrade、stamp、create_all、ALTER TABLE 或其他 DDL。",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        help="PostgreSQL URL. Defaults to DATABASE_URL from the environment or backend/.env.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    load_dotenv(BACKEND_ROOT / ".env", override=False)
    database_url = args.database_url or os.getenv("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required (environment, backend/.env, or --database-url).")
    if not database_url.startswith((
        "postgresql://",
        "postgresql+asyncpg://",
        "postgresql+psycopg2://",
        "postgresql+psycopg://",
    )):
        parser.error("only PostgreSQL URLs are supported by this remote migration diagnostic.")

    try:
        report = build_report(database_url)
    except SQLAlchemyError as error:
        report = {
            "state": "unreachable",
            "database": redact_database_url(database_url),
            "error": str(error),
            "guidance": "检查网络、凭证和 SSL 配置；不要因此执行 stamp 或任何 DDL。",
        }
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"Migration state: {report['state']}")
            print(f"Database: {report['database']}")
            print(f"Error: {report['error']}")
            print(f"Next: {report['guidance']}")
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Migration state: {report['state']}")
        print(f"Database: {report['database']}")
        print(f"Current revision(s): {report['current_revisions'] or '<none>'}")
        print(f"Local head(s): {', '.join(report['local_heads'])}")
        print(f"Next: {report['guidance']}")
        if report["recommended_command"]:
            print(f"After backup and approval: {report['recommended_command']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
