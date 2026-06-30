"""Compatibility wrapper for the archived legacy asset migration script.

Usage:
    python -m app.scripts.migrate_legacy_assets_to_hub
    python -m app.scripts.migrate_legacy_assets_to_hub --apply
    python -m app.scripts.migrate_legacy_assets_to_hub --apply --limit 20

Prefer the archived module path for maintenance reruns:
    python -m app.scripts.archive.migrate_legacy_assets_to_hub
"""

from __future__ import annotations

from app.scripts.archive.migrate_legacy_assets_to_hub import _run


if __name__ == "__main__":
    _run()
