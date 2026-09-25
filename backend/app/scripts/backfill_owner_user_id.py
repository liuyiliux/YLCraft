"""Backfill legacy NULL ownership to a real account.

Usage:
    python -m app.scripts.backfill_owner_user_id
    python -m app.scripts.backfill_owner_user_id --username root --apply

The default is a read-only dry run.  ``--apply`` performs one transaction over
the explicit target tables and never overwrites a non-NULL owner.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.db.database import SessionLocal  # noqa: E402
from app.services.ownership.backfill import (  # noqa: E402
    OwnerBackfillError,
    backfill_owner_user_id,
)


def _print_result(result) -> None:
    mode = "APPLIED" if result.applied else "DRY RUN"
    print(f"{mode}: username={result.username} user_id={result.user_id}")
    for item in result.tables:
        print(
            f"{item.table}: null_before={item.null_before} "
            f"updated={item.updated} remaining={item.remaining}"
        )
    print(
        "TOTAL: "
        f"null_before={result.total_null_before} "
        f"updated={result.total_updated} remaining={result.total_remaining}"
    )
    if not result.applied and result.total_null_before:
        print("Dry run only. Re-run with --apply to write these rows.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="root", help="target owner username")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the backfill; without this flag the command is read-only",
    )
    args = parser.parse_args(argv)

    session = SessionLocal()
    try:
        result = backfill_owner_user_id(
            session,
            username=args.username,
            apply=args.apply,
        )
        if args.apply:
            session.commit()
        else:
            session.rollback()
    except OwnerBackfillError as exc:
        session.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        print(f"ERROR: backfill failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()

    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
