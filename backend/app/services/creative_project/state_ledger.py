"""Append-only dynamic-state ledger for creative projects.

The ledger records every change to mutable story state (level, attributes,
skills, relationships, world variables) with chapter + source provenance. The
current state is a fold over these entries; ``scope`` separates character state
(``character:<id>``) from project-global state (``world``).

The envelope is schema'd; the values are free-form JSON.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import delete
from sqlmodel import Session, select

from app.db.models.creative_project import ProjectStateEntry

VALID_OPS = {"set", "add", "remove"}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _loads(value: str, fallback: Any = None) -> Any:
    try:
        return json.loads(value or "null")
    except (TypeError, json.JSONDecodeError):
        return fallback


def _fingerprint(
    project_id: str,
    scope: str,
    key: str,
    op: str,
    value_json: str,
    chapter_number: int,
    source_content_id: str | None,
) -> str:
    raw = "\x00".join(
        [project_id, scope, key, op, value_json, str(chapter_number), source_content_id or ""]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _apply(current: Any, op: str, value: Any) -> Any:
    """Fold one op into the current value. Returns None to mean "delete key"."""
    if op == "set":
        return value
    if op == "add":
        if isinstance(current, (int, float)) and isinstance(value, (int, float)):
            return current + value
        if isinstance(current, list):
            merged = list(current)
            for item in (value if isinstance(value, list) else [value]):
                if item not in merged:
                    merged.append(item)
            return merged
        return value
    if op == "remove":
        if isinstance(current, list):
            items = value if isinstance(value, list) else [value]
            return [item for item in current if item not in items]
        if isinstance(current, (int, float)) and isinstance(value, (int, float)):
            return current - value
        return None  # scalar remove deletes the key
    return current


class StateLedger:
    @staticmethod
    def fingerprint(change: dict[str, Any], *, project_id: str, chapter_number: int, source_content_id: str | None) -> str:
        return _fingerprint(
            project_id,
            str(change.get("scope") or ""),
            str(change.get("key") or ""),
            str(change.get("op") or "set"),
            _json(change.get("value")),
            int(chapter_number),
            source_content_id,
        )

    @classmethod
    def apply_changes(
        cls,
        session: Session,
        project_id: str,
        changes: list[dict[str, Any]],
        *,
        chapter_number: int,
        source_content_id: str | None = None,
        source_version: int = 1,
    ) -> int:
        """Append changes, skipping duplicates. Returns count of new entries."""
        added = 0
        for change in changes:
            if not isinstance(change, dict):
                continue
            scope = str(change.get("scope") or "").strip()
            key = str(change.get("key") or "").strip()
            if not scope or not key:
                continue
            op = str(change.get("op") or "set").strip() or "set"
            if op not in VALID_OPS:
                op = "set"
            value_json = _json(change.get("value"))
            fp = _fingerprint(project_id, scope, key, op, value_json, int(chapter_number), source_content_id)
            existing = session.exec(
                select(ProjectStateEntry).where(ProjectStateEntry.fingerprint == fp)
            ).first()
            if existing is not None:
                continue
            session.add(
                ProjectStateEntry(
                    project_id=project_id,
                    scope=scope,
                    key=key,
                    op=op,
                    value_json=value_json,
                    chapter_number=int(chapter_number),
                    source_content_id=source_content_id,
                    source_version=int(source_version or 1),
                    fingerprint=fp,
                )
            )
            added += 1
        return added

    @classmethod
    def replace_chapter_entries(
        cls,
        session: Session,
        project_id: str,
        chapter_number: int,
        changes: list[dict[str, Any]],
        *,
        source_content_id: str | None = None,
        source_version: int = 1,
    ) -> int:
        """Remove this chapter's prior entries, then apply the new ones."""
        session.execute(
            delete(ProjectStateEntry).where(
                ProjectStateEntry.project_id == project_id,
                ProjectStateEntry.chapter_number == int(chapter_number),
            )
        )
        return cls.apply_changes(
            session,
            project_id,
            changes,
            chapter_number=chapter_number,
            source_content_id=source_content_id,
            source_version=source_version,
        )

    @classmethod
    def compute_state(
        cls,
        session: Session,
        project_id: str,
        *,
        scope: str | None = None,
        up_to_chapter: int | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Fold the ledger into ``{scope: {key: value}}``."""
        stmt = select(ProjectStateEntry).where(ProjectStateEntry.project_id == project_id)
        if scope is not None:
            stmt = stmt.where(ProjectStateEntry.scope == scope)
        if up_to_chapter is not None:
            stmt = stmt.where(ProjectStateEntry.chapter_number <= int(up_to_chapter))
        entries = session.exec(
            stmt.order_by(
                ProjectStateEntry.chapter_number.asc(),
                ProjectStateEntry.created_at.asc(),
            )
        ).all()

        state: dict[str, dict[str, Any]] = {}
        for entry in entries:
            value = _loads(entry.value_json)
            scope_state = state.setdefault(entry.scope, {})
            current = scope_state.get(entry.key)
            result = _apply(current, entry.op, value)
            if result is None:
                scope_state.pop(entry.key, None)
            else:
                scope_state[entry.key] = result
        return state

    @classmethod
    def state_as_of(cls, session: Session, project_id: str, chapter_number: int) -> dict[str, dict[str, Any]]:
        return cls.compute_state(session, project_id, up_to_chapter=chapter_number)
