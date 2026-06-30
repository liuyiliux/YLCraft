"""Export legacy asset tables before final cleanup.

Usage:
    python -m app.scripts.archive.backup_legacy_assets
    python -m app.scripts.archive.backup_legacy_assets --output C:\\backup\\legacy_assets.json

This command is non-destructive. It exports the old asset compatibility tables
to a local JSON file so a later final deletion can be reviewed and rolled back.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.db.database import get_async_session


LEGACY_TABLES = ("assets", "asset_tags", "asset_collections")


def _json_default(value: Any) -> str:
    return str(value)


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


async def _export_table(session, table_name: str) -> dict[str, Any]:
    if not await _table_exists(session, table_name):
        return {"table": table_name, "exists": False, "count": 0, "rows": []}

    result = await session.execute(text(f'SELECT * FROM "{table_name}" ORDER BY 1'))
    rows = [dict(row) for row in result.mappings().all()]
    return {
        "table": table_name,
        "exists": True,
        "count": len(rows),
        "rows": rows,
    }


async def _run() -> None:
    parser = argparse.ArgumentParser(description="Backup legacy asset tables to JSON.")
    parser.add_argument("--output", default="", help="Output JSON path. Defaults to backend/backups/legacy_assets/.")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(__file__).resolve().parents[3] / "backups" / "legacy_assets" / f"legacy_assets_backup_{timestamp}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with get_async_session() as session:
        tables = [await _export_table(session, table_name) for table_name in LEGACY_TABLES]

    payload = {
        "created_at": datetime.now().isoformat(),
        "source": "legacy_asset_tables",
        "destructive": False,
        "tables": tables,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "success": True,
                "output": str(output_path),
                "tables": [{"table": table["table"], "exists": table["exists"], "count": table["count"]} for table in tables],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(_run())
