"""Drop old asset compatibility tables after Asset Hub migration.

Usage:
    python -m app.scripts.archive.drop_legacy_asset_tables --backup backend/backups/legacy_assets/legacy_assets_backup_YYYYMMDD_HHMMSS.json
    python -m app.scripts.archive.drop_legacy_asset_tables --apply --backup backend/backups/legacy_assets/legacy_assets_backup_YYYYMMDD_HHMMSS.json

Without --apply this script only reports the tables that would be dropped.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.db.database import get_async_session


LEGACY_TABLES = ("asset_tags", "asset_collections", "assets")
MAX_BACKUP_AGE = timedelta(hours=24)


def _load_backup(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Backup file does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    created_at_raw = payload.get("created_at")
    if not created_at_raw:
        raise SystemExit("Backup file is missing created_at")
    created_at = datetime.fromisoformat(str(created_at_raw))
    if datetime.now() - created_at > MAX_BACKUP_AGE:
        raise SystemExit(f"Backup is older than {MAX_BACKUP_AGE}: {path}")
    backed_up_tables = {str(item.get("table")) for item in payload.get("tables", [])}
    missing = sorted(set(LEGACY_TABLES) - backed_up_tables)
    if missing:
        raise SystemExit(f"Backup does not contain all legacy tables: {missing}")
    return payload


async def _table_exists(session, table_name: str) -> bool:
    result = await session.execute(
        text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    )
    return result.scalar_one_or_none() is not None


async def _run() -> None:
    parser = argparse.ArgumentParser(description="Drop legacy asset tables after backup.")
    parser.add_argument("--apply", action="store_true", help="Actually drop the old tables.")
    parser.add_argument("--backup", required=True, help="Recent JSON backup produced by backup_legacy_assets.")
    args = parser.parse_args()

    backup_path = Path(args.backup)
    if not backup_path.is_absolute():
        backup_path = Path.cwd() / backup_path
    backup = _load_backup(backup_path)

    async with get_async_session() as session:
        before = {table_name: await _table_exists(session, table_name) for table_name in LEGACY_TABLES}
        dropped: list[str] = []
        if args.apply:
            for table_name in LEGACY_TABLES:
                if before[table_name]:
                    await session.execute(text(f'DROP TABLE "{table_name}"'))
                    dropped.append(table_name)
            await session.commit()
        after = {table_name: await _table_exists(session, table_name) for table_name in LEGACY_TABLES}

    print(
        json.dumps(
            {
                "success": True,
                "applied": bool(args.apply),
                "backup": str(backup_path),
                "backup_created_at": backup.get("created_at"),
                "before": before,
                "dropped": dropped,
                "after": after,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(_run())
