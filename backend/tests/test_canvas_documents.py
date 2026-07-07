from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from app.api.v1 import canvas as canvas_api
from app.db.models.canvas import CanvasDocument
from app.services.agent.tools import canvas_tools


@pytest.fixture()
def canvas_session_factory(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'canvas.db'}")
    CanvasDocument.__table__.create(engine)
    factory = sessionmaker(class_=Session, autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(canvas_api, "SessionLocal", factory)
    monkeypatch.setattr(canvas_tools, "SessionLocal", factory)
    yield factory
    engine.dispose()


@pytest.fixture()
def canvas_client(canvas_session_factory):
    app = FastAPI()
    app.include_router(canvas_api.router, prefix="/api/v1/canvas")
    return TestClient(app)


def _document(document_id: str = "canvas-local-1") -> dict:
    return {
        "id": document_id,
        "title": "Storyboard canvas",
        "description": "Free-form test canvas",
        "viewport": {"x": 10, "y": 20, "k": 1.25},
        "nodes": [
            {
                "id": "node-prompt",
                "type": "prompt",
                "title": "Prompt",
                "position": {"x": 80, "y": 120},
                "width": 280,
                "height": 150,
                "metadata": {"prompt": "Write a scene."},
            }
        ],
        "connections": [],
        "createdAt": "2026-07-07T10:00:00",
        "updatedAt": "2026-07-07T10:00:00",
    }


def test_canvas_documents_api_persists_string_ids_and_round_trips(canvas_client):
    create_response = canvas_client.post("/api/v1/canvas/documents", json={"document": _document()})
    assert create_response.status_code == 200
    created = create_response.json()["data"]
    assert created["id"] == "canvas-local-1"
    assert created["title"] == "Storyboard canvas"

    save_response = canvas_client.put(
        "/api/v1/canvas/documents/canvas-local-1",
        json={
            "document": {
                **_document(),
                "title": "Updated canvas",
                "nodes": [
                    *_document()["nodes"],
                    {
                        "id": "node-image",
                        "type": "image_model",
                        "title": "Image",
                        "position": {"x": 380, "y": 120},
                        "width": 280,
                        "height": 150,
                        "metadata": {"size": "1024x1024"},
                    },
                ],
            }
        },
    )
    assert save_response.status_code == 200

    list_response = canvas_client.get("/api/v1/canvas/documents")
    assert list_response.status_code == 200
    listed = list_response.json()["data"]
    assert len(listed) == 1
    assert listed[0]["id"] == "canvas-local-1"
    assert listed[0]["title"] == "Updated canvas"
    assert len(listed[0]["nodes"]) == 2

    delete_response = canvas_client.delete("/api/v1/canvas/documents/canvas-local-1")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_id"] == "canvas-local-1"
    assert canvas_client.get("/api/v1/canvas/documents/canvas-local-1").status_code == 404


@pytest.mark.asyncio
async def test_agent_canvas_tools_apply_operations_to_persisted_document(canvas_session_factory):
    with canvas_session_factory() as session:
        session.add(
            CanvasDocument(
                id="canvas-agent-1",
                title="Agent canvas",
                description="",
                project_id=None,
                document_json=_document("canvas-agent-1"),
            )
        )
        session.commit()

    listed = await canvas_tools.list_creative_canvas_documents()
    assert listed["success"] is True
    assert listed["documents"][0]["id"] == "canvas-agent-1"

    result = await canvas_tools.apply_creative_canvas_operations(
        "canvas-agent-1",
        json.dumps(
            [
                {
                    "op": "add_node",
                    "node": {
                        "id": "node-output",
                        "type": "agent_output",
                        "title": "Agent result",
                        "position": {"x": 500, "y": 160},
                        "width": 260,
                        "height": 140,
                        "metadata": {"content": "done"},
                    },
                },
                {
                    "op": "connect_nodes",
                    "connection": {
                        "id": "conn-agent",
                        "fromNodeId": "node-prompt",
                        "toNodeId": "node-output",
                        "relation": "context",
                    },
                },
            ]
        ),
    )

    assert result["success"] is True
    assert result["applied_count"] == 2
    assert result["summary"]["nodes_count"] == 2
    assert result["summary"]["connections_count"] == 1

    detail = await canvas_tools.get_creative_canvas_document("canvas-agent-1")
    assert detail["document"]["nodes"][-1]["id"] == "node-output"
    assert detail["document"]["connections"][0]["id"] == "conn-agent"
