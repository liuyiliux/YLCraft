"""Real-route ownership contract tests for durable media task ledgers.

These exercise the FastAPI task routes (not just the ORM policy helper) so the
anonymous / human-session / external-key behaviors are fixed at the boundary
that clients actually call.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1 import tasks as tasks_api
from app.core.external_api_auth import ExternalApiKey
from app.core.user_auth import AuthenticatedPrincipal
from app.db.models.task import Model3DGenerationTask, VideoGenerationTask


class _EmptyQueue:
    """Minimal in-memory queue stub: persistent ledgers are the subject here."""

    def __init__(self) -> None:
        self._tasks: dict = {}

    async def restore_persisted_tasks(self, **_kwargs) -> None:
        return None

    async def get_task(self, _task_id: str):
        return None


@pytest.fixture
def task_ledger_client(tmp_path, monkeypatch):
    import asyncio

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tasks.db'}")
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Model3DGenerationTask.metadata.create_all(
                    sync_connection,
                    tables=[VideoGenerationTask.__table__, Model3DGenerationTask.__table__],
                )
            )

    asyncio.run(setup())

    @asynccontextmanager
    async def session_scope():
        async with factory() as session:
            yield session
            await session.commit()

    monkeypatch.setattr(tasks_api, "get_async_session", session_scope)
    monkeypatch.setattr(tasks_api, "get_task_queue", lambda: _EmptyQueue())
    monkeypatch.setattr(tasks_api, "_external_task_infos", lambda **_kwargs: [])
    monkeypatch.setattr(tasks_api, "_recent_asset_download_infos", lambda **_kwargs: [])

    def build_client(principal: AuthenticatedPrincipal | None):
        app = FastAPI()
        app.include_router(tasks_api.router, prefix="/api/v1/tasks")

        def required_principal():
            # Mirror the production dependency: anonymous cannot pass a
            # state-changing task route, while an injected session/key can.
            if principal is None:
                raise HTTPException(status_code=401, detail="未提供认证凭据")
            return principal

        app.dependency_overrides[tasks_api.get_authenticated_principal] = required_principal
        app.dependency_overrides[tasks_api.get_authenticated_principal_optional] = lambda: principal
        return TestClient(app)

    def seed():
        async def _seed():
            async with factory() as session:
                session.add_all([
                    VideoGenerationTask(task_id="video-a", owner_user_id="user-a", status="pending", prompt="a"),
                    VideoGenerationTask(task_id="video-legacy", owner_user_id=None, status="pending", prompt="legacy"),
                    Model3DGenerationTask(task_id="model3d-a", owner_user_id="user-a", status="pending", prompt="a"),
                ])
                await session.commit()

        asyncio.run(_seed())

    seed()
    try:
        yield build_client, factory
    finally:
        asyncio.run(engine.dispose())


def _user_principal(user_id: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(user=type("User", (), {"id": user_id})())


def test_task_list_detail_and_mutations_are_owner_scoped(task_ledger_client):
    build_client, _factory = task_ledger_client

    with build_client(_user_principal("user-a")) as owner:
        listed = owner.get("/api/v1/tasks").json()["tasks"]
        ids = {item["task_id"] for item in listed}
        assert {"video-a", "video-legacy", "model3d-a"} <= ids
        assert owner.get("/api/v1/tasks/video-a").status_code == 200

    with build_client(_user_principal("user-b")) as other:
        listed = other.get("/api/v1/tasks").json()["tasks"]
        ids = {item["task_id"] for item in listed}
        assert "video-a" not in ids
        assert "model3d-a" not in ids
        assert "video-legacy" in ids
        assert other.get("/api/v1/tasks/video-a").status_code == 403
        assert other.get("/api/v1/tasks/model3d-a").status_code == 403
        assert other.get("/api/v1/tasks/video-legacy").status_code == 200
        assert other.post("/api/v1/tasks/video-a/cancel").status_code == 403
        assert other.post("/api/v1/tasks/video-a/retry").status_code == 403
        assert other.delete("/api/v1/tasks/video-a").status_code == 403

    with build_client(None) as anonymous:
        listed = anonymous.get("/api/v1/tasks").json()["tasks"]
        ids = {item["task_id"] for item in listed}
        assert "video-a" not in ids
        assert "model3d-a" not in ids
        assert "video-legacy" in ids
        assert anonymous.get("/api/v1/tasks/video-a").status_code == 403
        assert anonymous.get("/api/v1/tasks/video-legacy").status_code == 200
        assert anonymous.post("/api/v1/tasks/video-a/cancel").status_code == 401

    with build_client(_user_principal("user-a")) as owner:
        cancelled = owner.post("/api/v1/tasks/video-a/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["task"]["status"] == "cancelled"


def test_external_key_can_read_but_never_pretends_to_own(task_ledger_client):
    build_client, _factory = task_ledger_client
    external = AuthenticatedPrincipal(external_api_key=ExternalApiKey(id="key-1", name="agent"))

    with build_client(external) as client:
        listed = client.get("/api/v1/tasks").json()["tasks"]
        ids = {item["task_id"] for item in listed}
        # Documented current semantics: keys are authenticated but have no User
        # subject mapping, so they keep full read visibility until a dedicated
        # change gives them an owner. They must never be treated as a human user.
        assert {"video-a", "video-legacy", "model3d-a"} <= ids
        assert client.get("/api/v1/tasks/video-a").status_code == 200
