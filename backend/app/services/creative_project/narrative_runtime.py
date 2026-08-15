"""Project-owned narrative aftermath runtime.

The first release is deliberately deterministic.  It normalizes structured
fields already present on an approved chapter and uses bounded text metrics as
fallbacks.  An LLM extractor can be added behind the same contract later; it
must never turn a pending proposal into canon.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.db.models.creative_project import (
    CreativeProject,
    ForeshadowingStatus,
    NarrativeRunMode,
    NarrativeRunStatus,
    NarrativeSnapshotStatus,
    ProjectForeshadowing,
    ProjectContinuityCandidate,
    ProjectContent,
    ProjectNarrativeRun,
    ProjectNarrativeSnapshot,
    ProjectStoryEvent,
    ProjectStyleMeasurement,
)
from app.services.creative_project.schemas import (
    NarrativeEventSchema,
    NarrativeForeshadowingSchema,
    NarrativeSnapshotSchema,
)
from app.services.creative_project.service import loads_json, repair_utf8_mojibake
from app.services.creative_project.state_ledger import StateLedger


def _json(value: Any) -> str:
    """Serialize empty lists as lists; the legacy project helper maps them to {}."""
    return json.dumps(repair_utf8_mojibake(value if value is not None else {}), ensure_ascii=False)


def _retryable_error_details(error: Exception) -> dict[str, Any]:
    """Persist actionable failure context without depending on a provider SDK."""
    message = str(error)
    normalized = f"{type(error).__name__} {message}".lower()
    retryable_terms = ("timeout", "timed out", "connection", "unavailable", "provider", "rate limit")
    return {
        "error_type": type(error).__name__,
        "error": message,
        "retryable": any(term in normalized for term in retryable_terms),
    }


class ChapterAftermathPipeline:
    """Create replayable narrative state from one approved prose version."""

    pipeline_version = "v1"

    def __init__(self, session: Session):
        self.session = session

    def run(self, project_id: str, content_id: str) -> dict[str, Any]:
        project = self.session.get(CreativeProject, project_id)
        if project is None:
            raise ValueError("创作项目不存在")
        content = self._get_content(project_id, content_id)
        if content.content_type != "novel_body":
            raise ValueError("章节后处理只能作用于正式 novel_body")
        if content.chapter_number is None or content.chapter_number <= 0:
            raise ValueError("正文缺少有效章节号，无法建立叙事状态")

        text = repair_utf8_mojibake(content.text_content or "")
        data = loads_json(content.data_json)
        if not isinstance(data, dict):
            data = {}
        if not text:
            text = str(data.get("content") or "").strip()
        fingerprint = hashlib.sha256(
            f"{content.id}:{content.version}:{text}".encode("utf-8")
        ).hexdigest()
        self._supersede_replaced_chapter_state(project_id, content)
        existing = self.session.exec(
            select(ProjectNarrativeSnapshot)
            .where(
                ProjectNarrativeSnapshot.source_content_id == content.id,
                ProjectNarrativeSnapshot.source_fingerprint == fingerprint,
                ProjectNarrativeSnapshot.pipeline_version == self.pipeline_version,
            )
        ).first()
        if existing is not None and existing.status == NarrativeSnapshotStatus.SUCCESS.value:
            return self._result(existing, reused=True)

        run = ProjectNarrativeRun(
            project_id=project_id,
            mode=NarrativeRunMode.MANUAL.value,
            status=NarrativeRunStatus.RUNNING.value,
            pipeline_version=self.pipeline_version,
            target_chapters_json=_json([content.chapter_number]),
        )
        self.session.add(run)
        self.session.flush()
        trace: list[dict[str, Any]] = []
        diagnostics: dict[str, Any] = {}
        stage_failed = False

        def stage(name: str, status: str, **details: Any) -> None:
            trace.append({
                "stage": name,
                "status": status,
                "at": datetime.now().isoformat(),
                **details,
            })

        try:
            snapshot_data = self._extract_snapshot(data, text)
            stage("snapshot", "success")
        except Exception as exc:  # keep the approved source usable
            stage_failed = True
            diagnostics["snapshot"] = str(exc)
            snapshot_data = NarrativeSnapshotSchema(summary=self._bounded_summary(text))
            stage("snapshot", "failed", error=str(exc))

        try:
            events = self._extract_events(snapshot_data, content.chapter_number)
            stage("events", "success", count=len(events))
        except Exception as exc:
            stage_failed = True
            diagnostics["events"] = str(exc)
            events = []
            stage("events", "failed", error=str(exc))

        try:
            foreshadowing = self._extract_foreshadowing(data, content.chapter_number)
            stage("foreshadowing", "success", count=len(foreshadowing))
        except Exception as exc:
            stage_failed = True
            diagnostics["foreshadowing"] = str(exc)
            foreshadowing = []
            stage("foreshadowing", "failed", error=str(exc))

        try:
            state_changes = data.get("state_changes") if isinstance(data, dict) else []
            if not isinstance(state_changes, list):
                state_changes = []
            if state_changes:
                StateLedger.replace_chapter_entries(
                    self.session,
                    project_id,
                    content.chapter_number,
                    state_changes,
                    source_content_id=content.id,
                    source_version=content.version,
                )
                self.session.flush()
            stage("state", "success", count=len(state_changes))
        except Exception as exc:
            stage_failed = True
            diagnostics["state"] = str(exc)
            stage("state", "failed", error=str(exc))

        try:
            measurement = self._measure_style(text)
            stage("style", "success")
        except Exception as exc:
            stage_failed = True
            diagnostics["style"] = str(exc)
            measurement = {"character_count": len(text)}
            stage("style", "failed", error=str(exc))

        snapshot_status = NarrativeSnapshotStatus.PARTIAL.value if stage_failed else NarrativeSnapshotStatus.SUCCESS.value
        snapshot_fields = {
            "project_id": project_id,
            "source_content_id": content.id,
            "source_version": content.version,
            "chapter_number": content.chapter_number,
            "run_id": run.id,
            "pipeline_version": self.pipeline_version,
            "source_fingerprint": fingerprint,
            "status": snapshot_status,
            "summary": snapshot_data.summary,
            "character_state_json": _json(snapshot_data.character_state),
            "timeline_delta_json": _json(snapshot_data.timeline_delta),
            "location_delta_json": _json(snapshot_data.location_delta),
            "open_questions_json": _json(snapshot_data.open_questions),
            "diagnostics_json": _json(diagnostics),
            "context_fingerprint": hashlib.sha256(
                _json(snapshot_data.model_dump()).encode("utf-8")
            ).hexdigest(),
            "updated_at": datetime.now(),
        }
        if existing is not None:
            self._clear_snapshot_derived_state(existing, content.id, fingerprint)
            for field, value in snapshot_fields.items():
                setattr(existing, field, value)
            snapshot = existing
        else:
            snapshot = ProjectNarrativeSnapshot(**snapshot_fields)
        self.session.add(snapshot)
        self.session.flush()

        for event in events:
            self.session.add(
                ProjectStoryEvent(
                    project_id=project_id,
                    snapshot_id=snapshot.id,
                    source_content_id=content.id,
                    source_version=content.version,
                    chapter_number=content.chapter_number,
                    run_id=run.id,
                    source_fingerprint=fingerprint,
                    status="pending_review",
                    event_type=event.event_type,
                    title=event.title,
                    description=event.description,
                    participants_json=_json(event.participants),
                    location=event.location,
                    timeline_order=event.timeline_order,
                    evidence_anchor_json=_json(event.evidence_anchor.model_dump()),
                )
            )
        for item in foreshadowing:
            self.session.add(
                ProjectForeshadowing(
                    project_id=project_id,
                    snapshot_id=snapshot.id,
                    source_content_id=content.id,
                    source_version=content.version,
                    chapter_number=content.chapter_number,
                    run_id=run.id,
                    source_fingerprint=fingerprint,
                    kind=item.kind,
                    statement=item.statement,
                    planted_chapter=item.planted_chapter,
                    expected_window_json=_json(item.expected_window),
                    status=ForeshadowingStatus.PENDING_REVIEW.value,
                    evidence_anchor_json=_json(item.evidence_anchor.model_dump()),
                )
            )
        self.session.add(
            ProjectStyleMeasurement(
                project_id=project_id,
                source_content_id=content.id,
                source_version=content.version,
                chapter_number=content.chapter_number,
                run_id=run.id,
                source_fingerprint=fingerprint,
                status=NarrativeSnapshotStatus.PARTIAL.value if stage_failed else NarrativeSnapshotStatus.SUCCESS.value,
                measurement_json=_json(measurement),
                style_fingerprint=hashlib.sha256(_json(measurement).encode("utf-8")).hexdigest(),
            )
        )

        run.status = NarrativeRunStatus.PARTIAL.value if stage_failed else NarrativeRunStatus.SUCCESS.value
        run.trace_json = _json(trace)
        run.error_message = _json(diagnostics)
        run.updated_at = datetime.now()
        run.finished_at = datetime.now()
        self.session.add(run)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.session.exec(
                select(ProjectNarrativeSnapshot)
                .where(
                    ProjectNarrativeSnapshot.source_content_id == content.id,
                    ProjectNarrativeSnapshot.source_fingerprint == fingerprint,
                    ProjectNarrativeSnapshot.pipeline_version == self.pipeline_version,
                )
            ).first()
            if existing is not None:
                return self._result(existing, reused=True)
            raise
        self.session.refresh(snapshot)
        self.session.refresh(run)
        continuity_count = self._persist_continuity_candidates(project_id, content.id, data)
        if continuity_count:
            trace.append({
                "stage": "continuity_candidates",
                "status": "success",
                "at": datetime.now().isoformat(),
                "count": continuity_count,
            })
            run.trace_json = _json(trace)
            run.updated_at = datetime.now()
            self.session.add(run)
            self.session.commit()
        return self._result(snapshot, run=run, reused=False)

    def _clear_snapshot_derived_state(
        self,
        snapshot: ProjectNarrativeSnapshot,
        source_content_id: str,
        source_fingerprint: str,
    ) -> None:
        """Reset only state derived from a retryable partial snapshot."""
        for model in (ProjectStoryEvent, ProjectForeshadowing):
            for row in self.session.exec(select(model).where(model.snapshot_id == snapshot.id)).all():
                self.session.delete(row)
        for row in self.session.exec(
            select(ProjectStyleMeasurement).where(
                ProjectStyleMeasurement.source_content_id == source_content_id,
                ProjectStyleMeasurement.source_fingerprint == source_fingerprint,
            )
        ).all():
            self.session.delete(row)
        self.session.flush()

    def _supersede_replaced_chapter_state(self, project_id: str, content: Any) -> None:
        """Keep historical evidence, but remove replaced prose from active state."""
        from app.db.models.creative_project import ProjectContent

        latest = self.session.exec(
            select(ProjectContent)
            .where(
                ProjectContent.project_id == project_id,
                ProjectContent.content_type == "novel_body",
                ProjectContent.chapter_number == content.chapter_number,
            )
            .order_by(ProjectContent.version.desc(), ProjectContent.created_at.desc())
        ).first()
        if latest is None or latest.id != content.id:
            return
        stale_snapshots = self.session.exec(
            select(ProjectNarrativeSnapshot).where(
                ProjectNarrativeSnapshot.project_id == project_id,
                ProjectNarrativeSnapshot.chapter_number == content.chapter_number,
                ProjectNarrativeSnapshot.source_content_id != content.id,
                ProjectNarrativeSnapshot.status != NarrativeSnapshotStatus.SUPERSEDED.value,
            )
        ).all()
        stale_snapshot_ids = [snapshot.id for snapshot in stale_snapshots]
        for snapshot in stale_snapshots:
            snapshot.status = NarrativeSnapshotStatus.SUPERSEDED.value
            snapshot.updated_at = datetime.now()
            self.session.add(snapshot)
        if stale_snapshot_ids:
            for event in self.session.exec(
                select(ProjectStoryEvent).where(ProjectStoryEvent.snapshot_id.in_(stale_snapshot_ids))
            ).all():
                event.status = "superseded"
                event.updated_at = datetime.now()
                self.session.add(event)
            for item in self.session.exec(
                select(ProjectForeshadowing).where(ProjectForeshadowing.snapshot_id.in_(stale_snapshot_ids))
            ).all():
                item.status = ForeshadowingStatus.SUPERSEDED.value
                item.updated_at = datetime.now()
                self.session.add(item)
        for measurement in self.session.exec(
            select(ProjectStyleMeasurement).where(
                ProjectStyleMeasurement.project_id == project_id,
                ProjectStyleMeasurement.chapter_number == content.chapter_number,
                ProjectStyleMeasurement.source_content_id != content.id,
                ProjectStyleMeasurement.status != NarrativeSnapshotStatus.SUPERSEDED.value,
            )
        ).all():
            measurement.status = NarrativeSnapshotStatus.SUPERSEDED.value
            measurement.updated_at = datetime.now()
            self.session.add(measurement)
        if stale_snapshots:
            self.session.flush()

    def rebuild(self, project_id: str, *, chapter_numbers: list[int] | None = None) -> dict[str, Any]:
        """Create and synchronously execute a resumable batch replay."""
        run = self.create_batch_run(project_id, chapter_numbers=chapter_numbers)
        return self.resume_batch_run(project_id, run.id)

    def create_batch_run(
        self,
        project_id: str,
        *,
        chapter_numbers: list[int] | None = None,
        mode: str = NarrativeRunMode.BATCH.value,
        input_data: dict[str, Any] | None = None,
    ) -> ProjectNarrativeRun:
        """Persist a batch intent without mutating approved prose or derived state."""
        from app.db.models.creative_project import ProjectContent

        if self.session.get(CreativeProject, project_id) is None:
            raise ValueError("创作项目不存在")
        requested = {int(number) for number in chapter_numbers or [] if int(number) > 0}
        rows = self.session.exec(
            select(ProjectContent)
            .where(
                ProjectContent.project_id == project_id,
                ProjectContent.content_type == "novel_body",
            )
            .order_by(ProjectContent.chapter_number.asc(), ProjectContent.version.desc(), ProjectContent.created_at.desc())
        ).all()
        latest_by_chapter: dict[int, ProjectContent] = {}
        for row in rows:
            if row.chapter_number is None or row.chapter_number <= 0:
                continue
            if requested and row.chapter_number not in requested:
                continue
            latest_by_chapter.setdefault(row.chapter_number, row)
        targets = [chapter for chapter, _ in sorted(latest_by_chapter.items())]
        if mode not in {NarrativeRunMode.BATCH.value, NarrativeRunMode.GUARDED_AUTOPILOT.value}:
            raise ValueError("不支持的叙事批次模式")
        batch_run = ProjectNarrativeRun(
            project_id=project_id,
            mode=mode,
            status=NarrativeRunStatus.PENDING.value,
            pipeline_version=self.pipeline_version,
            target_chapters_json=_json(targets),
            input_json=_json({"requested_chapter_numbers": sorted(requested), **(input_data or {})}),
        )
        self.session.add(batch_run)
        self.session.commit()
        self.session.refresh(batch_run)
        return batch_run

    def resume_batch_run(self, project_id: str, run_id: str) -> dict[str, Any]:
        """Continue a pending batch from its durable cursor in chapter order."""
        batch_run = self.session.get(ProjectNarrativeRun, run_id)
        if batch_run is None or batch_run.project_id != project_id:
            raise ValueError("叙事批次运行不存在")
        if batch_run.mode not in {NarrativeRunMode.BATCH.value, NarrativeRunMode.GUARDED_AUTOPILOT.value}:
            raise ValueError("只有批次叙事运行可以执行")
        if batch_run.status not in {NarrativeRunStatus.PENDING.value, NarrativeRunStatus.RUNNING.value}:
            raise ValueError(f"当前批次状态 {batch_run.status} 不能执行")
        targets = [int(item) for item in loads_json(batch_run.target_chapters_json, []) if int(item) > 0]
        batch_run.status = NarrativeRunStatus.RUNNING.value
        batch_run.started_at = batch_run.started_at or datetime.now()
        batch_run.updated_at = datetime.now()
        self.session.add(batch_run)
        self.session.commit()

        rows = self.session.exec(
            select(ProjectContent)
            .where(
                ProjectContent.project_id == project_id,
                ProjectContent.content_type == "novel_body",
                ProjectContent.chapter_number.in_(targets),
            )
            .order_by(ProjectContent.chapter_number.asc(), ProjectContent.version.desc(), ProjectContent.created_at.desc())
        ).all()
        latest_by_chapter: dict[int, ProjectContent] = {}
        for row in rows:
            if row.chapter_number and row.chapter_number not in latest_by_chapter:
                latest_by_chapter[row.chapter_number] = row
        ordered = [(chapter, latest_by_chapter[chapter]) for chapter in targets if chapter in latest_by_chapter]
        trace = loads_json(batch_run.trace_json, [])
        if not isinstance(trace, list):
            trace = []
        input_data = loads_json(batch_run.input_json, {})
        policy = input_data.get("autopilot_policy") if isinstance(input_data, dict) else {}
        failure_limit = int(policy.get("max_consecutive_failures") or 2) if isinstance(policy, dict) else 2

        results: list[dict[str, Any]] = []
        for index, (chapter_number, content) in enumerate(ordered, start=1):
            self.session.refresh(batch_run)
            if batch_run.status == NarrativeRunStatus.PAUSED.value:
                return self._batch_result(batch_run, results, trace)
            if batch_run.status == NarrativeRunStatus.CANCELLED.value:
                return self._batch_result(batch_run, results, trace)
            if index <= batch_run.current_cursor:
                continue
            try:
                result = self.run(project_id, content.id)
                results.append(result)
                trace.append({
                    "chapter_number": chapter_number,
                    "status": "success",
                    "child_run_id": result.get("run_id"),
                    "reused": result.get("reused", False),
                    "at": datetime.now().isoformat(),
                })
            except Exception as exc:
                details = _retryable_error_details(exc)
                trace.append({
                    "chapter_number": chapter_number,
                    "status": "failed",
                    **details,
                    "at": datetime.now().isoformat(),
                })
                if batch_run.mode == NarrativeRunMode.GUARDED_AUTOPILOT.value:
                    consecutive_failures = 0
                    for item in reversed(trace):
                        if item.get("status") != "failed":
                            break
                        consecutive_failures += 1
                    if consecutive_failures >= failure_limit:
                        batch_run.status = NarrativeRunStatus.FAILED.value
                        batch_run.error_message = _json({"circuit_breaker": "consecutive_chapter_failures", "failures": consecutive_failures})
                        batch_run.finished_at = datetime.now()
                        batch_run.trace_json = _json(trace)
                        batch_run.updated_at = datetime.now()
                        self.session.add(batch_run)
                        self.session.commit()
                        return self._batch_result(batch_run, results, trace)
            batch_run.current_cursor = index
            batch_run.trace_json = _json(trace)
            batch_run.updated_at = datetime.now()
            self.session.add(batch_run)
            self.session.commit()

        failures = [item for item in trace if item["status"] == "failed"]
        batch_run.status = (
            NarrativeRunStatus.PARTIAL.value if failures else NarrativeRunStatus.SUCCESS.value
        )
        batch_run.error_message = _json({"failed_chapters": failures}) if failures else ""
        batch_run.finished_at = datetime.now()
        batch_run.updated_at = datetime.now()
        self.session.add(batch_run)
        self.session.commit()
        self.session.refresh(batch_run)
        return self._batch_result(batch_run, results, trace)

    @staticmethod
    def _batch_result(batch_run: ProjectNarrativeRun, results: list[dict[str, Any]], trace: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "project_id": batch_run.project_id,
            "run_id": batch_run.id,
            "status": batch_run.status,
            "chapter_numbers": [result["chapter_number"] for result in results],
            "results": results,
            "trace": trace,
            "summary": {
                "total": len(results),
                "reused": sum(1 for result in results if result["reused"]),
                "created": sum(1 for result in results if not result["reused"]),
            },
        }

    def _get_content(self, project_id: str, content_id: str):
        from app.db.models.creative_project import ProjectContent

        content = self.session.get(ProjectContent, content_id)
        if content is None or content.project_id != project_id:
            raise ValueError("项目内容不存在")
        return content

    def _extract_snapshot(self, data: dict[str, Any], text: str) -> NarrativeSnapshotSchema:
        return NarrativeSnapshotSchema(
            summary=str(data.get("summary") or self._bounded_summary(text)),
            character_state=data.get("character_state") or data.get("character_changes") or [],
            timeline_delta=data.get("timeline_delta") or data.get("timeline_changes") or [],
            location_delta=data.get("location_delta") or data.get("location_changes") or [],
            open_questions=data.get("open_questions") or [],
            events=data.get("events") or data.get("key_events") or [],
            diagnostics={"extractor": "structured-content-plus-deterministic-fallback"},
        )

    def _extract_events(self, snapshot: NarrativeSnapshotSchema, chapter: int) -> list[NarrativeEventSchema]:
        raw_events = snapshot.model_extra.get("events") if snapshot.model_extra else None
        if not raw_events:
            raw_events = snapshot.timeline_delta
        events: list[NarrativeEventSchema] = []
        for index, raw in enumerate(raw_events or [], start=1):
            if isinstance(raw, str):
                events.append(NarrativeEventSchema(
                    event_type="chapter_progress",
                    title=f"第{chapter}章事件 {index}",
                    description=raw,
                    timeline_order=index,
                ))
            elif isinstance(raw, dict):
                event_data = dict(raw)
                event_data["timeline_order"] = event_data.get("timeline_order") or index
                events.append(NarrativeEventSchema(**event_data))
        if not events and snapshot.summary:
            events.append(NarrativeEventSchema(
                event_type="chapter_progress",
                title=f"第{chapter}章叙事推进",
                description=snapshot.summary,
                timeline_order=1,
            ))
        return events

    def _extract_foreshadowing(self, data: dict[str, Any], chapter: int) -> list[NarrativeForeshadowingSchema]:
        raw_items = data.get("foreshadowing") or data.get("foreshadowing_candidates") or []
        if isinstance(raw_items, str):
            raw_items = [raw_items]
        result: list[NarrativeForeshadowingSchema] = []
        for raw in raw_items:
            if isinstance(raw, str):
                result.append(NarrativeForeshadowingSchema(statement=raw, planted_chapter=chapter))
            elif isinstance(raw, dict):
                foreshadow_data = dict(raw)
                foreshadow_data["planted_chapter"] = foreshadow_data.get("planted_chapter") or chapter
                result.append(NarrativeForeshadowingSchema(**foreshadow_data))
        return result

    def _persist_continuity_candidates(
        self,
        project_id: str,
        content_id: str,
        data: dict[str, Any],
    ) -> int:
        notes = data.get("continuity_notes") or []
        if isinstance(notes, str):
            notes = [notes]
        candidates = [
            {
                "entity_type": "other",
                "claim": str(note).strip(),
                "evidence_excerpt": str(note).strip(),
                "evidence_anchor": {"chapter_number": data.get("chapter_number")},
                "severity": "info",
                "suggested_action": "create_fact",
                "target_fact_type": "world_asset",
            }
            for note in notes
            if str(note).strip()
        ]
        if not candidates:
            return 0
        from app.services.creative_project.service import CreativeProjectService

        persisted = 0
        try:
            for payload in candidates:
                fingerprint = CreativeProjectService.compute_continuity_fingerprint(
                    project_id,
                    "narrative_aftermath",
                    content_id,
                    payload,
                )
                existing = self.session.exec(
                    select(ProjectContinuityCandidate).where(
                        ProjectContinuityCandidate.project_id == project_id,
                        ProjectContinuityCandidate.source_kind == "narrative_aftermath",
                        ProjectContinuityCandidate.source_fingerprint == fingerprint,
                    )
                ).first()
                if existing is not None:
                    persisted += 1
                    continue
                self.session.add(
                    ProjectContinuityCandidate(
                        project_id=project_id,
                        source_content_id=content_id,
                        source_kind="narrative_aftermath",
                        source_fingerprint=fingerprint,
                        entity_type=payload["entity_type"],
                        claim=payload["claim"],
                        evidence_excerpt=payload["evidence_excerpt"],
                        evidence_anchor_json=_json(payload["evidence_anchor"]),
                        severity=payload["severity"],
                        suggested_action=payload["suggested_action"],
                        target_fact_type=payload["target_fact_type"],
                        status="pending",
                    )
                )
                persisted += 1
            self.session.flush()
        except Exception:
            # Continuity candidates are enrichment proposals.  Their failure
            # must not retroactively invalidate an already persisted snapshot.
            if self.session.in_transaction():
                self.session.rollback()
            return 0
        return persisted

    @staticmethod
    def _bounded_summary(text: str, limit: int = 900) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        return compact[:limit]

    @staticmethod
    def _measure_style(text: str) -> dict[str, Any]:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        sentences = [part for part in re.split(r"(?<=[。！？!?])", text) if part.strip()]
        dialogue = len(re.findall(r"[\"“‘「『].*?[\"”’」』]", text, flags=re.S))
        cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
        return {
            "character_count": len(text),
            "cjk_character_count": cjk,
            "paragraph_count": len(paragraphs),
            "sentence_count": len(sentences),
            "average_sentence_length": round(len(text) / max(len(sentences), 1), 2),
            "dialogue_ratio": round(dialogue / max(len(text), 1), 4),
            "tension_score": min(
                100,
                int(
                    25 * len(re.findall(r"[！？!?]", text))
                    + 5 * len(re.findall(r"冲突|危险|秘密|追|逃|杀|死|失踪", text))
                ),
            ),
            "extractor": "deterministic-v1",
        }

    @staticmethod
    def _result(snapshot: ProjectNarrativeSnapshot, *, run: ProjectNarrativeRun | None = None, reused: bool) -> dict[str, Any]:
        return {
            "snapshot_id": snapshot.id,
            "run_id": run.id if run else snapshot.run_id,
            "project_id": snapshot.project_id,
            "source_content_id": snapshot.source_content_id,
            "source_version": snapshot.source_version,
            "chapter_number": snapshot.chapter_number,
            "status": snapshot.status,
            "reused": reused,
        }


class NarrativeReviewService:
    """Project-scoped review/query surface for narrative ledger and graph data."""

    _FORESHADOWING_STATUSES = {item.value for item in ForeshadowingStatus}
    _EVENT_CONFIRMED_STATUSES = {"confirmed"}

    def __init__(self, session: Session):
        self.session = session

    def list_foreshadowing(
        self,
        project_id: str,
        *,
        statuses: list[str] | None = None,
        chapter_number: int | None = None,
    ) -> dict[str, Any]:
        project = self._project(project_id)
        current_chapter = chapter_number or self._current_chapter(project_id, project)
        self._refresh_overdue(project_id, current_chapter)
        requested = {value for value in (statuses or []) if value}
        unknown = requested - self._FORESHADOWING_STATUSES
        if unknown:
            raise ValueError(f"不支持的伏笔状态：{', '.join(sorted(unknown))}")
        statement = select(ProjectForeshadowing).where(ProjectForeshadowing.project_id == project_id)
        if requested:
            statement = statement.where(ProjectForeshadowing.status.in_(sorted(requested)))
        items = self.session.exec(
            statement.order_by(ProjectForeshadowing.planted_chapter.asc(), ProjectForeshadowing.created_at.asc())
        ).all()
        return {
            "project_id": project_id,
            "current_chapter": current_chapter,
            "data": [self._serialize_foreshadowing(item, current_chapter) for item in items],
        }

    def decide_foreshadowing(
        self,
        project_id: str,
        item_id: str,
        *,
        action: str,
        note: str = "",
        current_chapter: int | None = None,
    ) -> dict[str, Any]:
        current_chapter = current_chapter or self._current_chapter(project_id, self._project(project_id))
        self._refresh_overdue(project_id, current_chapter)
        item = self.session.get(ProjectForeshadowing, item_id)
        if item is None or item.project_id != project_id:
            raise ValueError("伏笔记录不存在")
        action = str(action or "").strip().lower()
        transitions = {
            "accept": ({"pending_review"}, "active"),
            "advance": ({"active", "advanced", "overdue"}, "advanced"),
            "resolve": ({"active", "advanced", "overdue"}, "resolved"),
            "ignore": ({"pending_review", "active", "advanced", "overdue"}, "ignored"),
        }
        if action not in transitions:
            raise ValueError("伏笔操作仅支持 accept、advance、resolve 或 ignore")
        allowed, target = transitions[action]
        if item.status not in allowed:
            raise ValueError(f"当前状态 {item.status} 不能执行 {action}")
        item.status = target
        item.resolution_note = str(note or "").strip()
        item.updated_at = datetime.now()
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return self._serialize_foreshadowing(item, current_chapter)

    def narrative_graph(
        self,
        project_id: str,
        *,
        node_types: list[str] | None = None,
        chapter_number: int | None = None,
        include_pending: bool = False,
    ) -> dict[str, Any]:
        self._project(project_id)
        requested_types = {value for value in (node_types or []) if value}
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        locked_facts = self.session.exec(
            select(ProjectContent).where(
                ProjectContent.project_id == project_id,
                ProjectContent.content_type.in_(["project_bible", "world_asset"]),
                ProjectContent.is_locked == True,
            )
        ).all()
        for fact in locked_facts:
            data = loads_json(fact.data_json)
            raw_type = str(data.get("entity_type") or data.get("role") or fact.content_type).lower()
            node_type = self._graph_node_type(raw_type)
            nodes.append({
                "id": f"fact:{fact.id}", "type": node_type, "label": fact.title or data.get("entity_name") or node_type,
                "confirmed": True, "source": {"content_id": fact.id, "version": fact.version, "kind": fact.content_type},
                "summary": str(data.get("summary") or data.get("details") or fact.text_content)[:500],
            })

        snapshots = self.session.exec(
            select(ProjectNarrativeSnapshot).where(
                ProjectNarrativeSnapshot.project_id == project_id,
                ProjectNarrativeSnapshot.status == NarrativeSnapshotStatus.SUCCESS.value,
            ).order_by(ProjectNarrativeSnapshot.chapter_number.asc(), ProjectNarrativeSnapshot.updated_at.desc())
        ).all()
        seen_chapters: set[int] = set()
        included_snapshots: list[ProjectNarrativeSnapshot] = []
        for snapshot in snapshots:
            if snapshot.chapter_number in seen_chapters:
                continue
            if chapter_number is not None and snapshot.chapter_number != chapter_number:
                continue
            seen_chapters.add(snapshot.chapter_number)
            included_snapshots.append(snapshot)
            chapter_id = f"chapter:{snapshot.chapter_number}"
            nodes.append({
                "id": chapter_id, "type": "chapter", "label": f"第 {snapshot.chapter_number} 章",
                "confirmed": True, "source": {"content_id": snapshot.source_content_id, "snapshot_id": snapshot.id, "version": snapshot.source_version},
                "summary": snapshot.summary,
            })

        snapshot_ids = [item.id for item in included_snapshots]
        if snapshot_ids:
            event_statuses = {"confirmed"}
            if include_pending:
                event_statuses.add("pending_review")
            events = self.session.exec(
                select(ProjectStoryEvent).where(
                    ProjectStoryEvent.project_id == project_id,
                    ProjectStoryEvent.snapshot_id.in_(snapshot_ids),
                    ProjectStoryEvent.status.in_(sorted(event_statuses)),
                ).order_by(ProjectStoryEvent.chapter_number.asc(), ProjectStoryEvent.timeline_order.asc())
            ).all()
            for event in events:
                event_id = f"event:{event.id}"
                nodes.append({
                    "id": event_id, "type": "event", "label": event.title or f"第 {event.chapter_number} 章事件",
                    "confirmed": event.status in self._EVENT_CONFIRMED_STATUSES,
                    "source": {"content_id": event.source_content_id, "event_id": event.id, "snapshot_id": event.snapshot_id},
                    "summary": event.description,
                    "participants": loads_json(event.participants_json), "location": event.location,
                })
                edges.append({"id": f"occurs:{event.id}", "type": "occurs_in", "source": event_id, "target": f"chapter:{event.chapter_number}", "confirmed": event.status == "confirmed"})

        ledger_statuses = {"active", "advanced", "resolved", "overdue"}
        if include_pending:
            ledger_statuses.add("pending_review")
        ledger = self.session.exec(
            select(ProjectForeshadowing).where(
                ProjectForeshadowing.project_id == project_id,
                ProjectForeshadowing.status.in_(sorted(ledger_statuses)),
            ).order_by(ProjectForeshadowing.planted_chapter.asc())
        ).all()
        for item in ledger:
            if chapter_number is not None and item.planted_chapter != chapter_number:
                continue
            item_id = f"foreshadowing:{item.id}"
            nodes.append({
                "id": item_id, "type": "foreshadowing", "label": item.statement or f"第 {item.planted_chapter} 章伏笔",
                "confirmed": item.status != "pending_review", "status": item.status,
                "source": {"content_id": item.source_content_id, "foreshadowing_id": item.id, "snapshot_id": item.snapshot_id},
                "expected_window": loads_json(item.expected_window_json),
            })
            edges.append({"id": f"plants:{item.id}", "type": "plants", "source": f"chapter:{item.planted_chapter}", "target": item_id, "confirmed": item.status != "pending_review"})

        if requested_types:
            permitted_ids = {node["id"] for node in nodes if node["type"] in requested_types}
            nodes = [node for node in nodes if node["id"] in permitted_ids]
            edges = [edge for edge in edges if edge["source"] in permitted_ids and edge["target"] in permitted_ids]
        return {"project_id": project_id, "nodes": nodes, "edges": edges, "include_pending": include_pending}

    def _refresh_overdue(self, project_id: str, current_chapter: int) -> None:
        changed = False
        rows = self.session.exec(
            select(ProjectForeshadowing).where(
                ProjectForeshadowing.project_id == project_id,
                ProjectForeshadowing.status.in_(["active", "advanced"]),
            )
        ).all()
        for item in rows:
            window = loads_json(item.expected_window_json)
            end = int(window.get("end") or 0) if isinstance(window, dict) else 0
            if end and current_chapter > end:
                item.status = ForeshadowingStatus.OVERDUE.value
                item.updated_at = datetime.now()
                self.session.add(item)
                changed = True
        if changed:
            self.session.commit()

    def _serialize_foreshadowing(self, item: ProjectForeshadowing, current_chapter: int) -> dict[str, Any]:
        window = loads_json(item.expected_window_json)
        start = int(window.get("start") or 0) if isinstance(window, dict) else 0
        end = int(window.get("end") or 0) if isinstance(window, dict) else 0
        timing = "unscheduled"
        if start and current_chapter < start:
            timing = "upcoming"
        elif end and current_chapter > end and item.status not in {"resolved", "ignored", "superseded"}:
            timing = "overdue"
        elif start or end:
            timing = "in_window"
        return {
            "id": item.id, "project_id": item.project_id, "snapshot_id": item.snapshot_id,
            "source_content_id": item.source_content_id, "source_version": item.source_version,
            "chapter_number": item.chapter_number, "kind": item.kind, "statement": item.statement,
            "planted_chapter": item.planted_chapter, "expected_window": window, "status": item.status,
            "timing": timing, "evidence_anchor": loads_json(item.evidence_anchor_json),
            "resolution_note": item.resolution_note, "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(),
        }

    @staticmethod
    def _graph_node_type(value: str) -> str:
        aliases = {"character": "character", "location": "location", "organization": "organization", "item": "item", "world_rule": "world_rule", "rule": "world_rule"}
        return aliases.get(value, "world_rule")

    def _current_chapter(self, project_id: str, project: CreativeProject) -> int:
        latest = self.session.exec(
            select(ProjectNarrativeSnapshot.chapter_number).where(
                ProjectNarrativeSnapshot.project_id == project_id,
                ProjectNarrativeSnapshot.status == NarrativeSnapshotStatus.SUCCESS.value,
            ).order_by(ProjectNarrativeSnapshot.chapter_number.desc())
        ).first()
        if latest:
            return int(latest)
        plan = loads_json(project.chapter_plan_json)
        chapters = plan.get("chapters") if isinstance(plan, dict) else []
        if not isinstance(chapters, list):
            chapters = []
        return max((int(item.get("chapter_number") or 0) for item in chapters if isinstance(item, dict)), default=1) or 1

    def _project(self, project_id: str) -> CreativeProject:
        project = self.session.get(CreativeProject, project_id)
        if project is None:
            raise ValueError("创作项目不存在")
        return project
