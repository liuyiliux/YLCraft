from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import creative_projects as creative_projects_api


def _candidate(candidate_id: str = "candidate-1"):
    return SimpleNamespace(
        id=candidate_id,
        project_id="project-1",
        source_content_id="content-1",
        source_generation_log_id=None,
        source_kind="prose_review",
        source_fingerprint="fp1",
        entity_type="character",
        entity_name="林昭",
        claim="林昭 28 岁",
        evidence_excerpt="林昭今年 28 岁。",
        evidence_anchor_json='{"chapter_number": 2, "paragraph_index": 1}',
        severity="warning",
        suggested_action="create_fact",
        target_fact_type="world_asset",
        status="pending",
        resolved_fact_id=None,
        resolution_note="",
        resolved_at=None,
        created_at=datetime(2026, 8, 4, 10, 0, 0),
        updated_at=datetime(2026, 8, 4, 10, 0, 0),
    )


class FakeContinuityService:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def check_continuity(self, project_id: str, chapter_number: int, *, candidate_id: str | None = None):
        self.calls.append(("check_continuity", {
            "project_id": project_id,
            "chapter_number": chapter_number,
            "candidate_id": candidate_id,
        }))
        return {
            "project_id": project_id,
            "chapter_number": chapter_number,
            "candidate_id": candidate_id,
            "checked_claims": ["林昭 28 岁"],
            "conflicts": [],
            "skipped": False,
            "skip_reason": "",
        }

    async def rewrite_paragraph(
        self,
        project_id: str,
        content_id: str,
        paragraph_index: int,
        instruction: str,
        *,
        provider: str | None = None,
        model: str | None = None,
    ):
        self.calls.append(("rewrite_paragraph", {
            "project_id": project_id,
            "content_id": content_id,
            "paragraph_index": paragraph_index,
            "instruction": instruction,
            "provider": provider,
            "model": model,
        }))
        return {
            "content_id": content_id,
            "project_id": project_id,
            "source_content_id": content_id,
            "paragraph_index": paragraph_index,
            "original_paragraph": "原文。",
            "rewritten_paragraph": "重写后。",
            "status": "candidate",
            "anchor_not_found": False,
            "candidate_content_id": "candidate-content-1",
            "instruction": instruction,
        }


def _client(service: FakeContinuityService):
    app = FastAPI()
    app.include_router(creative_projects_api.router, prefix="/api/v1/creative-projects")
    app.dependency_overrides[creative_projects_api.service] = lambda: service
    return TestClient(app)


def test_check_continuity_api_passes_candidate_id():
    service = FakeContinuityService()
    with _client(service) as client:
        response = client.post(
            "/api/v1/creative-projects/project-1/chapters/3/check-continuity",
            json={"candidate_id": "candidate-1"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["candidate_id"] == "candidate-1"
    assert service.calls[0] == (
        "check_continuity",
        {"project_id": "project-1", "chapter_number": 3, "candidate_id": "candidate-1"},
    )


def test_check_continuity_api_accepts_empty_body():
    service = FakeContinuityService()
    with _client(service) as client:
        response = client.post(
            "/api/v1/creative-projects/project-1/chapters/2/check-continuity",
            json={},
        )

    assert response.status_code == 200
    assert service.calls[0] == (
        "check_continuity",
        {"project_id": "project-1", "chapter_number": 2, "candidate_id": None},
    )


@pytest.mark.asyncio
async def test_rewrite_paragraph_api_passes_request_to_service():
    service = FakeContinuityService()
    with _client(service) as client:
        response = client.post(
            "/api/v1/creative-projects/project-1/contents/content-1/rewrite-paragraph",
            json={
                "paragraph_index": 2,
                "instruction": "让林昭更紧张",
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["candidate_content_id"] == "candidate-content-1"
    assert service.calls[0] == (
        "rewrite_paragraph",
        {
            "project_id": "project-1",
            "content_id": "content-1",
            "paragraph_index": 2,
            "instruction": "让林昭更紧张",
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
        },
    )
