"""CLI helper to migrate old assets rows into asset_hub.

Usage:
    python -m app.scripts.migrate_legacy_assets_to_hub
    python -m app.scripts.migrate_legacy_assets_to_hub --apply
    python -m app.scripts.migrate_legacy_assets_to_hub --apply --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.db.database import get_async_session
from app.services.asset_hub.legacy_migration import LegacyAssetHubMigration


async def _run() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy assets table rows into asset_hub.")
    parser.add_argument("--apply", action="store_true", help="Write changes. Without this flag, only dry-run.")
    parser.add_argument("--limit", type=int, default=None, help="Limit scanned rows for a small batch.")
    args = parser.parse_args()

    async with get_async_session() as session:
        result = await LegacyAssetHubMigration(session).migrate(
            limit=args.limit,
            dry_run=not args.apply,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_run())
