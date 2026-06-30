"""Archived legacy asset migration placeholder.

Usage:
    python -m app.scripts.archive.migrate_legacy_assets_to_hub

The final legacy cleanup removed the old `assets` tables and migration bridge.
Use backend/backups/legacy_assets JSON exports for historical inspection.
"""

from __future__ import annotations

import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _run() -> None:
    print(
        json.dumps(
            {
                "success": False,
                "archived": True,
                "message": "Legacy asset migration is closed because old asset tables have been removed.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    _run()
