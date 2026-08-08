from __future__ import annotations

import json

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine, select

from app.db.models.creative_project import (
    CreativeProject,
    ProjectContinuityCandidate,
    ProjectContent,
    ProjectForeshadowing,
    ProjectGenerationLog,
    ProjectNarrativeRun,
    ProjectNarrativeContextSnapshot,
    ProjectNarrativeSnapshot,
    ProjectStoryEvent,
    ProjectStyleMeasurement,
)
from app.services.creative_project.narrative_runtime import ChapterAftermathPipeline, NarrativeReviewService


def _create_runtime_tables(engine) -> None:
    for table in (
        CreativeProject.__table__,
        ProjectContent.__table__,
        ProjectGenerationLog.__table__,
        ProjectContinuityCandidate.__table__,
        ProjectNarrativeRun.__table__,
        ProjectNarrativeContextSnapshot.__table__,
        ProjectNarrativeSnapshot.__table__,
        ProjectStoryEvent.__table__,
        ProjectForeshadowing.__table__,
        ProjectStyleMeasurement.__table__,
    ):
        table.create(engine)


def test_narrative_runtime_records_keep_project_and_source_version_provenance():
    engine = create_engine("sqlite://")
    _create_runtime_tables(engine)
    with Session(engine) as session:
        project = CreativeProject(title="Narrative provenance")
        session.add(project)
        session.flush()
        body = ProjectContent(
            project_id=project.id,
            content_type="novel_body",
            chapter_number=3,
            version=2,
            text_content="Approved chapter three.",
        )
        session.add(body)
        session.flush()
        run = ProjectNarrativeRun(project_id=project.id, mode="manual", status="running")
        session.add(run)
        session.flush()
        snapshot = ProjectNarrativeSnapshot(
            project_id=project.id,
            source_content_id=body.id,
            source_version=body.version,
            chapter_number=3,
            run_id=run.id,
            source_fingerprint="body-v2",
            summary="A decision changes the investigation.",
        )
        session.add(snapshot)
        session.flush()
        session.add_all(
            [
                ProjectStoryEvent(
                    project_id=project.id,
                    snapshot_id=snapshot.id,
                    source_content_id=body.id,
                    source_version=body.version,
                    chapter_number=3,
                    run_id=run.id,
                    source_fingerprint="body-v2",
                    title="The witness changes their story",
                ),
                ProjectForeshadowing(
                    project_id=project.id,
                    snapshot_id=snapshot.id,
                    source_content_id=body.id,
                    source_version=body.version,
                    chapter_number=3,
                    run_id=run.id,
                    source_fingerprint="body-v2",
                    planted_chapter=3,
                    statement="The torn receipt will matter later.",
                ),
                ProjectStyleMeasurement(
                    project_id=project.id,
                    source_content_id=body.id,
                    source_version=body.version,
                    chapter_number=3,
                    run_id=run.id,
                    source_fingerprint="body-v2",
                    measurement_json='{"dialogue_ratio": 0.36}',
                ),
            ]
        )
        session.commit()

        assert snapshot.project_id == project.id
        assert snapshot.source_content_id == body.id
        assert snapshot.source_version == 2
        assert snapshot.run_id == run.id


