"""Route-level ownership contract tests for asset mutations.

These exercise the FastAPI asset routes so cross-owner writes are rejected at
the boundary clients actually call, while NULL-legacy assets stay writable.
A lightweight session double is used because the real AssetNode table uses
PostgreSQL JSONB columns that SQLite cannot render.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.v1 import assets as assets_api
from app.core.user_auth import AuthenticatedPrincipal


class _FakeNode:
    def __init__(self, node_id: str, owner_user_id: str | None, deleted: bool = False):
        self.id = node_id
        self.owner_user_id = owner_user_id
        self.name = f"asset-{node_id}"
        self.metadata_json = {"deleted_at": "now" if deleted else "", "status": "DELETED" if deleted else "READY"}
        self.tags_json = []
        self.updated_at = None


class _FakeSession:
    def __init__(self, nodes: dict[str, _FakeNode]):
        self.nodes = nodes

    async def get(self, _model, asset_id: str):
        return self.nodes.get(asset_id)

    def add(self, _node):
        return None

    async def commit(self):
        return None

    async def refresh(self, _node):
        return None


def _user_principal(user_id: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(user=type("User", (), {"id": user_id})())


def _build_client(nodes: dict[str, _FakeNode], principal: AuthenticatedPrincipal | None):
    app = FastAPI()
    app.include_router(assets_api.router, prefix="/api/v1/assets")
    session = _FakeSession(nodes)

    app.dependency_overrides[assets_api.get_asset_session] = lambda: session

    def required_principal():
        if principal is None:
            raise HTTPException(status_code=401, detail="未提供认证凭据")
        return principal

    app.dependency_overrides[assets_api.get_authenticated_principal] = required_principal
    app.dependency_overrides[assets_api.get_authenticated_principal_optional] = lambda: principal
    return TestClient(app)


def test_asset_update_rejects_other_users_and_keeps_legacy_writable(monkeypatch):
    nodes = {
        "asset-a": _FakeNode("asset-a", "user-a"),
        "asset-legacy": _FakeNode("asset-legacy", None),
    }

    async def fake_card(_session, node, include_metadata=False, version=None, rep=None):
        if not isinstance(node, _FakeNode):
            return None
        return {"id": node.id, "type": "image", "title": node.name, "metadata": {}}

    async def fake_card_by_id(_session, asset_id, include_metadata=True):
        node = nodes.get(asset_id)
        if node is None:
            return None
        return {"id": node.id, "type": "image", "title": node.name, "metadata": {}}

    monkeypatch.setattr(assets_api, "_asset_hub_card", fake_card)
    monkeypatch.setattr(assets_api, "_get_asset_hub_card", fake_card_by_id)

    with _build_client(nodes, _user_principal("user-b")) as other:
        assert other.put("/api/v1/assets/asset-a", json={"title": "hacked"}).status_code == 403
        assert other.put("/api/v1/assets/asset-legacy", json={"title": "legacy-name"}).status_code == 200

    with _build_client(nodes, None) as anonymous:
        assert anonymous.put("/api/v1/assets/asset-a", json={"title": "x"}).status_code == 401

    with _build_client(nodes, _user_principal("user-a")) as owner:
        updated = owner.put("/api/v1/assets/asset-a", json={"title": "renamed"})
        assert updated.status_code == 200
        assert updated.json()["data"]["title"] == "renamed"


def test_asset_restore_requires_credential_and_rejects_other_users(monkeypatch):
    nodes = {
        "asset-a": _FakeNode("asset-a", "user-a", deleted=True),
        "asset-legacy": _FakeNode("asset-legacy", None, deleted=True),
    }

    async def fake_restore(_session, asset_id):
        return asset_id in nodes

    monkeypatch.setattr(assets_api, "_restore_asset_hub_node", fake_restore)

    with _build_client(nodes, None) as anonymous:
        assert anonymous.post("/api/v1/assets/asset-a/restore").status_code == 401

    with _build_client(nodes, _user_principal("user-b")) as other:
        assert other.post("/api/v1/assets/asset-a/restore").status_code == 403
        assert other.post("/api/v1/assets/asset-legacy/restore").status_code == 200


def test_asset_upload_requires_credential_and_writes_session_owner(monkeypatch):
    """Uploads are consumption writes: they need a credential and store its owner."""
    captured: dict = {}

    class FakeFacade:
        def __init__(self, session):
            self.session = session

        async def create_imported_file(self, **kwargs):
            captured.update(kwargs)
            return type("Result", (), {"node_id": "uploaded-1"})()

    monkeypatch.setattr(assets_api, "AssetHubFacade", FakeFacade)
    upload_dir = Path(tempfile.mkdtemp(prefix="ylcraft-upload-"))
    monkeypatch.setattr(assets_api, "_upload_assets_dir", lambda: upload_dir)
    nodes: dict[str, _FakeNode] = {}

    with _build_client(nodes, None) as anonymous:
        resp = anonymous.post(
            "/api/v1/assets/upload",
            files={"file": ("photo.png", b"png-bytes", "image/png")},
            data={"title": "My Photo"},
        )
        assert resp.status_code == 401

    with _build_client(nodes, _user_principal("user-a")) as owner:
        resp = owner.post(
            "/api/v1/assets/upload",
            files={"file": ("photo.png", b"png-bytes", "image/png")},
            data={"title": "My Photo"},
        )
        assert resp.status_code == 200
        assert captured["owner_user_id"] == "user-a"
