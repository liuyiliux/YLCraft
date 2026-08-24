from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import JSON, String
from sqlmodel import Session, create_engine, select
from sqlalchemy.pool import StaticPool

from app.api.v1 import creative_projects as creative_projects_api
from app.db.models.asset_hub import AssetNode, AssetType
from app.db.models.character import Character, CharacterStoryLink
from app.db.models.creative_project import (
    CreativeProject,
    ProjectAssetLink,
    ProjectContent,
    ProjectContinuityCandidate,
    ProjectForeshadowing,
    ProjectGenerationLog,
    ProjectNarrativeRun,
    ProjectNarrativeContextSnapshot,
    ProjectNarrativeSnapshot,
    ProjectStoryEvent,
    ProjectStyleMeasurement,
    NarrativeRunStatus,
)
from app.db.models.task import ProjectTaskRecord
from app.db.models.novel import NovelChapter
from app.services.creative_project.service import CreativeProjectService
from app.services.agent import context_pack as agent_context_pack
from tests.test_creative_project_service import FakeAIService


@pytest.fixture
def workflow_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # AssetNode uses PostgreSQL JSONB in production. Use SQLite JSON for this
    # API contract test so the test remains local and does not require PG.
    for column_name in ("metadata_json", "tags_json"):
        AssetNode.__table__.c[column_name].type = JSON()
    for column_name in ("id", "parent_id"):
        AssetNode.__table__.c[column_name].type = String(36)
    for table in (
        AssetNode.__table__,
        NovelChapter.__table__,
        Character.__table__,
        CharacterStoryLink.__table__,
        CreativeProject.__table__,
        ProjectContent.__table__,
        ProjectAssetLink.__table__,
        ProjectGenerationLog.__table__,
        ProjectContinuityCandidate.__table__,
        ProjectTaskRecord.__table__,
        ProjectNarrativeRun.__table__,
        ProjectNarrativeContextSnapshot.__table__,
        ProjectNarrativeSnapshot.__table__,
        ProjectStoryEvent.__table__,
        ProjectForeshadowing.__table__,
        ProjectStyleMeasurement.__table__,
    ):
        table.create(engine)
    with Session(engine) as session:
        yield session


