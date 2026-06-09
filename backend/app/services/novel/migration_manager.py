"""Migration helpers for novel book source rule metadata."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.services.novel.rule_converter import SUPPORTED_YLCRAFT_VERSION, convert_legado_to_ylcraft


RULE_METADATA_COLUMNS = {
    "rule_format": "VARCHAR DEFAULT 'legado' NOT NULL",
    "rule_version": "VARCHAR DEFAULT '' NOT NULL",
    "ylcraft_rule": "TEXT DEFAULT '' NOT NULL",
    "original_format": "VARCHAR DEFAULT '' NOT NULL",
    "original_source": "TEXT DEFAULT '' NOT NULL",
    "migration_log": "TEXT DEFAULT '' NOT NULL",
}


class BookSourceMigrationManager:
    """Backfill YLCraft rule metadata for existing book sources."""

    def __init__(self, db: Session):
        self.db = db

    def migrate_existing_sources(self) -> Dict[str, Any]:
        self.ensure_rule_metadata_columns()
        rows = self.db.execute(text("SELECT * FROM book_sources")).mappings().all()

        migrated = 0
        skipped = 0
        failed = 0
        errors = []

        for row in rows:
            if row.get("rule_format") == "ylcraft" and row.get("ylcraft_rule"):
                skipped += 1
                continue

            try:
                legado_source = _row_to_legado_source(row)
                ylcraft_rule = convert_legado_to_ylcraft(legado_source)
                migration_log = {
                    "migrated_at": datetime.now().isoformat(),
                    "from_format": row.get("rule_format") or "legado",
                    "to_format": "ylcraft",
                    "warnings": ylcraft_rule.get("conversion_warnings", []),
                }
                self.db.execute(
                    text(
                        """
                        UPDATE book_sources
                        SET rule_format = :rule_format,
                            rule_version = :rule_version,
                            ylcraft_rule = :ylcraft_rule,
                            original_format = :original_format,
                            original_source = CASE
                                WHEN COALESCE(original_source, '') = '' THEN :original_source
                                ELSE original_source
                            END,
                            migration_log = :migration_log
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": row["id"],
                        "rule_format": "ylcraft",
                        "rule_version": ylcraft_rule.get("version", SUPPORTED_YLCRAFT_VERSION),
                        "ylcraft_rule": json.dumps(ylcraft_rule, ensure_ascii=False),
                        "original_format": row.get("original_format") or "legado",
                        "original_source": json.dumps(legado_source, ensure_ascii=False),
                        "migration_log": json.dumps(migration_log, ensure_ascii=False),
                    },
                )
                migrated += 1
            except Exception as e:
                failed += 1
                errors.append({"id": row.get("id"), "error": str(e)})

        self.db.commit()
        return {
            "success": failed == 0,
            "migrated": migrated,
            "skipped": skipped,
            "failed": failed,
            "errors": errors,
        }

    def ensure_rule_metadata_columns(self) -> None:
        bind = self.db.get_bind()
        inspector = inspect(bind)
        table_names = inspector.get_table_names()
        if "book_sources" not in table_names:
            return

        existing = {column["name"] for column in inspector.get_columns("book_sources")}
        for column_name, column_type in RULE_METADATA_COLUMNS.items():
            if column_name in existing:
                continue
            self.db.execute(text(f"ALTER TABLE book_sources ADD COLUMN {column_name} {column_type}"))
        self.db.commit()


def _row_to_legado_source(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "bookSourceName": row.get("book_source_name") or "",
        "bookSourceUrl": row.get("book_source_url") or "",
        "bookSourceType": row.get("book_source_type") or 0,
        "enabled": row.get("enabled", True),
        "customOrder": row.get("custom_order") or 0,
        "searchUrl": row.get("search_url") or "",
        "bookSourceGroup": row.get("book_source_group") or "",
        "explore": row.get("explore", False),
        "cookie": row.get("cookie") or "",
        "header": row.get("header") or "",
        "loginUrl": row.get("login_url") or "",
        "loginUi": row.get("login_ui") or "",
        "loginCheckJs": row.get("login_check_js") or "",
        "coverUrl": row.get("cover_url") or "",
        "bookSourceComment": row.get("book_source_comment") or "",
        "weight": row.get("weight") or 0,
        "respondTime": row.get("respond_time") or 0,
        "lastUpdateTime": row.get("last_update_time") or "",
        "ruleSearch": _json_load(row.get("rule_search")),
        "ruleBookInfo": _json_load(row.get("rule_book_info")),
        "ruleToc": _json_load(row.get("rule_toc")),
        "ruleContent": _json_load(row.get("rule_content")),
        "ruleExplore": _json_load(row.get("rule_explore")),
    }


def _json_load(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}
