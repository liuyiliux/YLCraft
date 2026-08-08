from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import creative_projects as creative_projects_api


def _candidate(**overrides):
    base = {
        "id": "cand-1",
        "project_id": "project-1",
        "source_content_id": "body-1",
        "source_generation_log_id": None,
        "source_kind": "prose_review",
        "source_fingerprint": "abc123",
        "entity_type": "character",
        "entity_name": "萧然",
        "claim": "萧然首次意识到存在值规则",
        "evidence_excerpt": "存在值规则在第3段被提及",
        "evidence_anchor_json": json.dumps(
            {"chapter_number": 1, "paragraph_index": 3}, ensure_ascii=False
        ),
        "severity": "info",
        "suggested_action": "create_fact",
        "target_fact_type": "world_asset",
        "status": "pending",
        "resolved_fact_id": None,
        "resolution_note": "",
        "resolved_at": None,
        "created_at": datetime(2026, 8, 3, 10, 0, 0),
        "updated_at": datetime(2026, 8, 3, 10, 0, 0),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class FakeContinuityService:
    def __init__(self):
        self.candidates = {"project-1": [_candidate()]}
        self.calls: list[tuple[str, dict]] = []
        self.locked_facts: dict[str, list[dict]] = {"project-1": []}
        self.fact_provenance: dict[str, list[dict]] = {}

    def _require(self, project_id: str):
        if project_id not in self.candidates:
            raise ValueError("项目不存在")

    def list_continuity_candidates(self, project_id, **kwargs):
        self._require(project_id)
        self.calls.append(("list", {"project_id": project_id, **kwargs}))
        items = list(self.candidates.get(project_id, []))
        status = kwargs.get("status")
        if status:
            items = [c for c in items if c.status == status]
        return items

    def extract_continuity_candidates_v2(self, project_id, content_id, **kwargs):
        self._require(project_id)
        if content_id != "body-1":
            raise ValueError("项目正文不存在")
        candidates_in = kwargs.get("candidates_in") or []
        if not candidates_in:
            raise ValueError("未提供候选事实")
        self.calls.append(
            (
                "extract",
                {"project_id": project_id, "content_id": content_id, **kwargs},
            )
        )
        created = []
        for index, payload in enumerate(candidates_in, start=1):
            created.append(
                _candidate(
                    id=f"cand-new-{index}",
                    entity_type=payload.get("entity_type", "other"),
                    entity_name=payload.get("entity_name", ""),
                    claim=payload.get("claim", ""),
                    evidence_excerpt=(payload.get("evidence_excerpt") or "")[:200],
                    evidence_anchor_json=json.dumps(
                        payload.get("evidence_anchor") or {}, ensure_ascii=False
                    ),
                    severity=payload.get("severity", "info"),
                    suggested_action=payload.get("suggested_action", "create_fact"),
                    target_fact_type=payload.get("target_fact_type", "world_asset"),
                )
            )
        self.candidates.setdefault(project_id, []).extend(created)
        return created

    def accept_continuity_candidate(self, project_id, candidate_id, **kwargs):
        self._require(project_id)
        self.calls.append(
            ("accept", {"project_id": project_id, "candidate_id": candidate_id, **kwargs})
        )
        c = next(
            (x for x in self.candidates.get(project_id, []) if x.id == candidate_id),
            None,
        )
        if not c:
            raise ValueError("连续性候选不存在")
        if c.status != "pending":
            raise ValueError(f"候选状态为 {c.status}，不可再次确认")
        fact_id = f"fact-{len(self.locked_facts.get(project_id, [])) + 1}"
        self.locked_facts.setdefault(project_id, []).append(
            {
                "id": fact_id,
                "entity_name": c.entity_name,
                "is_locked": True,
                "content_type": c.target_fact_type,
                "chapter_number": 1,
            }
        )
        c.status = "accepted"
        c.resolved_fact_id = fact_id
        c.resolved_at = datetime.now()
        return c

    def ignore_continuity_candidate(self, project_id, candidate_id, **kwargs):
        self._require(project_id)
        self.calls.append(
            ("ignore", {"project_id": project_id, "candidate_id": candidate_id, **kwargs})
        )
        c = next(
            (x for x in self.candidates.get(project_id, []) if x.id == candidate_id),
            None,
        )
        if not c:
            raise ValueError("连续性候选不存在")
        if c.status != "pending":
            raise ValueError(f"候选状态为 {c.status}，不可忽略")
        c.status = "ignored"
        c.resolution_note = kwargs.get("note") or ""
        return c

    def merge_continuity_candidate(self, project_id, candidate_id, **kwargs):
        self._require(project_id)
        merged_fact_id = kwargs.get("merged_fact_id")
        if not merged_fact_id:
            raise ValueError("merged_fact_id 不能为空")
        self.calls.append(
            ("merge", {"project_id": project_id, "candidate_id": candidate_id, **kwargs})
        )
        c = next(
            (x for x in self.candidates.get(project_id, []) if x.id == candidate_id),
            None,
        )
        if not c:
            raise ValueError("连续性候选不存在")
        if c.status != "pending":
            raise ValueError(f"候选状态为 {c.status}，不可合并")
        c.status = "merged"
        c.resolved_fact_id = merged_fact_id
        c.resolution_note = kwargs.get("note") or ""
        self.fact_provenance.setdefault(merged_fact_id, []).append(
            {"candidate_id": c.id, "source_content_id": c.source_content_id}
        )
        return c

    def build_continuity_context_summary(self, project_id, **kwargs):
        return {
            "project_id": project_id,
            "locked_fact_count": len(self.locked_facts.get(project_id, [])),
            "fact_types": {
                "project_bible": sum(
                    1
                    for f in self.locked_facts.get(project_id, [])
                    if f["content_type"] == "project_bible"
                ),
                "world_asset": sum(
                    1
                    for f in self.locked_facts.get(project_id, [])
                    if f["content_type"] == "world_asset"
                ),
            },
            "source_chapters": sorted(
                {int(f["chapter_number"]) for f in self.locked_facts.get(project_id, [])}
            ),
            "pending_candidate_count": sum(
                1
                for c in self.candidates.get(project_id, [])
                if c.status == "pending"
            ),
            "fingerprint": "deadbeef",
        }


def _client(service: FakeContinuityService):
    app = FastAPI()
    app.include_router(
        creative_projects_api.router, prefix="/api/v1/creative-projects"
    )
    app.dependency_overrides[creative_projects_api.service] = lambda: service
    return TestClient(app)


def test_list_continuity_candidates_returns_pending():
    service = FakeContinuityService()
    with _client(service) as client:
        response = client.get(
            "/api/v1/creative-projects/project-1/continuity-candidates?status=pending"
        )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["entity_name"] == "萧然"
    assert data[0]["status"] == "pending"
    assert data[0]["evidence_anchor"] == {
        "chapter_number": 1,
        "paragraph_index": 3,
    }


def test_extract_continuity_candidates_creates_pending_candidates():
    service = FakeContinuityService()
    with _client(service) as client:
        response = client.post(
            "/api/v1/creative-projects/project-1/contents/body-1/continuity-candidates/extract",
            json={
                "source_kind": "prose_review",
                "candidates": [
                    {
                        "entity_type": "event",
                        "entity_name": "苏棠觉醒",
                        "claim": "苏棠在循环中觉醒",
                        "evidence_excerpt": "第十章末尾她突然停下脚步",
                        "evidence_anchor": {"chapter_number": 10, "paragraph_index": 12},
                        "severity": "warning",
                        "suggested_action": "create_fact",
                        "target_fact_type": "world_asset",
                    }
                ],
            },
        )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload[0]["status"] == "pending"
    assert payload[0]["entity_name"] == "苏棠觉醒"
    assert payload[0]["severity"] == "warning"
    assert service.calls[0][0] == "extract"


def test_accept_continuity_candidate_writes_locked_fact():
    service = FakeContinuityService()
    with _client(service) as client:
        response = client.post(
            "/api/v1/creative-projects/project-1/continuity-candidates/cand-1/accept",
            json={"note": "已确认"},
        )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "accepted"
    assert data["resolved_fact_id"] == "fact-1"
    assert service.locked_facts["project-1"][0]["is_locked"] is True
    assert service.locked_facts["project-1"][0]["content_type"] == "world_asset"


def test_ignore_continuity_candidate_marks_terminal_state():
    service = FakeContinuityService()
    with _client(service) as client:
        response = client.post(
            "/api/v1/creative-projects/project-1/continuity-candidates/cand-1/ignore",
            json={"note": "先不锁"},
        )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "ignored"
    assert data["resolution_note"] == "先不锁"


def test_merge_requires_merged_fact_id():
    service = FakeContinuityService()
    with _client(service) as client:
        response = client.post(
            "/api/v1/creative-projects/project-1/continuity-candidates/cand-1/merge",
            json={"note": "并入既有事实"},
        )
    assert response.status_code == 400


def test_merge_records_provenance_on_existing_fact():
    service = FakeContinuityService()
    service.locked_facts["project-1"].append(
        {"id": "fact-existing", "entity_name": "苏棠", "is_locked": True,
         "content_type": "world_asset", "chapter_number": 1}
    )
    with _client(service) as client:
        response = client.post(
            "/api/v1/creative-projects/project-1/continuity-candidates/cand-1/merge",
            json={"merged_fact_id": "fact-existing", "note": "同事实，多源"},
        )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "merged"
    assert data["resolved_fact_id"] == "fact-existing"
    assert service.fact_provenance["fact-existing"][0]["candidate_id"] == "cand-1"


def test_context_summary_reports_locked_and_pending():
    service = FakeContinuityService()
    service.locked_facts["project-1"].append(
        {"id": "f1", "entity_name": "苏棠", "is_locked": True,
         "content_type": "world_asset", "chapter_number": 1}
    )
    with _client(service) as client:
        response = client.get(
            "/api/v1/creative-projects/project-1/continuity-candidates/context-summary"
        )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["locked_fact_count"] == 1
    assert data["pending_candidate_count"] == 1
    assert data["fact_types"]["world_asset"] == 1


def test_decision_api_rejects_unknown_candidate():
    service = FakeContinuityService()
    with _client(service) as client:
        response = client.post(
            "/api/v1/creative-projects/project-1/continuity-candidates/missing/accept"
        )
    assert response.status_code == 400


def test_extract_validates_project_and_content_ownership():
    service = FakeContinuityService()
    with _client(service) as client:
        response = client.post(
            "/api/v1/creative-projects/project-1/contents/other-body/continuity-candidates/extract",
            json={"candidates": [{"entity_type": "other", "claim": "x"}]},
        )
    assert response.status_code == 400