def _client(session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(creative_projects_api.router, prefix="/api/v1/creative-projects")
    project_service = CreativeProjectService(session, ai_service=FakeAIService())
    app.dependency_overrides[creative_projects_api.service] = lambda: project_service
    return TestClient(app)


def _post(client: TestClient, path: str, payload: dict | None = None) -> dict:
    route = f"/api/v1/creative-projects{path or '/'}"
    response = client.post(route, json=payload or {})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True, body
    return body


async def test_idea_api_chain_reaches_comic_pages(workflow_session: Session):
    with _client(workflow_session) as client:
        project = _post(
            client,
            "",
            {
                "title": "API chain project",
                "idea": "A video editor follows an evidence trail.",
                "project_type": "short_drama",
            },
        )["data"]
        project_id = project["id"]

        _post(client, f"/{project_id}/generate-outline")
        _post(client, f"/{project_id}/generate-chapter-plan", {"chapter_count": 2})
        _post(client, f"/{project_id}/generate-chapter-outline", {"chapter_number": 1})
        _post(client, f"/{project_id}/generate-novel-body", {"chapter_number": 1})
        _post(client, f"/{project_id}/generate-script", {"chapter_number": 1})
        script = workflow_session.exec(
            select(ProjectContent)
            .where(ProjectContent.project_id == project_id)
            .where(ProjectContent.content_type == "script")
        ).one()
        _post(client, f"/{project_id}/generate-storyboard", {"content_id": script.id})
        storyboard = workflow_session.exec(
            select(ProjectContent)
            .where(ProjectContent.project_id == project_id)
            .where(ProjectContent.content_type == "storyboard")
        ).one()
        _post(
            client,
            f"/{project_id}/split-comic-pages",
            {"chapter_number": 1, "content_id": storyboard.id, "page_count": 2},
        )

    content_types = {
        content.content_type
        for content in workflow_session.exec(
            select(ProjectContent).where(ProjectContent.project_id == project_id)
        ).all()
    }
    assert {"outline", "chapter_plan", "chapter_outline", "novel_body", "script", "storyboard", "comic_pages"} <= content_types
    assert workflow_session.exec(
        select(ProjectGenerationLog).where(ProjectGenerationLog.project_id == project_id)
    ).all()


def test_novel_import_api_chain_reaches_script(workflow_session: Session):
    asset_id = str(uuid.uuid4())
    workflow_session.add(
        AssetNode(
            id=asset_id,
            name="Imported novel",
            asset_type=AssetType.TEXT,
            metadata_json={"title": "Imported novel", "author": "Test author"},
        )
    )
    chapter = NovelChapter(
        asset_id=asset_id,
        chapter_index=1,
        chapter_title="The first clue",
        content_path="",
        content_length=0,
        is_downloaded=False,
    )
    workflow_session.add(chapter)
    workflow_session.commit()

    with _client(workflow_session) as client:
        project = _post(
            client,
            "/from-novel",
            {
                "asset_id": asset_id,
                "chapter_ids": [chapter.id],
                "title": "Imported project",
                "project_type": "novel",
            },
        )["data"]
        project_id = project["id"]
        assert project["source_type"] == "novel"
        assert project["source_ref"]["chapter_ids"] == [chapter.id]

        _post(client, f"/{project_id}/generate-outline")
        _post(client, f"/{project_id}/generate-chapter-plan", {"chapter_count": 1})
        _post(client, f"/{project_id}/generate-script", {"chapter_number": 1})

    script = workflow_session.exec(
        select(ProjectContent)
        .where(ProjectContent.project_id == project_id)
        .where(ProjectContent.content_type == "script")
    ).one()
    assert script.chapter_number == 1
    assert script.source_content_id is None


def test_contents_api_hides_history_unless_explicitly_requested(workflow_session: Session):
    with _client(workflow_session) as client:
        project = _post(
            client,
            "",
            {"title": "Versioned project", "idea": "A writer revises one chapter."},
        )["data"]
        project_id = project["id"]
        first = ProjectContent(
            project_id=project_id,
            content_type="novel_body",
            chapter_number=1,
            title="Draft",
            text_content="first version",
            version=1,
        )
        second = ProjectContent(
            project_id=project_id,
            content_type="novel_body",
            chapter_number=1,
            title="Revised",
            text_content="latest version",
            version=2,
        )
        workflow_session.add(first)
        workflow_session.add(second)
        workflow_session.commit()

        current = client.get(f"/api/v1/creative-projects/{project_id}/contents")
        history = client.get(f"/api/v1/creative-projects/{project_id}/contents?include_history=true")

    assert current.status_code == 200, current.text
    assert history.status_code == 200, history.text
    assert [item["id"] for item in current.json()["data"]] == [second.id]
    assert {item["id"] for item in history.json()["data"]} == {first.id, second.id}


def test_update_project_api_rejects_duplicate_chapter_numbers(workflow_session: Session):
    with _client(workflow_session) as client:
        project = _post(
            client,
            "",
            {"title": "Plan validation", "idea": "A duplicate should be rejected."},
        )["data"]
        response = client.patch(
            f"/api/v1/creative-projects/{project['id']}",
            json={
                "chapter_plan": {
                    "chapters": [
                        {"chapter_number": 1, "title": "One"},
                        {"chapter_number": 1, "title": "Duplicate one"},
                    ]
                }
            },
        )

    assert response.status_code == 400, response.text
    assert "章节号重复" in response.json()["detail"]


def test_production_plan_api_versions_and_keeps_project_asset_association(workflow_session: Session):
    asset_id = str(uuid.uuid4())
    workflow_session.add(
        AssetNode(
            id=asset_id,
            name="Main character reference",
            asset_type=AssetType.IMAGE,
            metadata_json={},
        )
    )
    workflow_session.commit()

    with _client(workflow_session) as client:
        project = _post(
            client,
            "",
            {
                "title": "Horror comic",
                "idea": "A child finds a moving portrait.",
                "project_type": "manga",
                "production_profile": "storybook",
            },
        )["data"]
        source = ProjectContent(
            project_id=project["id"],
            content_type="outline",
            title="Story seed",
            data_json="{}",
        )
        workflow_session.add(source)
        workflow_session.commit()

        first = client.put(
            f"/api/v1/creative-projects/{project['id']}/production-plan",
            json={
                "plan": {
                    "title": "Horror comic plan",
                    "goal": "Finish a four-page horror comic.",
                    "production_profile": "storybook",
                    "asset_ids": [asset_id],
                    "nodes": [
                        {
                            "id": "story",
                            "stage": "story_seed",
                            "label": "Story and page beats",
                            "specialist_role": "story-designer",
                            "input_content_ids": [source.id],
                            "planning_summary": {"intent": "Set up an unsettling portrait."},
                            "requires_confirmation": True,
                        },
                        {
                            "id": "visual",
                            "stage": "image",
                            "label": "Plan page art",
                            "specialist_role": "visual-director",
                            "depends_on": ["story"],
                            "input_asset_ids": [asset_id],
                            "planning_summary": {"expected_output": "storyboard_frame"},
                            "requires_confirmation": True,
                        },
                    ],
                }
            },
        )
        assert first.status_code == 200, first.text
        first_plan = first.json()["data"]
        assert first_plan["content_type"] == "production_plan"
        assert first_plan["version"] == 1
        assert first_plan["data"]["plan_version"] == 1
        assert first_plan["data"]["project_id"] == project["id"]

        second = client.put(
            f"/api/v1/creative-projects/{project['id']}/production-plan",
            json={
                "base_plan_id": first_plan["id"],
                "plan": {
                    "title": "Horror comic plan",
                    "goal": "Revise only page three composition.",
                    "production_profile": "storybook",
                    "asset_ids": [asset_id],
                    "nodes": [
                        {
                            "id": "story",
                            "stage": "story_seed",
                            "label": "Story and page beats",
                            "specialist_role": "story-designer",
                            "input_content_ids": [source.id],
                        },
                        {
                            "id": "visual",
                            "stage": "image",
                            "label": "Revise page three composition",
                            "specialist_role": "visual-director",
                            "depends_on": ["story"],
                            "input_asset_ids": [asset_id],
                            "rerun_scope": "downstream",
                        },
                    ],
                },
            },
        )
        assert second.status_code == 200, second.text
        second_plan = second.json()["data"]
        current = client.get(f"/api/v1/creative-projects/{project['id']}/production-plan")
        history = client.get(f"/api/v1/creative-projects/{project['id']}/production-plan?include_history=true")
        links = client.get(f"/api/v1/creative-projects/{project['id']}/assets")

    assert second_plan["version"] == 2
    assert second_plan["source_content_id"] == first_plan["id"]
    assert second_plan["data"]["source_plan_id"] == first_plan["id"]
    assert current.json()["data"]["id"] == second_plan["id"]
    assert {item["id"] for item in history.json()["data"]} == {first_plan["id"], second_plan["id"]}
    assert any(
        item["asset_id"] == asset_id and item["content_id"] == second_plan["id"] and item["role"] == "production_plan"
        for item in links.json()["data"]
    )


def test_production_plan_api_rejects_cycles_before_saving(workflow_session: Session):
    with _client(workflow_session) as client:
        project = _post(client, "", {"title": "Invalid plan", "idea": "No loops."})["data"]
        response = client.put(
            f"/api/v1/creative-projects/{project['id']}/production-plan",
            json={
                "plan": {
                    "nodes": [
                        {"id": "first", "depends_on": ["second"]},
                        {"id": "second", "depends_on": ["first"]},
                    ]
                }
            },
        )

    assert response.status_code == 422, response.text
    assert "依赖不能形成循环" in response.text


def test_agent_context_pack_includes_profile_and_visible_production_plan(
    workflow_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    with _client(workflow_session) as client:
        project = _post(
            client,
            "",
            {
                "title": "Storybook context",
                "idea": "A child notices a portrait blink.",
                "production_profile": "storybook",
            },
        )["data"]
        saved = client.put(
            f"/api/v1/creative-projects/{project['id']}/production-plan",
            json={
                "plan": {
                    "title": "Visible director plan",
                    "goal": "Plan a four-page illustrated story.",
                    "production_profile": "storybook",
                    "confirmation_status": "pending",
                    "nodes": [
                        {
                            "id": "visual",
                            "stage": "image",
                            "label": "Plan the first page",
                            "specialist_role": "visual-director",
                            "planning_summary": {"intent": "A portrait blinks in candlelight."},
                            "requires_confirmation": True,
                        }
                    ],
                }
            },
        )
        assert saved.status_code == 200, saved.text

    monkeypatch.setattr(agent_context_pack, "SessionLocal", lambda: workflow_session)
    monkeypatch.setattr(
        "app.services.ai.get_ai_service",
        lambda: FakeAIService(),
    )
    pack = agent_context_pack.build_creative_project_context_pack(project["id"])

    assert pack["project"]["production_profile"]["id"] == "storybook"
    assert pack["project"]["production_profile"]["label"]
    assert pack["production_plan"]["content_id"] == saved.json()["data"]["id"]
    assert pack["production_plan"]["confirmation_status"] == "pending"
    assert pack["production_plan"]["confirmation_nodes"] == [
        {"id": "visual", "label": "Plan the first page", "stage": "image", "status": "planned"}
    ]
    assert pack["production_plan"]["nodes"][0]["planning_summary"] == {"intent": "A portrait blinks in candlelight."}


def test_narrative_health_api_reports_legacy_plan_and_missing_dependencies(workflow_session: Session):
    with _client(workflow_session) as client:
        project = _post(
            client,
            "",
            {"title": "Narrative health", "idea": "A chapter plan needs repair."},
        )["data"]
        project_id = project["id"]
        stored = workflow_session.get(CreativeProject, project_id)
        assert stored is not None
        stored.chapter_plan_json = '{"chapter_count": 5, "chapters": [{"chapter_number": 1}, {"chapter_number": 3}]}'
        workflow_session.add_all([
            ProjectContent(
                project_id=project_id,
                content_type="novel_body",
                chapter_number=1,
                title="Body A",
                text_content="first",
                version=2,
            ),
            ProjectContent(
                project_id=project_id,
                content_type="novel_body",
                chapter_number=1,
                title="Body B",
                text_content="duplicate latest",
                version=2,
            ),
            ProjectContent(
                project_id=project_id,
                content_type="prose_humanized",
                chapter_number=1,
                title="Detached candidate",
                source_content_id="missing-upstream",
                version=1,
            ),
            ProjectAssetLink(project_id=project_id, asset_id="deleted-asset"),
        ])
        workflow_session.commit()

        response = client.get(f"/api/v1/creative-projects/{project_id}/narrative/health")

    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["status"] == "blocked"
    assert payload["summary"]["valid_chapter_count"] == 2
    assert {item["code"] for item in payload["issues"]} >= {
        "chapter_plan_count_mismatch",
        "chapter_plan_gaps",
        "duplicate_latest_novel_body",
        "writer_room_missing_source",
        "unavailable_linked_asset",
    }


def test_narrative_health_route_is_present_in_creative_project_api_contract():
    from app.main import app as main_app

    paths = {route.path for route in main_app.routes}

    assert "/api/v1/creative-projects/{project_id}/narrative/health" in paths


def test_narrative_context_preview_api_is_read_only(workflow_session: Session):
    project = CreativeProject(title="Context preview", chapter_plan_json='{"chapters": [{"chapter_number": 2, "goal": "A decision"}]}')
    workflow_session.add(project)
    workflow_session.commit()

    with _client(workflow_session) as client:
        response = client.get(
            f"/api/v1/creative-projects/{project.id}/narrative/context-preview",
            params={"chapter_number": 2},
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["chapter_number"] == 2
    assert data["persisted"] is False
    assert data["metadata"]["layers"][3]["id"] == "T3"
    assert workflow_session.exec(select(ProjectNarrativeContextSnapshot)).all() == []


def test_foreshadowing_ledger_and_narrative_graph_api(workflow_session: Session):
    project = CreativeProject(title="Ledger API")
    workflow_session.add(project)
    workflow_session.flush()
    body = ProjectContent(project_id=project.id, content_type="novel_body", chapter_number=1, text_content="A clue")
    workflow_session.add(body)
    workflow_session.flush()
    item = ProjectForeshadowing(
        project_id=project.id,
        source_content_id=body.id,
        chapter_number=1,
        planted_chapter=1,
        statement="The receipt number",
        status="pending_review",
    )
    workflow_session.add(item)
    workflow_session.commit()

    with _client(workflow_session) as client:
        listed = client.get(f"/api/v1/creative-projects/{project.id}/foreshadowing")
        assert listed.status_code == 200, listed.text
        assert listed.json()["data"]["data"][0]["status"] == "pending_review"
        accepted = client.post(
            f"/api/v1/creative-projects/{project.id}/foreshadowing/{item.id}/accept",
            json={"note": "Keep it active", "current_chapter": 1},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["data"]["status"] == "active"
        graph = client.get(f"/api/v1/creative-projects/{project.id}/narrative-graph")
        assert graph.status_code == 200, graph.text
        assert "The receipt number" in {node["label"] for node in graph.json()["data"]["nodes"]}


def test_narrative_aftermath_api_is_idempotent_and_rejects_unknown_version(workflow_session: Session):
    with _client(workflow_session) as client:
        project = _post(
            client,
            "",
            {"title": "Aftermath API", "idea": "A receipt is hidden."},
        )["data"]
        body = ProjectContent(
            project_id=project["id"],
            content_type="novel_body",
            chapter_number=1,
            title="The receipt",
            text_content="她把收据夹进旧书里。",
            data_json='{"foreshadowing": ["旧收据上的编号"]}',
        )
        workflow_session.add(body)
        workflow_session.commit()

        first = client.post(
            f"/api/v1/creative-projects/{project['id']}/contents/{body.id}/aftermath",
            json={"pipeline_version": "v1"},
        )
        second = client.post(
            f"/api/v1/creative-projects/{project['id']}/contents/{body.id}/aftermath",
            json={"pipeline_version": "v1"},
        )
        rebuild = client.post(
            f"/api/v1/creative-projects/{project['id']}/narrative/rebuild",
            json={"chapter_numbers": [1]},
        )
        unsupported = client.post(
            f"/api/v1/creative-projects/{project['id']}/contents/{body.id}/aftermath",
            json={"pipeline_version": "v999"},
        )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["data"]["reused"] is False
    assert second.json()["data"]["reused"] is True
    assert rebuild.status_code == 200, rebuild.text
    assert rebuild.json()["data"]["status"] == "success"
    assert rebuild.json()["data"]["run_id"]
    assert rebuild.json()["data"]["summary"] == {"total": 1, "reused": 1, "created": 0}
    assert unsupported.status_code == 400
    assert "不支持的叙事后处理版本" in unsupported.json()["detail"]


def test_narrative_runs_api_exposes_durable_aftermath_trace(workflow_session: Session):
    with _client(workflow_session) as client:
        project = _post(client, "", {"title": "Narrative runs", "idea": "A clue in a book."})["data"]
        body = ProjectContent(
            project_id=project["id"], content_type="novel_body", chapter_number=1,
            title="Chapter one", text_content="她把线索夹回书页。",
        )
        workflow_session.add(body)
        workflow_session.commit()
        created = client.post(
            f"/api/v1/creative-projects/{project['id']}/contents/{body.id}/aftermath",
            json={"pipeline_version": "v1"},
        )
        listed = client.get(f"/api/v1/creative-projects/{project['id']}/narrative/runs")

    assert created.status_code == 200, created.text
    assert listed.status_code == 200, listed.text
    run = listed.json()["data"][0]
    assert run["id"] == created.json()["data"]["run_id"]
    assert run["mode"] == "manual"
    assert run["status"] == "success"
    assert run["target_chapters"] == [1]
    assert run["trace"]


def test_narrative_batch_run_controls_use_non_terminal_state_transitions(workflow_session: Session):
    project = CreativeProject(title="Controlled narrative run")
    workflow_session.add(project)
    workflow_session.flush()
    run = ProjectNarrativeRun(
        project_id=project.id,
        mode="batch",
        status=NarrativeRunStatus.RUNNING.value,
        target_chapters_json="[1, 2]",
    )
    workflow_session.add(run)
    workflow_session.commit()
    with _client(workflow_session) as client:
        paused = client.post(f"/api/v1/creative-projects/{project.id}/narrative/runs/{run.id}/pause")
        resumed = client.post(f"/api/v1/creative-projects/{project.id}/narrative/runs/{run.id}/resume")
        cancelled = client.post(f"/api/v1/creative-projects/{project.id}/narrative/runs/{run.id}/cancel")
        again = client.post(f"/api/v1/creative-projects/{project.id}/narrative/runs/{run.id}/resume")

    assert paused.json()["data"]["status"] == "paused"
    assert resumed.json()["data"]["status"] == "pending"
    assert cancelled.json()["data"]["status"] == "cancelled"
    assert again.status_code == 409


def test_narrative_retry_resumes_from_first_failed_chapter_and_keeps_budget(workflow_session: Session):
    project = CreativeProject(title="Retryable narrative run")
    workflow_session.add(project)
    workflow_session.flush()
    run = ProjectNarrativeRun(
        project_id=project.id,
        mode="batch",
        status=NarrativeRunStatus.PARTIAL.value,
        target_chapters_json="[1, 2, 3]",
        current_cursor=3,
        trace_json=(
            '[{"chapter_number": 1, "status": "success"}, '
            '{"chapter_number": 2, "status": "failed", "error_type": "ProviderUnavailable", "retryable": true}, '
            '{"chapter_number": 3, "status": "success"}]'
        ),
        input_json='{"budget": {"max_cost_amount": 3.5, "max_token_usage": 1200}}',
        error_message="provider unavailable",
    )
    workflow_session.add(run)
    workflow_session.commit()

    with _client(workflow_session) as client:
        retried = client.post(f"/api/v1/creative-projects/{project.id}/narrative/runs/{run.id}/retry")
        listed = client.get(f"/api/v1/creative-projects/{project.id}/narrative/runs")

    assert retried.status_code == 200, retried.text
    data = retried.json()["data"]
    assert data["status"] == "pending"
    assert data["current_cursor"] == 1
    assert data["retry_count"] == 1
    assert data["error_message"] == ""
    assert data["budget"] == {"max_cost_amount": 3.5, "max_token_usage": 1200}
    assert listed.json()["data"][0]["id"] == run.id


def test_narrative_retry_rejects_terminal_success_and_missing_failure_trace(workflow_session: Session):
    project = CreativeProject(title="Non retryable narrative run")
    workflow_session.add(project)
    workflow_session.flush()
    success = ProjectNarrativeRun(project_id=project.id, mode="batch", status=NarrativeRunStatus.SUCCESS.value)
    partial_without_failure = ProjectNarrativeRun(
        project_id=project.id,
        mode="batch",
        status=NarrativeRunStatus.PARTIAL.value,
        target_chapters_json="[1]",
        trace_json='[{"chapter_number": 1, "status": "success"}]',
    )
    workflow_session.add_all([success, partial_without_failure])
    workflow_session.commit()

    with _client(workflow_session) as client:
        successful_retry = client.post(f"/api/v1/creative-projects/{project.id}/narrative/runs/{success.id}/retry")
        missing_failure_retry = client.post(f"/api/v1/creative-projects/{project.id}/narrative/runs/{partial_without_failure.id}/retry")

    assert successful_retry.status_code == 409
    assert missing_failure_retry.status_code == 409


def test_narrative_batch_run_api_persists_pending_intent_before_background_execution(workflow_session: Session):
    with _client(workflow_session) as client:
        project = _post(client, "", {"title": "Queued narrative", "idea": "A quiet secret."})["data"]
        body = ProjectContent(
            project_id=project["id"], content_type="novel_body", chapter_number=1,
            title="Chapter one", text_content="窗外的雨停了。",
        )
        workflow_session.add(body)
        workflow_session.commit()
        response = client.post(
            f"/api/v1/creative-projects/{project['id']}/narrative/runs",
            json={"chapter_numbers": [1]},
        )

    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["mode"] == "batch"
    assert payload["target_chapters"] == [1]
    assert payload["status"] in {"pending", "running", "success", "partial"}


def test_guarded_narrative_autopilot_only_schedules_approved_prose_aftermath(workflow_session: Session):
    with _client(workflow_session) as client:
        project = _post(client, "", {"title": "Guarded auto", "idea": "A clue waits."})["data"]
        body = ProjectContent(
            project_id=project["id"], content_type="novel_body", chapter_number=1,
            title="Approved only", text_content="她没有打开那封信。",
        )
        workflow_session.add(body)
        workflow_session.commit()
        response = client.put(
            f"/api/v1/creative-projects/{project['id']}/narrative/autopilot",
            json={"enabled": True, "chapter_numbers": [1], "max_chapters_per_run": 1, "max_consecutive_failures": 2},
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["policy"]["scope"] == "approved_prose_aftermath_only"
    assert data["run"]["mode"] == "guarded_autopilot"
    stored = workflow_session.get(CreativeProject, project["id"])
    assert "approved_prose_aftermath_only" in stored.settings_json
