"""Explicit migration of legacy TripoSR environment configuration.

The application no longer reads TripoSR credentials at request time.  This
module turns the old environment contract into one AIConnector record while
keeping the command read-only unless the operator explicitly applies it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy import or_
from sqlmodel import Session, select

from app.db.models.ai_connector import AIConnector


DEFAULT_CONNECTOR_ID = "triposr"
DEFAULT_CONNECTOR_NAME = "TripoSR"
DEFAULT_API_BASE = "https://api.tripo3d.ai/api/v1"


class TripoSRMigrationError(RuntimeError):
    """Readable migration failure safe to show to an operator."""


@dataclass(frozen=True)
class TripoSRMigrationResult:
    action: str
    connector_id: str
    name: str
    base_url: str
    has_api_key: bool
    changed_fields: tuple[str, ...]
    applied: bool


def build_triposr_connector_values(env: Mapping[str, str]) -> dict[str, Any]:
    """Build the connector values from the old environment contract."""
    base_url = str(env.get("TRIPOSR_API_BASE") or DEFAULT_API_BASE).strip().rstrip("/")
    api_key = str(env.get("TRIPOSR_API_KEY") or "").strip()
    response_config = {
        "legacy_image_to_3d": True,
        "upload_endpoint": "/upload",
        "upload_field": "file",
        "upload_url_path": "$.url",
        "task_id_path": "$.task_id",
        "status_path": "$.status",
        "model_url_path": "$.result.model_url",
        "error_path": "$.error",
        "poll_endpoint": "/task/{task_id}",
        "poll_interval": 10,
        "done_values": ["completed", "success", "succeeded"],
        "failed_values": ["failed", "error", "cancelled"],
    }
    return {
        "provider": "triposr",
        "name": DEFAULT_CONNECTOR_NAME,
        "provider_type": "3d",
        "api_format": "custom",
        "base_url": base_url,
        "api_endpoint": "/task",
        "default_model": "triposr",
        "available_models": json.dumps(["triposr"]),
        "api_key": api_key,
        "request_template": '{"image_url":"{{ image_url }}"}',
        "response_config": json.dumps(response_config, ensure_ascii=False, separators=(",", ":")),
        "default_params": "{}",
        "support_reference_image": True,
        "is_active": True,
        "is_default": False,
        "priority": 0,
        "timeout": 300,
        "description": "Migrated from legacy TRIPOSR_API_BASE / TRIPOSR_API_KEY.",
    }


def _existing_connector(session: Session, name: str) -> AIConnector | None:
    statement = select(AIConnector).where(
        or_(
            AIConnector.id == DEFAULT_CONNECTOR_ID,
            AIConnector.provider == "triposr",
            AIConnector.name == name,
        )
    )
    return session.execute(statement).scalars().first()


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _changed_fields(existing: AIConnector, values: dict[str, Any]) -> list[str]:
    return [
        field
        for field, value in values.items()
        if not _empty(value) and _empty(getattr(existing, field, None))
    ]


def migrate_triposr_connector(
    session: Session,
    env: Mapping[str, str],
    *,
    apply: bool = False,
    connector_name: str = DEFAULT_CONNECTOR_NAME,
) -> TripoSRMigrationResult:
    """Plan or apply the one-time TripoSR connector migration.

    ``apply=False`` never mutates the session.  ``apply=True`` only fills empty
    fields on an existing connector, so a manually edited key or endpoint is
    not overwritten by a repeated run.
    """
    values = build_triposr_connector_values(env)
    values["name"] = connector_name
    api_key = str(values.get("api_key") or "")
    if apply and not api_key:
        raise TripoSRMigrationError(
            "TRIPOSR_API_KEY is not configured; refusing to create an unusable connector"
        )

    existing = _existing_connector(session, connector_name)
    if existing is None:
        result = TripoSRMigrationResult(
            action="create",
            connector_id=DEFAULT_CONNECTOR_ID,
            name=connector_name,
            base_url=str(values["base_url"]),
            has_api_key=bool(api_key),
            changed_fields=tuple(values.keys()),
            applied=apply,
        )
        if apply:
            connector = AIConnector(id=DEFAULT_CONNECTOR_ID, **values)
            session.add(connector)
        return result

    changed = _changed_fields(existing, values)
    result = TripoSRMigrationResult(
        action="update" if changed else "noop",
        connector_id=str(existing.id),
        name=str(existing.name),
        base_url=str(existing.base_url or values["base_url"]),
        has_api_key=bool(existing.api_key or api_key),
        changed_fields=tuple(changed),
        applied=apply,
    )
    if apply:
        for field in changed:
            setattr(existing, field, values[field])
    return result