def test_narrative_snapshot_source_fingerprint_is_idempotent_per_pipeline_version():
    engine = create_engine("sqlite://")
    _create_runtime_tables(engine)
    with Session(engine) as session:
        project = CreativeProject(title="Snapshot idempotency")
        session.add(project)
        session.flush()
        body = ProjectContent(project_id=project.id, content_type="novel_body", chapter_number=1)
        session.add(body)
        session.flush()
        session.add(
            ProjectNarrativeSnapshot(
                project_id=project.id,
                source_content_id=body.id,
                chapter_number=1,
                source_fingerprint="same-approved-body",
                pipeline_version="v1",
            )
        )
        session.commit()

        session.add(
            ProjectNarrativeSnapshot(
                project_id=project.id,
                source_content_id=body.id,
                chapter_number=1,
                source_fingerprint="same-approved-body",
                pipeline_version="v1",
            )
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("duplicate snapshot fingerprint must be rejected")


def test_chapter_aftermath_is_idempotent_and_keeps_foreshadowing_pending():
    engine = create_engine("sqlite://")
    _create_runtime_tables(engine)
    with Session(engine) as session:
        project = CreativeProject(title="Aftermath")
        session.add(project)
        session.flush()
        body = ProjectContent(
            project_id=project.id,
            content_type="novel_body",
            chapter_number=1,
            version=4,
            data_json='{"summary":"The key changes hands.","foreshadowing":["The torn receipt"],"continuity_notes":["The receipt number is still unknown."]}',
            text_content="The key changes hands.\n\nShe hides the torn receipt.",
        )
        session.add(body)
        session.commit()

        first = ChapterAftermathPipeline(session).run(project.id, body.id)
        second = ChapterAftermathPipeline(session).run(project.id, body.id)

        assert first["reused"] is False
        assert second["reused"] is True
        assert second["snapshot_id"] == first["snapshot_id"]
        foreshadowing = session.exec(select(ProjectForeshadowing)).all()
        assert len(foreshadowing) == 1
        assert foreshadowing[0].status == "pending_review"
        continuity = session.exec(select(ProjectContinuityCandidate)).all()
        assert len(continuity) == 1
        assert continuity[0].status == "pending"
        assert continuity[0].source_kind == "narrative_aftermath"


def test_narrative_rebuild_uses_latest_approved_body_in_chapter_order():
    engine = create_engine("sqlite://")
    _create_runtime_tables(engine)
    with Session(engine) as session:
        project = CreativeProject(title="Ordered rebuild")
        session.add(project)
        session.flush()
        session.add_all(
            [
                ProjectContent(project_id=project.id, content_type="novel_body", chapter_number=2, version=1, text_content="Second chapter."),
                ProjectContent(project_id=project.id, content_type="novel_body", chapter_number=1, version=1, text_content="Old first chapter."),
                ProjectContent(project_id=project.id, content_type="novel_body", chapter_number=1, version=2, text_content="New first chapter."),
            ]
        )
        session.commit()

        result = ChapterAftermathPipeline(session).rebuild(project.id)

        assert result["chapter_numbers"] == [1, 2]
        assert result["summary"] == {"total": 2, "reused": 0, "created": 2}


def test_partial_aftermath_can_retry_without_mutating_approved_prose():
    engine = create_engine("sqlite://")
    _create_runtime_tables(engine)
    with Session(engine) as session:
        project = CreativeProject(title="Partial retry")
        session.add(project)
        session.flush()
        body = ProjectContent(
            project_id=project.id,
            content_type="novel_body",
            chapter_number=1,
            text_content="Approved text must stay untouched.",
        )
        session.add(body)
        session.commit()

        pipeline = ChapterAftermathPipeline(session)
        original_measure = pipeline._measure_style
        pipeline._measure_style = lambda _: (_ for _ in ()).throw(RuntimeError("style adapter unavailable"))
        partial = pipeline.run(project.id, body.id)
        pipeline._measure_style = original_measure
        retried = pipeline.run(project.id, body.id)

        snapshot = session.get(ProjectNarrativeSnapshot, partial["snapshot_id"])
        assert partial["status"] == "partial"
        assert retried["reused"] is False
        assert retried["snapshot_id"] == partial["snapshot_id"]
        assert snapshot.status == "success"
        assert session.get(ProjectContent, body.id).text_content == "Approved text must stay untouched."


def test_batch_provider_unavailable_is_persisted_as_retryable_partial_failure():
    engine = create_engine("sqlite://")
    _create_runtime_tables(engine)
    with Session(engine) as session:
        project = CreativeProject(title="Provider unavailable")
        body = ProjectContent(
            project_id=project.id,
            content_type="novel_body",
            chapter_number=1,
            text_content="An approved chapter remains unchanged.",
        )
        session.add_all([project, body])
        session.commit()

        pipeline = ChapterAftermathPipeline(session)
        batch = pipeline.create_batch_run(project.id, chapter_numbers=[1])

        def unavailable(*_args, **_kwargs):
            raise RuntimeError("provider unavailable")

        pipeline.run = unavailable  # type: ignore[method-assign]
        result = pipeline.resume_batch_run(project.id, batch.id)
        stored = session.get(ProjectNarrativeRun, batch.id)

        assert result["status"] == "partial"
        assert stored is not None
        trace = json.loads(stored.trace_json)
        assert trace[0]["error_type"] == "RuntimeError"
        assert trace[0]["retryable"] is True
        assert session.get(ProjectContent, body.id).text_content == "An approved chapter remains unchanged."


def test_latest_approved_body_supersedes_prior_chapter_narrative_state():
    engine = create_engine("sqlite://")
    _create_runtime_tables(engine)
    with Session(engine) as session:
        project = CreativeProject(title="Superseded state")
        session.add(project)
        session.flush()
        first = ProjectContent(
            project_id=project.id,
            content_type="novel_body",
            chapter_number=1,
            version=1,
            text_content="The first approved ending.",
        )
        session.add(first)
        session.commit()
        old = ChapterAftermathPipeline(session).run(project.id, first.id)

        replacement = ProjectContent(
            project_id=project.id,
            content_type="novel_body",
            chapter_number=1,
            version=2,
            text_content="The corrected approved ending.",
        )
        session.add(replacement)
        session.commit()
        current = ChapterAftermathPipeline(session).run(project.id, replacement.id)

        assert session.get(ProjectNarrativeSnapshot, old["snapshot_id"]).status == "superseded"
        assert session.get(ProjectNarrativeSnapshot, current["snapshot_id"]).status == "success"


def test_aftermath_service_keeps_versions_projects_and_terminal_ledger_decisions_isolated():
    """The pipeline must not duplicate, leak, or revive derived narrative state."""
    engine = create_engine("sqlite://")
    _create_runtime_tables(engine)
    with Session(engine) as session:
        project = CreativeProject(title="Primary narrative")
        other_project = CreativeProject(title="Other narrative")
        session.add_all([project, other_project])
        session.flush()
        approved = ProjectContent(
            project_id=project.id,
            content_type="novel_body",
            chapter_number=1,
            version=1,
            text_content="A key is found behind the portrait.",
            data_json='{"foreshadowing":["The missing key opens the archive."]}',
        )
        foreign = ProjectContent(
            project_id=other_project.id,
            content_type="novel_body",
            chapter_number=1,
            version=1,
            text_content="A different clue belongs to another project.",
            data_json='{"foreshadowing":["Foreign clue"]}',
        )
        session.add_all([approved, foreign])
        session.commit()

        pipeline = ChapterAftermathPipeline(session)
        first = pipeline.run(project.id, approved.id)
        duplicate = pipeline.run(project.id, approved.id)
        pipeline.run(other_project.id, foreign.id)

        assert duplicate["reused"] is True
        assert len(session.exec(
            select(ProjectNarrativeSnapshot).where(
                ProjectNarrativeSnapshot.project_id == project.id,
                ProjectNarrativeSnapshot.source_content_id == approved.id,
            )
        ).all()) == 1

        replacement = ProjectContent(
            project_id=project.id,
            content_type="novel_body",
            chapter_number=1,
            version=2,
            text_content="The key is recovered and its owner is identified.",
            data_json='{"foreshadowing":["The recovered key opens the archive."]}',
        )
        session.add(replacement)
        session.commit()
        current = pipeline.run(project.id, replacement.id)

        old_snapshot = session.get(ProjectNarrativeSnapshot, first["snapshot_id"])
        current_snapshot = session.get(ProjectNarrativeSnapshot, current["snapshot_id"])
        assert old_snapshot.status == "superseded"
        assert current_snapshot.status == "success"
        assert len(session.exec(
            select(ProjectNarrativeSnapshot).where(
                ProjectNarrativeSnapshot.project_id == other_project.id,
                ProjectNarrativeSnapshot.status == "success",
            )
        ).all()) == 1

        review = NarrativeReviewService(session)
        item = session.exec(
            select(ProjectForeshadowing).where(
                ProjectForeshadowing.project_id == project.id,
                ProjectForeshadowing.source_content_id == replacement.id,
            )
        ).one()
        assert review.decide_foreshadowing(project.id, item.id, action="accept")["status"] == "active"
        assert review.decide_foreshadowing(project.id, item.id, action="resolve")["status"] == "resolved"
        with pytest.raises(ValueError):
            review.decide_foreshadowing(project.id, item.id, action="advance")
        with pytest.raises(ValueError):
            review.decide_foreshadowing(other_project.id, item.id, action="ignore")


def test_foreshadowing_review_transitions_and_overdue_are_project_scoped():
    engine = create_engine("sqlite://")
    _create_runtime_tables(engine)
    with Session(engine) as session:
        project = CreativeProject(title="Ledger")
        other = CreativeProject(title="Other ledger")
        session.add_all([project, other])
        session.flush()
        body = ProjectContent(project_id=project.id, content_type="novel_body", chapter_number=2, text_content="A clue is planted.")
        other_body = ProjectContent(project_id=other.id, content_type="novel_body", chapter_number=2, text_content="Other clue.")
        session.add_all([body, other_body])
        session.flush()
        item = ProjectForeshadowing(
            project_id=project.id, source_content_id=body.id, chapter_number=2, planted_chapter=2,
            statement="The blue receipt", expected_window_json='{"start": 3, "end": 4}', status="pending_review",
        )
        session.add_all([
            item,
            ProjectForeshadowing(
                project_id=other.id, source_content_id=other_body.id, chapter_number=2, planted_chapter=2,
                statement="Other project's clue", status="active",
            ),
        ])
        session.commit()
        review = NarrativeReviewService(session)

        pending = review.list_foreshadowing(project.id, chapter_number=2)["data"]
        assert [row["statement"] for row in pending] == ["The blue receipt"]
        accepted = review.decide_foreshadowing(project.id, item.id, action="accept", current_chapter=2)
        assert accepted["status"] == "active"
        overdue = review.list_foreshadowing(project.id, chapter_number=5)["data"]
        assert overdue[0]["status"] == "overdue"
        assert overdue[0]["timing"] == "overdue"
        assert review.decide_foreshadowing(project.id, item.id, action="resolve", note="Paid off", current_chapter=5)["status"] == "resolved"


def test_narrative_graph_excludes_pending_and_foreign_records_by_default():
    engine = create_engine("sqlite://")
    _create_runtime_tables(engine)
    with Session(engine) as session:
        project = CreativeProject(title="Graph")
        other = CreativeProject(title="Foreign graph")
        session.add_all([project, other])
        session.flush()
        fact = ProjectContent(project_id=project.id, content_type="project_bible", title="Lin", text_content="Lin edits evidence.", is_locked=True, data_json='{"entity_type":"character","summary":"Lin edits evidence."}')
        body = ProjectContent(project_id=project.id, content_type="novel_body", chapter_number=1, text_content="Approved event.")
        foreign_body = ProjectContent(project_id=other.id, content_type="novel_body", chapter_number=1, text_content="Foreign event.")
        session.add_all([fact, body, foreign_body])
        session.flush()
        snapshot = ProjectNarrativeSnapshot(project_id=project.id, source_content_id=body.id, chapter_number=1, source_fingerprint="graph", summary="Lin takes the receipt.")
        foreign_snapshot = ProjectNarrativeSnapshot(project_id=other.id, source_content_id=foreign_body.id, chapter_number=1, source_fingerprint="foreign", summary="Foreign state")
        session.add_all([snapshot, foreign_snapshot])
        session.flush()
        session.add_all([
            ProjectStoryEvent(project_id=project.id, snapshot_id=snapshot.id, source_content_id=body.id, chapter_number=1, source_fingerprint="graph", status="confirmed", title="Receipt acquired", description="Lin takes it."),
            ProjectStoryEvent(project_id=project.id, snapshot_id=snapshot.id, source_content_id=body.id, chapter_number=1, source_fingerprint="pending", status="pending_review", title="Pending event"),
            ProjectForeshadowing(project_id=project.id, snapshot_id=snapshot.id, source_content_id=body.id, chapter_number=1, planted_chapter=1, source_fingerprint="active", status="active", statement="The receipt number"),
            ProjectForeshadowing(project_id=project.id, snapshot_id=snapshot.id, source_content_id=body.id, chapter_number=1, planted_chapter=1, source_fingerprint="pending", status="pending_review", statement="Pending clue"),
        ])
        session.commit()

        graph = NarrativeReviewService(session).narrative_graph(project.id)
        labels = {node["label"] for node in graph["nodes"]}
        assert {"Lin", "第 1 章", "Receipt acquired", "The receipt number"} <= labels
        assert "Pending event" not in labels
        assert "Pending clue" not in labels
        assert "Foreign state" not in labels
        pending_graph = NarrativeReviewService(session).narrative_graph(project.id, include_pending=True)
        assert {"Pending event", "Pending clue"} <= {node["label"] for node in pending_graph["nodes"]}
