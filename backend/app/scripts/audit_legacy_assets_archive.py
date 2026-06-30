"""Audit legacy assets archive state without destructive cleanup.

Usage:
    python -m app.scripts.audit_legacy_assets_archive
    python -m app.scripts.audit_legacy_assets_archive --limit 50
    python -m app.scripts.audit_legacy_assets_archive --apply-markers

The command never deletes database rows, tables, or files. With --apply-markers
it only writes metadata markers on legacy assets that already have an Asset Hub
node.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.db.database import get_async_session
from app.services.asset_hub.legacy_migration import LegacyAssetArchiveAudit


async def _run() -> None:
    parser = argparse.ArgumentParser(description="Audit legacy assets archive state.")
    parser.add_argument("--limit", type=int, default=None, help="Limit scanned rows for a small batch.")
    parser.add_argument(
        "--apply-markers",
        action="store_true",
        help="Write only archived_in_hub metadata markers for already migrated legacy assets.",
    )
    args = parser.parse_args()

    async with get_async_session() as session:
        result = await LegacyAssetArchiveAudit(session).audit(
            limit=args.limit,
            apply_markers=args.apply_markers,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_run())
