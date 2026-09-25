from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, select

from app.db.models.ai_connector import AIConnector
from app.services.model3d.triposr_migration import (
    DEFAULT_API_BASE,
    DEFAULT_CONNECTOR_ID,
    TripoSRMigrationError,
    build_triposr_connector_values,
    migrate_triposr_connector,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    AIConnector.metadata.create_all(engine, tables=[AIConnector.__table__])
    with Session(engine) as db:
        yield db


def test_plan_preserves_default_base_and_marks_missing_key():
    values = build_triposr_connector_values({})

    assert values["base_url"] == DEFAULT_API_BASE
    assert values["api_key"] == ""
    config = json.loads(values["response_config"])
    assert config["legacy_image_to_3d"] is True
    assert config["upload_endpoint"] == "/upload"
    assert config["poll_endpoint"] == "/task/{task_id}"


def test_dry_run_does_not_create_connector_and_apply_is_idempotent(session):
    env = {"TRIPOSR_API_BASE": "https://api.tripo3d.ai/api/v1", "TRIPOSR_API_KEY": "test-key"}

    dry = migrate_triposr_connector(session, env, apply=False)
    assert dry.action == "create"
    assert dry.has_api_key is True
    assert session.execute(select(AIConnector)).scalars().all() == []

    first = migrate_triposr_connector(session, env, apply=True)
    session.commit()
    assert first.action == "create"
    rows = session.execute(select(AIConnector)).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == DEFAULT_CONNECTOR_ID
    assert json.loads(rows[0].response_config)["legacy_image_to_3d"] is True

    second = migrate_triposr_connector(session, env, apply=True)
    session.commit()
    assert second.action == "noop"
    assert len(session.execute(select(AIConnector)).scalars().all()) == 1


def test_apply_without_key_fails_readably_without_writing(session):
    with pytest.raises(TripoSRMigrationError, match="TRIPOSR_API_KEY"):
        migrate_triposr_connector(session, {"TRIPOSR_API_BASE": DEFAULT_API_BASE}, apply=True)

    assert session.execute(select(AIConnector)).scalars().all() == []


def test_existing_manual_non_empty_fields_are_not_overwritten(session):
    existing = AIConnector(
        id=DEFAULT_CONNECTOR_ID,
        provider="triposr",
        name="TripoSR",
        provider_type="3d",
        api_key="manual-key",
        base_url="https://manual.example.test/v1",
        response_config='{"legacy_image_to_3d":true,"poll_endpoint":"/manual/{task_id}"}',
    )
    session.add(existing)
    session.commit()

    result = migrate_triposr_connector(
        session,
        {"TRIPOSR_API_BASE": "https://env.example.test/v1", "TRIPOSR_API_KEY": "env-key"},
        apply=True,
    )
    session.commit()
    session.refresh(existing)

    assert result.action in {"update", "noop"}
    assert existing.api_key == "manual-key"
    assert existing.base_url == "https://manual.example.test/v1"
    assert json.loads(existing.response_config)["poll_endpoint"] == "/manual/{task_id}"


def test_model3d_service_has_no_direct_tripo_http_or_env_branch():
    source_path = Path(__file__).resolve().parents[1] / "app" / "services" / "model3d" / "service.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update({
        (node.module or "").split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    })
    assert "httpx" not in imported

    env_reads = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"getenv", "environ"}:
            continue
        env_reads.extend(
            arg.value for arg in node.args
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
        )
    assert not any(name.startswith("TRIPOSR") for name in env_reads)
