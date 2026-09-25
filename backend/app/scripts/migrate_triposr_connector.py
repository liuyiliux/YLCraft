"""Import legacy TripoSR environment configuration into AIConnector.

Usage:
    python -m app.scripts.migrate_triposr_connector
    python -m app.scripts.migrate_triposr_connector --apply

The default is a read-only dry run.  The API key is never printed.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.db.database import SessionLocal  # noqa: E402
from app.services.model3d.triposr_migration import (  # noqa: E402
    DEFAULT_CONNECTOR_NAME,
    TripoSRMigrationError,
    migrate_triposr_connector,
)


def _print_result(result) -> None:
    mode = "APPLIED" if result.applied else "DRY RUN"
    changed = ", ".join(result.changed_fields) if result.changed_fields else "none"
    print(f"{mode}: action={result.action} connector_id={result.connector_id}")
    print(f"name={result.name} base_url={result.base_url} has_api_key={str(result.has_api_key).lower()}")
    print(f"changed_fields={changed}")
    if not result.applied and result.action != "noop":
        print("Dry run only. Re-run with --apply to write the connector.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the connector; without this flag the command is read-only")
    parser.add_argument("--name", default=DEFAULT_CONNECTOR_NAME, help="connector display name")
    args = parser.parse_args(argv)

    session = SessionLocal()
    try:
        result = migrate_triposr_connector(
            session,
            os.environ,
            apply=args.apply,
            connector_name=args.name,
        )
        if args.apply:
            session.commit()
        else:
            session.rollback()
    except TripoSRMigrationError as exc:
        session.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        print(f"ERROR: TripoSR migration failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()

    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
