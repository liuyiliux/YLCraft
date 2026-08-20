from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from app.api.v1 import previs as previs_api
from app.db.models.previs import PrevisSceneDocument


@pytest.fixture()
def previs_session_factory(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'previs.db'}")
    PrevisSceneDocument.__table__.create(engine)
    factory = sessionmaker(class_=Session, autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(previs_api, "SessionLocal", factory)
    yield factory
    engine.dispose()


@pytest.fixture()
def previs_client(previs_session_factory):
    app = FastAPI()
    app.include_router(previs_api.router, prefix="/api/v1/previs")
    return TestClient(app)


def _create_payload(**overrides) -> dict:
    payload = {
        "project_id": "project-1",
        "storyboard_content_id": "content-1",
        "panel_number": 1,
        "title": "第 1 镜预演",
        "scene": {
            "fps": 24,
            "durationFrames": 0,
            "activeCameraId": "cam-1",
            "nodes": [{"id": "node-1", "kind": "asset_model", "name": "角色", "assetId": "asset-1"}],
            "cameras": [{"id": "cam-1", "name": "机位 1", "fov": 50}],
            "keyframes": [],
            "settings": {},
        },
    }
    payload.update(overrides)
    return payload


def test_previs_scene_create_and_round_trip(previs_client):
    create_response = previs_client.post("/api/v1/previs/scenes", json=_create_payload())
    assert create_response.status_code == 200
    created = create_response.json()["data"]
    assert created["project_id"] == "project-1"
    assert created["storyboard_content_id"] == "content-1"
    assert created["panel_number"] == 1
    assert created["revision"] == 1
    assert created["scene"]["nodes"][0]["id"] == "node-1"

    get_response = previs_client.get(f"/api/v1/previs/scenes/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["data"]["revision"] == 1


def test_previs_scene_rejects_duplicate_panel(previs_client):
    first = previs_client.post("/api/v1/previs/scenes", json=_create_payload())
    assert first.status_code == 200

    duplicate = previs_client.post("/api/v1/previs/scenes", json=_create_payload())
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]


def test_previs_scene_save_requires_matching_revision(previs_client):
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]
    scene_id = created["id"]

    save_response = previs_client.put(
        f"/api/v1/previs/scenes/{scene_id}",
        json={"expected_revision": 1, "title": "更新后", "scene": created["scene"]},
    )
    assert save_response.status_code == 200
    assert save_response.json()["data"]["revision"] == 2

    stale_response = previs_client.put(
        f"/api/v1/previs/scenes/{scene_id}",
        json={"expected_revision": 1, "title": "过期保存", "scene": created["scene"]},
    )
    assert stale_response.status_code == 409
    detail = stale_response.json()["detail"]
    assert detail["current_revision"] == 2
    assert detail["expected_revision"] == 1


def test_previs_scene_list_filters_by_panel(previs_client):
    previs_client.post("/api/v1/previs/scenes", json=_create_payload())
    previs_client.post(
        "/api/v1/previs/scenes",
        json=_create_payload(panel_number=2, title="第 2 镜预演"),
    )

    all_response = previs_client.get("/api/v1/previs/scenes?project_id=project-1")
    assert all_response.status_code == 200
    assert all_response.json()["total"] == 2

    filtered = previs_client.get(
        "/api/v1/previs/scenes?project_id=project-1&storyboard_content_id=content-1&panel_number=2"
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["data"][0]["panel_number"] == 2


def test_previs_scene_delete(previs_client):
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]
    scene_id = created["id"]

    delete_response = previs_client.delete(f"/api/v1/previs/scenes/{scene_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_id"] == scene_id
    assert previs_client.get(f"/api/v1/previs/scenes/{scene_id}").status_code == 404


def test_previs_scene_rejects_non_object_scene(previs_client):
    response = previs_client.post(
        "/api/v1/previs/scenes",
        json=_create_payload(scene="not-an-object"),
    )
    assert response.status_code == 422
