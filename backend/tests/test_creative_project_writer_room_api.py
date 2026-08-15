from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import creative_projects as creative_projects_api


def _content(
    *,
    content_id: str,
    project_id: str = "project-1",
    content_type: str,
    text: str,
    version: int = 1,
    source_content_id: str | None = None,
):
    return SimpleNamespace(
        id=content_id,
        project_id=project_id,
        content_type=content_type,
        chapter_number=1,
        episode_number=1,
        title="Entry",
        data_json=json.dumps(
            {
                "chapter_number": 1,
                "title": "Entry",
                "content": text,
                "word_count": len(text),
                "promoted_from_content_id": source_content_id or "",
            },
            ensure_ascii=False,
        ),
        text_content=text,
        source_content_id=source_content_id,
        version=version,
        is_locked=False,
        created_at=datetime(2026, 7, 4, 10, 0, 0),
        updated_at=datetime(2026, 7, 4, 10, 0, 0),
    )


def _project(project_id: str = "project-1"):
    return SimpleNamespace(
        id=project_id,
        title="Writer Room API",
        project_type="novel",
        source_type="original_idea",
        source_ref_json="{}",
        status="draft",
        current_stage="writer_room",
        outline_json="{}",
        chapter_plan_json="{}",
        settings_json="{}",
        metadata_json="{}",
        created_at=datetime(2026, 7, 4, 9, 0, 0),
        updated_at=datetime(2026, 7, 4, 10, 0, 0),
    )


class FakeWriterRoomService:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.project = _project()
        self.old_body = _content(
            content_id="body-1",
            content_type="novel_body",
            text="Original approved prose.",
            version=1,
        )
        self.rewrite = _content(
            content_id="rewrite-1",
            content_type="prose_rewrite",
            text="Candidate rewrite prose.",
            version=1,
            source_content_id=self.old_body.id,
        )
        self.promoted_body = _content(
            content_id="body-2",
            content_type="novel_body",
            text=self.rewrite.text_content,
            version=2,
            source_content_id=self.rewrite.id,
        )
        self.bodies = [self.old_body]
        self.list_calls: list[dict] = []

    async def run_writer_room_step(self, project_id: str, **kwargs):
        self.calls.append(("step", {"project_id": project_id, **kwargs}))
        if kwargs["step"] == "bad_step":
            raise ValueError("writer-room step failed")
        return self.rewrite

    async def run_writer_room(self, project_id: str, **kwargs):
        self.calls.append(("run", {"project_id": project_id, **kwargs}))
        return {
            "project_id": project_id,
            "chapter_number": kwargs["chapter_number"],
            "steps": kwargs["steps"],
            "summary": {"total": len(kwargs["steps"]), "success": len(kwargs["steps"]), "failed": 0},
            "results": [
                {"step": step, "status": "success", "content_id": f"{step}-1"}
                for step in kwargs["steps"]
            ],
        }

    def promote_writer_room_content(self, project_id: str, *, content_id: str):
        self.calls.append(("promote", {"project_id": project_id, "content_id": content_id}))
        if content_id != self.rewrite.id:
            raise ValueError("写作室内容不存在")
        self.bodies.append(self.promoted_body)
        return self.promoted_body

    def get_project(self, project_id: str):
        assert project_id == self.project.id
        return self.project

    def list_contents(self, project_id: str, **kwargs):
        self.list_calls.append({"project_id": project_id, **kwargs})
        return [self.rewrite]


def _client(service: FakeWriterRoomService):
    app = FastAPI()
    app.include_router(creative_projects_api.router, prefix="/api/v1/creative-projects")
    app.dependency_overrides[creative_projects_api.service] = lambda: service
    return TestClient(app)


def test_writer_room_step_api_passes_request_to_service_without_overwriting_body():
    service = FakeWriterRoomService()
    with _client(service) as client:
        response = client.post(
            "/api/v1/creative-projects/project-1/writer-room/step/prose_rewrite",
            json={
                "chapter_number": 1,
                "content_id": "body-1",
                "instruction": "加强结尾钩子",
                "selected_text": "Original paragraph",
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
                "template_id": "template-1",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["content_type"] == "prose_rewrite"
    assert service.bodies == [service.old_body]
    assert service.calls[0] == (
        "step",
        {
            "project_id": "project-1",
            "step": "prose_rewrite",
            "chapter_number": 1,
            "content_id": "body-1",
            "instruction": "加强结尾钩子",
            "selected_text": "Original paragraph",
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "template_id": "template-1",
            "rehearsal_mode": "team",
        },
    )


def test_writer_room_step_api_maps_service_error_to_400():
    service = FakeWriterRoomService()
    with _client(service) as client:
        response = client.post(
            "/api/v1/creative-projects/project-1/writer-room/step/bad_step",
            json={"chapter_number": 1},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "writer-room step failed"


def test_writer_room_run_api_passes_selected_steps():
    service = FakeWriterRoomService()
    with _client(service) as client:
        response = client.post(
            "/api/v1/creative-projects/project-1/writer-room/run",
            json={
                "chapter_number": 2,
                "steps": ["scene_beats", "prose_review"],
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
                "continue_on_error": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["steps"] == ["scene_beats", "prose_review"]
    assert payload["summary"] == {"total": 2, "success": 2, "failed": 0}
    assert service.calls[0][1]["continue_on_error"] is False


def test_contents_api_passes_candidate_filters_and_selected_chapter():
    service = FakeWriterRoomService()
    with _client(service) as client:
        response = client.get(
            "/api/v1/creative-projects/project-1/contents",
            params={
                "content_types": "scene_beats,prose_draft,prose_review",
                "chapter_number": 10,
                "include_history": "true",
            },
        )

    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == service.rewrite.id
    assert service.list_calls == [{
        "project_id": "project-1",
        "content_type": None,
        "content_types": ["scene_beats", "prose_draft", "prose_review"],
        "chapter_number": 10,
        "latest_only": False,
    }]


def test_writer_room_promote_api_creates_new_body_version_and_preserves_old_body():
    service = FakeWriterRoomService()
    with _client(service) as client:
        response = client.post(
            "/api/v1/creative-projects/project-1/writer-room/promote",
            json={"content_id": "rewrite-1"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["content_type"] == "novel_body"
    assert payload["data"]["version"] == 2
    assert payload["data"]["source_content_id"] == "rewrite-1"
    assert payload["project"]["id"] == "project-1"
    assert [body.id for body in service.bodies] == ["body-1", "body-2"]
