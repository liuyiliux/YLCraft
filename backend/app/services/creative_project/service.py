"""Creative project workflow service."""

from __future__ import annotations

import json
import hashlib
import logging
import math
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from app.db.models.asset_hub import AssetNode, AssetType, AssetVersion
from app.db.models.character import Character, CharacterRole, CharacterSourceType, CharacterStoryLink
from app.db.models.creative_project import (
    CreativeProject,
    CreativeProjectStatus,
    ProjectAssetLink,
    ProjectContent,
    ProjectGenerationLog,
    ProjectContinuityCandidate,
    ProjectNarrativeContextSnapshot,
    ProjectNarrativeSnapshot,
    ProjectForeshadowing,
)
from app.db.models.novel import NovelChapter
from app.db.models.platform_template import PlatformTemplate
from app.db.models.task import ProjectTaskRecord
from app.services.ai.types import LLMMessage
from app.services.creative_project.schemas import (
    ChapterOutlineScenesSchema,
    ChapterOutlineSchema,
    ChapterPlanSchema,
    ComicPagesSchema,
    NovelBodySchema,
    NarrativeHealthIssueSchema,
    ProjectNarrativeHealthSchema,
    ReferenceAssetMatchSchema,
    ShortDramaScriptSchema,
    StoryOutlineSchema,
    StoryboardSchema,
    WriterRoomCharacterRehearsalSchema,
    WriterRoomProseReviewSchema,
    WriterRoomSceneBeatsSchema,
)
from app.services.creative_project.semantic_recall import (
    DisabledNarrativeSemanticRecallAdapter,
    NarrativeRecallCandidate,
    NarrativeRecallResult,
    NarrativeSemanticRecallAdapter,
)

logger = logging.getLogger("ylcraft.creative_project")

TModel = TypeVar("TModel", bound=BaseModel)

WRITER_ROOM_STEP_ORDER = (
    "scene_beats",
    "character_rehearsal",
    "prose_draft",
    "prose_humanized",
    "prose_review",
    "prose_rewrite",
)

_MOJIBAKE_PRIMARY_MARKERS = ("\u00c2", "\u00c3")


def _cjk_character_count(value: str) -> int:
    return sum(
        1
        for char in value
        if "\u3400" <= char <= "\u4dbf"
        or "\u4e00" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
    )


def repair_utf8_mojibake(value: Any, *, max_passes: int = 2) -> Any:
    """Repair legacy UTF-8-as-Latin-1 text without touching valid CJK text.

    Some early project imports decoded UTF-8 bytes as Latin-1 before saving.
    A second save could repeat that mistake, so a value may need two passes.
    We only accept a conversion when it restores CJK characters or removes the
    characteristic ``\u00c2``/``\u00c3`` marker pair. This keeps ordinary text intact.
    """
    if isinstance(value, dict):
        return {key: repair_utf8_mojibake(item, max_passes=max_passes) for key, item in value.items()}
    if isinstance(value, list):
        return [repair_utf8_mojibake(item, max_passes=max_passes) for item in value]
    if not isinstance(value, str) or not value:
        return value

    repaired = value
    for _ in range(max_passes):
        try:
            candidate = repaired.encode("latin-1").decode("utf-8")
        except UnicodeError:
            break
        if candidate == repaired:
            break

        current_cjk = _cjk_character_count(repaired)
        candidate_cjk = _cjk_character_count(candidate)
        current_markers = sum(repaired.count(marker) for marker in _MOJIBAKE_PRIMARY_MARKERS)
        candidate_markers = sum(candidate.count(marker) for marker in _MOJIBAKE_PRIMARY_MARKERS)
        if candidate_cjk > current_cjk or (current_markers and candidate_markers < current_markers):
            repaired = candidate
            continue
        break
    return repaired


def dumps_json(data: Any) -> str:
    return json.dumps(repair_utf8_mojibake(data or {}), ensure_ascii=False)


def loads_json(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return {} if fallback is None else fallback
    try:
        # Old imported project records may still contain UTF-8 text that was
        # decoded as Latin-1 before it reached storage.  Normalize on every
        # read as well as on write so those records cannot leak into the UI or
        # later generation prompts merely because they have not been edited.
        return repair_utf8_mojibake(json.loads(value))
    except Exception:
        return {} if fallback is None else fallback


def normalize_chapter_plan(data: dict[str, Any] | None) -> dict[str, Any]:
    """Derive a plan count from valid unique chapter rows.

    Older projects occasionally persisted a declared ``chapter_count`` that did
    not match the actual plan rows.  The rows are the executable contract for
    downstream chapter work, so retain their original order/content but expose
    a count derived from valid unique chapter numbers.  The previous declared
    count is kept as provenance instead of being silently discarded.
    """
    normalized = dict(data or {})
    chapters = normalized.get("chapters")
    if isinstance(chapters, list):
        legacy_count = normalized.get("chapter_count")
        numbers: set[int] = set()
        for item in chapters:
            if not isinstance(item, dict):
                continue
            raw_number = item.get("chapter_number")
            try:
                chapter_number = int(raw_number)
            except (TypeError, ValueError):
                continue
            if isinstance(raw_number, bool) or chapter_number <= 0:
                continue
            numbers.add(chapter_number)
        normalized["chapter_count"] = len(numbers)
        if legacy_count is not None and legacy_count != normalized["chapter_count"]:
            normalized["legacy_chapter_count"] = legacy_count
    return normalized


def validate_chapter_plan(data: dict[str, Any] | None) -> None:
    """Reject ambiguous chapter plans before they become downstream inputs.

    A duplicate chapter number makes every chapter-scoped stage ambiguous:
    generation may attach to either row and the reader can appear to have a
    duplicate chapter.  Preserve the submitted row order, but require a unique
    positive chapter number for every explicit row.
    """
    chapters = (data or {}).get("chapters") if isinstance(data, dict) else None
    if chapters is None:
        return
    if not isinstance(chapters, list):
        raise ValueError("章节规划的 chapters 必须是数组")

    seen: set[int] = set()
    duplicates: set[int] = set()
    for index, item in enumerate(chapters, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 条章节规划不是对象")
        raw_number = item.get("chapter_number")
        try:
            chapter_number = int(raw_number)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"第 {index} 条章节缺少有效章节号") from exc
        if isinstance(raw_number, bool) or chapter_number <= 0 or str(raw_number).strip() != str(chapter_number):
            raise ValueError(f"第 {index} 条章节号必须是正整数")
        if chapter_number in seen:
            duplicates.add(chapter_number)
        seen.add(chapter_number)

    if duplicates:
        numbers = ", ".join(str(number) for number in sorted(duplicates))
        raise ValueError(f"章节号重复：第 {numbers} 章。请修改后再保存")


def writer_room_allows_length_expansion(instruction: str | None) -> bool:
    """Let targeted rewrites grow when the user explicitly asks for expansion."""
    text = str(instruction or "").lower()
    if not text:
        return False
    negative_markers = ("不要扩写", "不用扩写", "禁止扩写", "不扩写", "不要加长", "keep length")
    if any(marker in text for marker in negative_markers):
        return False
    expansion_markers = (
        "扩写",
        "扩充",
        "扩展",
        "加长",
        "补足",
        "增加篇幅",
        "目标字数",
        "目标4000",
        "目标 4000",
        "目标4500",
        "目标 4500",
        "expand",
        "longer",
    )
    return any(marker in text for marker in expansion_markers)


def _writer_room_requested_character_bounds(instruction: str | None) -> tuple[int | None, int | None]:
    """Extract an explicit prose length range from a Writer Room instruction."""
    text = str(instruction or "")
    if not text or any(marker in text.lower() for marker in ("keep length", "不要扩写", "不用扩写", "禁止扩写")):
        return None, None

    patterns = (
        r"(?:目标|至少|不少于|扩写到|写到|达到)\s*(\d{3,5})\s*(?:(?:-|~|～|至|到)\s*(\d{3,5}))?\s*(?:个?字|个?中文字符|characters?)",
        r"(\d{3,5})\s*(?:(?:-|~|～|至|到)\s*(\d{3,5}))?\s*(?:个?字|个?中文字符|characters?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        lower = int(match.group(1))
        upper = int(match.group(2)) if match.group(2) else None
        if upper is not None and upper < lower:
            lower, upper = upper, lower
        if 800 <= lower <= 20000:
            return lower, upper if upper is not None and upper <= 20000 else None
    return None, None


def writer_room_requested_minimum_characters(instruction: str | None) -> int | None:
    """Extract an explicit prose length floor from a Writer Room instruction."""
    return _writer_room_requested_character_bounds(instruction)[0]


def writer_room_requested_maximum_characters(instruction: str | None) -> int | None:
    """Extract an explicit prose length ceiling from a Writer Room instruction."""
    return _writer_room_requested_character_bounds(instruction)[1]


def writer_room_output_max_tokens(maximum_characters: int | None) -> int:
    """Keep a requested prose range from inheriting the generic 12k token budget."""
    if maximum_characters is None:
        return 12000
    # Chinese prose is close to one token per character for the configured
    # models. Keep only a compact JSON/punctuation margin: a larger multiplier
    # lets providers ignore a 4-5k character contract and emit 6k+ chapters.
    return min(8000, max(3500, maximum_characters + 350))


def writer_room_effective_instruction(
    step: str,
    instruction: str | None,
    source_word_count: int = 0,
) -> str:
    """Supply the page/Agent default for prose without overriding explicit direction."""
    explicit = str(instruction or "").strip()
    if explicit or step not in {"prose_draft", "prose_humanized", "prose_rewrite"}:
        return explicit

    if source_word_count >= 4200:
        length_target = "至少 4000 字"
    elif source_word_count >= 3000:
        length_target = "至少 3500 字"
    else:
        length_target = "至少 3000 字"
    return (
        f"目标 {length_target}。输出完整连载小说正文，不写提纲、设定说明或审稿意见。"
        "用具体动作、物件互动、停顿和有潜台词的对白推进冲突；保留本章事实、人物关系和结尾钩子。"
    )


def _list_join(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "、".join(str(item) for item in value if str(item or "").strip())
    return str(value)


def _dedupe_keep_order(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    if values is None:
        return result
    if isinstance(values, str):
        values = [values]
    for value in values if isinstance(values, list) else list(values):
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


class CreativeProjectService:
    """业务编排：创作项目、阶段内容、生成日志和素材关联。"""

    def __init__(
        self,
        session: Session,
        ai_service: Any | None = None,
        semantic_recall_adapter: NarrativeSemanticRecallAdapter | None = None,
    ):
        self.session = session
        self.semantic_recall_adapter = semantic_recall_adapter or DisabledNarrativeSemanticRecallAdapter()
        if ai_service is not None:
            self.ai_service = ai_service
        else:
            from app.services.ai import get_ai_service

            self.ai_service = get_ai_service()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_project(
        self,
        *,
        title: str,
        project_type: str = "short_drama",
        source_type: str = "original_idea",
        source_ref: dict[str, Any] | None = None,
        idea: str = "",
        settings: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CreativeProject:
        meta = dict(metadata or {})
        if idea:
            meta["idea"] = idea.strip()

        project = CreativeProject(
            title=title.strip() or self._title_from_idea(idea),
            project_type=project_type or "short_drama",
            source_type=source_type or "original_idea",
            source_ref_json=dumps_json(source_ref or {}),
            settings_json=dumps_json(settings or {}),
            metadata_json=dumps_json(meta),
        )
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        return project

    def list_projects(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        project_type: str | None = None,
    ) -> tuple[list[CreativeProject], int]:
        query = select(CreativeProject)
        count_query = select(func.count(CreativeProject.id))
        if status:
            query = query.where(CreativeProject.status == status)
            count_query = count_query.where(CreativeProject.status == status)
        if project_type:
            query = query.where(CreativeProject.project_type == project_type)
            count_query = count_query.where(CreativeProject.project_type == project_type)
        query = query.order_by(CreativeProject.updated_at.desc()).offset(offset).limit(limit)
        projects = self.session.exec(query).all()
        total = self.session.exec(count_query).one()
        return projects, int(total or 0)

    def get_project(self, project_id: str) -> CreativeProject | None:
        return self.session.get(CreativeProject, project_id)

    def update_project(self, project_id: str, data: dict[str, Any]) -> CreativeProject | None:
        project = self.get_project(project_id)
        if not project:
            return None

        scalar_fields = {"title", "project_type", "source_type", "status", "current_stage"}
        json_fields = {
            "source_ref": "source_ref_json",
            "outline": "outline_json",
            "chapter_plan": "chapter_plan_json",
            "settings": "settings_json",
            "metadata": "metadata_json",
            "canvas": "metadata_json",
        }
        for key, value in data.items():
            if key in scalar_fields and value is not None:
                setattr(project, key, value)
            elif key in json_fields and value is not None:
                if key == "canvas":
                    meta = loads_json(project.metadata_json)
                    meta["canvas"] = value
                    project.metadata_json = dumps_json(meta)
                else:
                    if key == "chapter_plan":
                        validate_chapter_plan(value)
                        value = normalize_chapter_plan(value)
                    setattr(project, json_fields[key], dumps_json(value))
        project.updated_at = datetime.now()
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        return project

    def delete_project(self, project_id: str) -> dict[str, int]:
        """Delete a creative project and its project-local records.

        Characters and asset library nodes are deliberately kept. The project only owns
        content versions, project links, generation logs and story-character links.
        """
        project = self.get_project(project_id)
        if not project:
            raise ValueError("创作项目不存在")

        stats = {
            "contents": 0,
            "asset_links": 0,
            "generation_logs": 0,
            "character_links": 0,
            "projects": 1,
        }

        for model, key, predicate in [
            (ProjectAssetLink, "asset_links", ProjectAssetLink.project_id == project_id),
            (ProjectGenerationLog, "generation_logs", ProjectGenerationLog.project_id == project_id),
            (ProjectContent, "contents", ProjectContent.project_id == project_id),
            (CharacterStoryLink, "character_links", CharacterStoryLink.story_id == project_id),
        ]:
            rows = self.session.exec(select(model).where(predicate)).all()
            stats[key] = len(rows)
            for row in rows:
                self.session.delete(row)

        self.session.delete(project)
        self.session.commit()
        return stats

    def fill_demo_data(self, project_id: str, *, overwrite: bool = False) -> dict[str, Any]:
        """Fill a project with readable demo data for end-to-end testing."""
        project = self._require_project(project_id)
        outline = self._demo_outline(project)
        chapter_plan = self._demo_chapter_plan()

        if overwrite:
            contents = self.session.exec(
                select(ProjectContent).where(ProjectContent.project_id == project_id)
            ).all()
            for content in contents:
                self.session.delete(content)
            self.session.flush()

        changed = {"outline": False, "chapter_plan": False, "contents": 0, "characters": 0}
        if overwrite or not loads_json(project.outline_json):
            project.outline_json = dumps_json(outline)
            changed["outline"] = True
        if overwrite or not loads_json(project.chapter_plan_json).get("chapters"):
            project.chapter_plan_json = dumps_json(chapter_plan)
            changed["chapter_plan"] = True

        for chapter_number in [1, 2]:
            for content_type, title, data, text in self._demo_chapter_contents(chapter_number):
                if not overwrite and self._content_exists(project_id, content_type, chapter_number):
                    continue
                self._create_content(
                    project_id=project_id,
                    content_type=content_type,
                    title=title,
                    data=data,
                    text_content=text,
                    chapter_number=chapter_number,
                    episode_number=chapter_number,
                )
                changed["contents"] += 1

        meta = loads_json(project.metadata_json)
        meta.setdefault("idea", "短剧但是不降智：高概念悬疑短剧，靠严密逻辑和人物选择推进爽感。")
        meta["demo_data_filled_at"] = datetime.now().isoformat()
        project.metadata_json = dumps_json(meta)
        project.status = CreativeProjectStatus.READY.value
        project.current_stage = "storyboard"
        project.updated_at = datetime.now()
        self.session.add(project)
        self.session.commit()

        try:
            changed["characters"] = len(self.sync_outline_characters(project_id))
        except Exception as exc:
            logger.warning("Demo data character sync skipped: %s", exc)

        self.session.refresh(project)
        return {"project": project, "changed": changed}

    def sync_project_bible(self, project_id: str, *, overwrite: bool = False) -> list[ProjectContent]:
        """Create editable project-bible and world-asset cards from the latest outline.

        The cards are stored as ProjectContent rows so existing deployments do not
        need a schema migration. Re-running without overwrite only fills missing
        cards; overwrite creates fresh versions from the current outline.
        """
        project = self._require_project(project_id)
        outline = loads_json(project.outline_json)
        if not outline:
            raise ValueError("请先生成或保存故事大纲")

        created: list[ProjectContent] = []
        for card in self._project_bible_cards_from_outline(outline):
            if not overwrite and self._latest_content_by_data_key(
                project_id,
                "project_bible",
                "section_key",
                card["section_key"],
            ):
                continue
            created.append(
                self._create_content(
                    project_id=project_id,
                    content_type="project_bible",
                    title=card["title"],
                    data=card,
                    text_content=self._bible_card_text(card),
                )
            )

        for card in self._world_asset_cards_from_outline(outline):
            if not overwrite and self._latest_content_by_data_key(
                project_id,
                "world_asset",
                "asset_key",
                card["asset_key"],
            ):
                continue
            created.append(
                self._create_content(
                    project_id=project_id,
                    content_type="world_asset",
                    title=card["title"],
                    data=card,
                    text_content=self._bible_card_text(card),
                )
            )

        meta = loads_json(project.metadata_json)
        meta["project_bible_synced_at"] = datetime.now().isoformat()
        project.metadata_json = dumps_json(meta)
        project.updated_at = datetime.now()
        self.session.add(project)
        self.session.commit()
        for content in created:
            self.session.refresh(content)
        return created

    def extract_continuity_candidates(self, project_id: str, content_id: str) -> list[ProjectContent]:
        """Project generated continuity notes into reviewable world-asset candidates."""
        self._require_project(project_id)
        source = self.session.get(ProjectContent, content_id)
        if not source or source.project_id != project_id:
            raise ValueError("项目正文不存在")
        source_data = loads_json(source.data_json)
        notes = [str(note).strip() for note in (source_data.get("continuity_notes") or []) if str(note).strip()]
        if not notes:
            raise ValueError("当前正文没有可提取的连续性备注")

        existing = self.session.exec(
            select(ProjectContent).where(
                ProjectContent.project_id == project_id,
                ProjectContent.content_type == "world_asset",
                ProjectContent.source_content_id == content_id,
            )
        ).all()
        existing_by_note = {
            str(loads_json(item.data_json).get("fact") or "").strip(): item
            for item in existing
        }
        candidates: list[ProjectContent] = []
        for index, note in enumerate(notes, start=1):
            if note in existing_by_note:
                candidates.append(existing_by_note[note])
                continue
            data = {
                "asset_kind": "continuity_candidate",
                "status": "candidate",
                "fact": note,
                "source_content_id": content_id,
                "source_chapter": source.chapter_number or source.episode_number,
                "review_required": True,
            }
            candidate = ProjectContent(
                project_id=project_id,
                content_type="world_asset",
                chapter_number=source.chapter_number,
                episode_number=source.episode_number,
                title=f"第 {source.chapter_number or source.episode_number or ''} 章连续性候选 {index}",
                data_json=dumps_json(data),
                text_content=note,
                source_content_id=content_id,
                version=1,
            )
            self.session.add(candidate)
            candidates.append(candidate)
        self.session.commit()
        for candidate in candidates:
            self.session.refresh(candidate)
        return candidates

    # ------------------------------------------------------------------
    # Continuity fact workflow (creative-project-continuity-facts)
    # ------------------------------------------------------------------

    @staticmethod
    def compute_continuity_fingerprint(
        project_id: str,
        source_kind: str,
        source_content_id: str | None,
        payload: dict[str, Any],
    ) -> str:
        """source-aware 候选指纹，用于去重（同一来源+同一事实只入库一次）。"""
        anchor = payload.get("evidence_anchor") or {}
        seed = "|".join(
            [
                str(project_id or ""),
                str(source_kind or ""),
                str(source_content_id or ""),
                str(payload.get("entity_type") or ""),
                str(payload.get("entity_name") or "").strip().lower(),
                str(payload.get("claim") or "").strip().lower(),
                str(anchor.get("chapter_number") or ""),
                str(anchor.get("paragraph_index") or ""),
                str((payload.get("evidence_excerpt") or "")[:120]).strip().lower(),
            ]
        )
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    def list_continuity_candidates(
        self,
        project_id: str,
        *,
        status: str | None = None,
        source_content_id: str | None = None,
        limit: int = 200,
    ) -> list[ProjectContinuityCandidate]:
        self._require_project(project_id)
        stmt = select(ProjectContinuityCandidate).where(
            ProjectContinuityCandidate.project_id == project_id
        )
        if status:
            stmt = stmt.where(ProjectContinuityCandidate.status == status)
        if source_content_id:
            stmt = stmt.where(
                ProjectContinuityCandidate.source_content_id == source_content_id
            )
        stmt = (
            stmt.order_by(ProjectContinuityCandidate.created_at.desc())
            .limit(limit)
        )
        return list(self.session.exec(stmt).all())

    def extract_continuity_candidates_v2(
        self,
        project_id: str,
        content_id: str,
        *,
        source_kind: str = "prose_review",
        candidates_in: list[dict[str, Any]],
    ) -> list[ProjectContinuityCandidate]:
        """结构化候选入库（idempotent by source fingerprint）。"""
        self._require_project(project_id)
        source = self.session.get(ProjectContent, content_id)
        if not source or source.project_id != project_id:
            raise ValueError("项目正文不存在")

        if not candidates_in:
            raise ValueError("未提供候选事实")

        result: list[ProjectContinuityCandidate] = []
        for payload in candidates_in:
            entity_type = (
                str(payload.get("entity_type") or "other").strip().lower() or "other"
            )
            entity_name = str(payload.get("entity_name") or "").strip()
            claim = str(payload.get("claim") or "").strip()
            excerpt = str(payload.get("evidence_excerpt") or "").strip()
            if not claim and not excerpt:
                continue

            fingerprint = self.compute_continuity_fingerprint(
                project_id, source_kind, content_id, payload
            )
            existing = self.session.exec(
                select(ProjectContinuityCandidate).where(
                    ProjectContinuityCandidate.project_id == project_id,
                    ProjectContinuityCandidate.source_kind == source_kind,
                    ProjectContinuityCandidate.source_fingerprint == fingerprint,
                )
            ).first()
            if existing is not None:
                result.append(existing)
                continue

            anchor = payload.get("evidence_anchor") or {}
            if not isinstance(anchor, dict):
                anchor = {}
            candidate = ProjectContinuityCandidate(
                project_id=project_id,
                source_content_id=content_id,
                source_kind=source_kind,
                source_fingerprint=fingerprint,
                entity_type=entity_type,
                entity_name=entity_name,
                claim=claim,
                evidence_excerpt=excerpt[:480],
                evidence_anchor_json=dumps_json(anchor),
                severity=str(payload.get("severity") or "info").strip().lower()
                or "info",
                suggested_action=str(
                    payload.get("suggested_action") or "create_fact"
                ).strip().lower()
                or "create_fact",
                target_fact_type=str(
                    payload.get("target_fact_type") or "world_asset"
                ).strip().lower()
                or "world_asset",
                status="pending",
            )
            self.session.add(candidate)
            self.session.flush()
            result.append(candidate)

        self.session.commit()
        for c in result:
            self.session.refresh(c)
        return result

    def _build_fact_from_candidate(
        self,
        candidate: ProjectContinuityCandidate,
        *,
        resolution_note: str = "",
    ) -> ProjectContent:
        """accept 时把候选物化为 project_bible / world_asset 内容卡（locked）。"""
        chapter_number: int | None = None
        if candidate.source_content_id:
            source = self.session.get(ProjectContent, candidate.source_content_id)
            if source and source.project_id == candidate.project_id:
                chapter_number = source.chapter_number
        fact_payload = {
            "fact": candidate.claim or candidate.entity_name or candidate.evidence_excerpt,
            "entity_type": candidate.entity_type,
            "entity_name": candidate.entity_name,
            "source_candidate_id": candidate.id,
            "source_content_id": candidate.source_content_id,
            "evidence_excerpt": candidate.evidence_excerpt,
            "evidence_anchor": loads_json(candidate.evidence_anchor_json or "{}"),
            "severity": candidate.severity,
            "resolution_note": resolution_note,
        }
        text = candidate.claim or candidate.entity_name or candidate.evidence_excerpt
        fact = ProjectContent(
            project_id=candidate.project_id,
            content_type=candidate.target_fact_type,
            chapter_number=chapter_number,
            title=candidate.entity_name or (candidate.claim[:60] if candidate.claim else "连续性事实"),
            data_json=dumps_json(fact_payload),
            text_content=text,
            source_content_id=candidate.source_content_id,
            version=1,
            is_locked=True,
        )
        self.session.add(fact)
        self.session.flush()
        self.session.refresh(fact)
        return fact

    def accept_continuity_candidate(
        self,
        project_id: str,
        candidate_id: str,
        *,
        note: str = "",
    ) -> ProjectContinuityCandidate:
        candidate = self.session.get(ProjectContinuityCandidate, candidate_id)
        if not candidate or candidate.project_id != project_id:
            raise ValueError("连续性候选不存在")
        if candidate.status != "pending":
            raise ValueError(f"候选状态为 {candidate.status}，不可再次确认")

        fact = self._build_fact_from_candidate(candidate, resolution_note=note)
        candidate.status = "accepted"
        candidate.resolved_fact_id = fact.id
        candidate.resolution_note = note
        candidate.resolved_at = datetime.now()
        candidate.updated_at = datetime.now()
        self.session.add(candidate)
        self.session.commit()
        self.session.refresh(candidate)
        return candidate

    def ignore_continuity_candidate(
        self,
        project_id: str,
        candidate_id: str,
        *,
        note: str = "",
    ) -> ProjectContinuityCandidate:
        candidate = self.session.get(ProjectContinuityCandidate, candidate_id)
        if not candidate or candidate.project_id != project_id:
            raise ValueError("连续性候选不存在")
        if candidate.status != "pending":
            raise ValueError(f"候选状态为 {candidate.status}，不可忽略")
        candidate.status = "ignored"
        candidate.resolution_note = note
        candidate.resolved_at = datetime.now()
        candidate.updated_at = datetime.now()
        self.session.add(candidate)
        self.session.commit()
        self.session.refresh(candidate)
        return candidate

    def merge_continuity_candidate(
        self,
        project_id: str,
        candidate_id: str,
        *,
        merged_fact_id: str,
        note: str = "",
    ) -> ProjectContinuityCandidate:
        candidate = self.session.get(ProjectContinuityCandidate, candidate_id)
        if not candidate or candidate.project_id != project_id:
            raise ValueError("连续性候选不存在")
        if candidate.status != "pending":
            raise ValueError(f"候选状态为 {candidate.status}，不可合并")
        if not merged_fact_id:
            raise ValueError("merged_fact_id 不能为空")
        fact = self.session.get(ProjectContent, merged_fact_id)
        if not fact or fact.project_id != project_id:
            raise ValueError("目标事实不存在或不属于本项目")
        if fact.content_type not in {"project_bible", "world_asset"}:
            raise ValueError("只能合并到 project_bible / world_asset 事实卡")

        candidate.status = "merged"
        candidate.resolved_fact_id = fact.id
        candidate.resolution_note = note
        candidate.resolved_at = datetime.now()
        candidate.updated_at = datetime.now()

        meta = loads_json(fact.data_json or "{}")
        provenance = meta.get("provenance") or []
        provenance.append(
            {
                "candidate_id": candidate.id,
                "source_content_id": candidate.source_content_id,
                "merged_at": datetime.now().isoformat(),
                "note": note,
            }
        )
        meta["provenance"] = provenance[-12:]
        fact.data_json = dumps_json(meta)
        fact.updated_at = datetime.now()
        self.session.add(fact)
        self.session.add(candidate)
        self.session.commit()
        self.session.refresh(candidate)
        return candidate

    def build_continuity_context_summary(
        self,
        project_id: str,
        *,
        generation_log_id: str | None = None,
    ) -> dict[str, Any]:
        """构造 context pack 的连续性事实摘要（不带完整长文本）。"""
        contents = self.list_contents(project_id)
        locked_counts: dict[str, int] = {"project_bible": 0, "world_asset": 0}
        source_chapters: set[int] = set()
        for content in contents:
            if not content.is_locked:
                continue
            if content.content_type in locked_counts:
                locked_counts[content.content_type] += 1
            if content.chapter_number:
                source_chapters.add(int(content.chapter_number))
        pending_count_stmt = select(ProjectContinuityCandidate).where(
            ProjectContinuityCandidate.project_id == project_id,
            ProjectContinuityCandidate.status == "pending",
        )
        pending_count = len(list(self.session.exec(pending_count_stmt).all()))
        locked_fact_ids = sorted(
            c.id
            for c in contents
            if c.is_locked and c.content_type in {"project_bible", "world_asset"}
        )
        fingerprint = hashlib.sha256(
            "|".join(locked_fact_ids).encode("utf-8")
        ).hexdigest()[:16]
        return {
            "project_id": project_id,
            "locked_fact_count": sum(locked_counts.values()),
            "fact_types": locked_counts,
            "source_chapters": sorted(source_chapters),
            "pending_candidate_count": pending_count,
            "fingerprint": fingerprint,
        }

    def check_continuity(
        self,
        project_id: str,
        chapter_number: int,
        *,
        candidate_id: str | None = None,
    ) -> dict[str, Any]:
        """检查指定候选或当前章节正文与已锁定事实之间是否存在结构化冲突。

        只读，不修改任何数据；返回的 conflict 项带有 contradicting_fact_id，
        可直接用于 merge/resolve_conflict 流程。
        """
        self._require_project(project_id)

        # 被检查对象：候选 > 当前章 novel_body > 跳过
        candidate: ProjectContinuityCandidate | None = None
        if candidate_id:
            candidate = self.session.get(ProjectContinuityCandidate, candidate_id)
            if not candidate or candidate.project_id != project_id:
                raise ValueError("连续性候选不存在")
            if candidate.status != "pending":
                raise ValueError(f"候选状态为 {candidate.status}，不可检查")

        checked_claims: list[str] = []
        evidence_excerpt = ""
        evidence_anchor: dict[str, Any] = {}

        if candidate:
            checked_claims = [
                part for part in (candidate.claim, candidate.evidence_excerpt, candidate.entity_name) if part
            ]
            evidence_excerpt = candidate.evidence_excerpt
            evidence_anchor = loads_json(candidate.evidence_anchor_json or "{}")
        else:
            body = self.session.exec(
                select(ProjectContent)
                .where(ProjectContent.project_id == project_id)
                .where(ProjectContent.content_type == "novel_body")
                .where(ProjectContent.chapter_number == chapter_number)
                .order_by(ProjectContent.version.desc())
            ).first()
            if body and body.text_content:
                checked_claims = [body.text_content[:600]]
                evidence_excerpt = body.text_content[:240]

        if not checked_claims:
            return {
                "project_id": project_id,
                "chapter_number": chapter_number,
                "candidate_id": candidate_id,
                "checked_claims": [],
                "conflicts": [],
                "skipped": True,
                "skip_reason": "没有可检查的候选或正文",
            }

        # 已锁定事实
        locked_facts = self.session.exec(
            select(ProjectContent)
            .where(ProjectContent.project_id == project_id)
            .where(ProjectContent.is_locked == True)  # noqa: E712
            .where(ProjectContent.content_type.in_({"project_bible", "world_asset"}))  # type: ignore[attr-defined]
            .order_by(ProjectContent.created_at.desc())
            .limit(200)
        ).all()

        conflicts: list[dict[str, Any]] = []
        text_to_check = "\n".join(checked_claims)

        for fact in locked_facts:
            fact_data = loads_json(fact.data_json or "{}")
            fact_text = str(fact_data.get("fact") or fact_data.get("claim") or fact.text_content or "").strip()
            if not fact_text:
                continue

            # 规则层：命名实体 / 关键词重叠 + 否定词触发的潜在冲突
            entity_name = str(fact_data.get("entity_name") or "").strip()
            fact_claim = str(fact_data.get("claim") or "").strip()

            match_terms: list[str] = []
            if entity_name and entity_name in text_to_check:
                match_terms.append(entity_name)
            elif fact_claim and fact_claim in text_to_check:
                match_terms.append(fact_claim[:80])
            elif fact_text and fact_text in text_to_check:
                match_terms.append(fact_text[:80])

            if not match_terms:
                #  fallback：关键词分词命中（中文按 2-6 字滑动，英文按空格）
                tokens = self._tokenize_for_continuity(fact_text)
                hits = [token for token in tokens if len(token) >= 2 and token in text_to_check]
                if hits:
                    match_terms = hits[:3]

            if not match_terms:
                continue

            # 否定 / 反义检测：事实里没否定，被检查文本里有“不/没/无”包裹同一实体
            negation_markers = ("不是", "没有", "并未", "不曾", "无", "未", "非")
            has_negation = any(marker in text_to_check for marker in negation_markers)
            # 事实文本里也有否定则不视为冲突（双方同向）
            fact_has_negation = any(marker in fact_text for marker in negation_markers)

            severity = "warning"
            reason = f"与锁定事实出现关键词重叠：{', '.join(match_terms[:3])}"
            if has_negation and not fact_has_negation:
                severity = "conflict"
                reason = f"疑似否定已锁定事实：{', '.join(match_terms[:3])}"

            conflicts.append(
                {
                    "entity_type": str(
                        fact_data.get("entity_type") or (candidate.entity_type if candidate else "other")
                    ),
                    "entity_name": entity_name or (candidate.entity_name if candidate else ""),
                    "claim": candidate.claim if candidate else fact_claim,
                    "contradicting_fact_id": fact.id,
                    "contradicting_fact_excerpt": fact_text[:240],
                    "severity": severity,
                    "suggested_action": "resolve_conflict" if severity == "conflict" else "rewrite_excerpt",
                    "evidence_excerpt": evidence_excerpt[:240],
                    "evidence_anchor": evidence_anchor,
                    "reason": reason,
                }
            )

        # 去重：同一锁定事实只保留一次
        seen_fact_ids = set()
        unique_conflicts = []
        for conflict in conflicts:
            if conflict["contradicting_fact_id"] in seen_fact_ids:
                continue
            seen_fact_ids.add(conflict["contradicting_fact_id"])
            unique_conflicts.append(conflict)

        return {
            "project_id": project_id,
            "chapter_number": chapter_number,
            "candidate_id": candidate_id,
            "checked_claims": checked_claims,
            "conflicts": unique_conflicts,
            "skipped": False,
            "skip_reason": "",
        }

    @staticmethod
    def _tokenize_for_continuity(text: str) -> list[str]:
        """为连续性检查提取可能命名的片段（中文按 2-6 字，英文按空格）。"""
        tokens: list[str] = []
        cleaned = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9\s]", " ", text)
        # 英文/数字词
        for word in cleaned.split():
            if len(word) >= 2:
                tokens.append(word.lower())
        # 中文滑动窗口，优先较长词
        chinese = re.sub(r"[^\u4e00-\u9fa5]", "", text)
        for length in range(6, 1, -1):
            for i in range(0, max(0, len(chinese) - length + 1)):
                token = chinese[i : i + length]
                if len(token) >= 2:
                    tokens.append(token)
        return tokens

    async def rewrite_paragraph(
        self,
        project_id: str,
        content_id: str,
        paragraph_index: int,
        instruction: str,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """段落级非破坏性重写：定位段落、生成候选版本、不回写原文。"""
        self._require_project(project_id)
        content = self.session.get(ProjectContent, content_id)
        if not content or content.project_id != project_id:
            raise ValueError("项目内容不存在")

        source_text = content.text_content or ""
        if not source_text.strip():
            raise ValueError("源内容没有可重写的正文")

        # 分段策略：优先按空行，否则按换行 + 最小长度合并
        paragraphs = self._split_paragraphs(source_text)
        if not paragraphs:
            raise ValueError("未能从源内容解析出段落")

        if paragraph_index < 0 or paragraph_index >= len(paragraphs):
            return {
                "content_id": content_id,
                "project_id": project_id,
                "source_content_id": content_id,
                "paragraph_index": paragraph_index,
                "original_paragraph": "",
                "rewritten_paragraph": "",
                "status": "anchor_not_found",
                "anchor_not_found": True,
                "candidate_content_id": None,
                "instruction": instruction,
            }

        original_paragraph = paragraphs[paragraph_index]
        context_before = "\n\n".join(paragraphs[max(0, paragraph_index - 2) : paragraph_index])
        context_after = "\n\n".join(paragraphs[paragraph_index + 1 : paragraph_index + 3])

        prompt = (
            f"你是小说编辑。请根据用户指令，只重写第 {paragraph_index + 1} 段，"
            "保持前后文语气、人称、节奏一致。只输出重写后的该段，不要解释。\n\n"
            f"前文：\n{context_before}\n\n"
            f"待重写段落：\n{original_paragraph}\n\n"
            f"后文：\n{context_after}\n\n"
            f"指令：{instruction}\n\n"
            "重写后的段落："
        )

        response = await self.ai_service.chat(
            messages=[
                LLMMessage(role="system", content="你是一位严格的中文小说编辑，只输出修改后的段落文本，不输出 Markdown、JSON 或解释。"),
                LLMMessage(role="user", content=prompt),
            ],
            provider=provider,
            model=model,
            temperature=0.6,
            max_tokens=min(2048, max(512, len(original_paragraph) * 3)),
        )

        response_text = self._response_content(response) or ""
        rewritten = response_text.strip()
        if rewritten.startswith("```"):
            rewritten = re.sub(r"^```[\w]*\n?|\n?```$", "", rewritten).strip()

        candidate_content = self._create_content(
            project_id=project_id,
            content_type="prose_rewrite",
            title=f"第 {content.chapter_number or ''} 章段落重写候选（段落 {paragraph_index + 1}）",
            data={
                "source_content_id": content_id,
                "paragraph_index": paragraph_index,
                "original_paragraph": original_paragraph,
                "rewritten_paragraph": rewritten,
                "instruction": instruction,
                "provider": provider or "",
                "model": model or "",
                "rewritten_by": "paragraph_rewrite",
            },
            text_content=rewritten,
            chapter_number=content.chapter_number,
            episode_number=content.episode_number,
            source_content_id=content_id,
        )
        self.session.commit()
        self.session.refresh(candidate_content)

        return {
            "content_id": content_id,
            "project_id": project_id,
            "source_content_id": content_id,
            "paragraph_index": paragraph_index,
            "original_paragraph": original_paragraph,
            "rewritten_paragraph": rewritten,
            "status": "candidate",
            "anchor_not_found": False,
            "candidate_content_id": candidate_content.id,
            "instruction": instruction,
        }

    def _split_paragraphs(self, text: str) -> list[str]:
        """按空行优先、否则按自然换行合并短行来分段。"""
        if not text:
            return []
        # 先尝试空行分段
        by_blank = [p.strip() for p in text.split("\n\n") if p.strip()]
        if len(by_blank) >= 2:
            return by_blank
        # fallback：按换行拆分并合并连续短行
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return []
        paragraphs: list[str] = [lines[0]]
        for line in lines[1:]:
            if len(line) < 40 and len(paragraphs[-1]) < 120:
                paragraphs[-1] += line
            else:
                paragraphs.append(line)
        return paragraphs

    # ------------------------------------------------------------------
    # Novel source
    # ------------------------------------------------------------------

    def create_from_novel(
        self,
        *,
        asset_id: str,
        chapter_ids: list[str] | None = None,
        chapter_indices: list[int] | None = None,
        title: str = "",
        project_type: str = "short_drama",
    ) -> CreativeProject:
        source_node = self.session.get(AssetNode, asset_id)
        if not source_node:
            raise ValueError("小说素材不存在")
        source_meta = source_node.metadata_json or {}
        novel_title = (
            source_meta.get("novel_title")
            or source_meta.get("title")
            or source_node.name
            or "未命名小说"
        )
        novel_author = source_meta.get("novel_author") or source_meta.get("author") or ""

        chapters = self._select_novel_chapters(
            asset_id=asset_id,
            chapter_ids=chapter_ids or [],
            chapter_indices=chapter_indices or [],
        )
        sample_text = self._read_chapter_samples(chapters)
        source_ref = {
            "asset_id": asset_id,
            "chapter_ids": [c.id for c in chapters],
            "chapter_indices": [c.chapter_index for c in chapters],
        }
        metadata = {
            "novel_title": novel_title,
            "novel_author": novel_author,
            "source_sample": sample_text,
        }
        idea = f"改编小说《{novel_title}》"
        if chapters:
            title_list = "、".join(c.chapter_title for c in chapters[:5] if c.chapter_title)
            if title_list:
                idea += f"，选定章节：{title_list}"

        return self.create_project(
            title=title or f"{novel_title} 改编项目",
            project_type=project_type,
            source_type="novel",
            source_ref=source_ref,
            idea=idea,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    async def generate_outline(
        self,
        project_id: str,
        *,
        idea: str = "",
        provider: str | None = None,
        model: str | None = None,
        template_id: str | None = None,
    ) -> dict[str, Any]:
        project = self._require_project(project_id)
        meta = loads_json(project.metadata_json)
        source_idea = idea.strip() or str(meta.get("idea") or "")
        source_sample = str(meta.get("source_sample") or "")
        default_prompt = self._outline_prompt(project, source_idea, source_sample)
        prompt, system_prompt, template_meta = self._stage_prompt(
            stage="outline",
            default_prompt=default_prompt,
            template_id=template_id,
            variables={
                "project_title": project.title,
                "project_type": project.project_type,
                "idea": source_idea or "用户暂未填写创意，请基于项目标题扩展。",
                "source_sample": source_sample[:8000],
            },
        )

        data = await self._generate_json(
            project=project,
            stage="outline",
            prompt=prompt,
            system_prompt=system_prompt,
            schema_model=StoryOutlineSchema,
            provider=provider,
            model=model,
            template_meta=template_meta,
        )
        project.outline_json = dumps_json(data)
        project.title = data.get("title") or project.title
        project.status = CreativeProjectStatus.PLANNING.value
        project.current_stage = "chapter_plan"
        project.updated_at = datetime.now()
        self.session.add(project)
        self._create_content(
            project_id=project.id,
            content_type="outline",
            title=data.get("title", project.title),
            data=data,
            text_content=self._outline_text(data),
        )
        self.session.commit()
        self.session.refresh(project)
        return data

    async def generate_chapter_plan(
        self,
        project_id: str,
        *,
        chapter_count: int = 12,
        append_existing: bool = False,
        provider: str | None = None,
        model: str | None = None,
        template_id: str | None = None,
    ) -> dict[str, Any]:
        project = self._require_project(project_id)
        outline = loads_json(project.outline_json)
        if not outline:
            raise ValueError("请先生成或保存故事大纲")

        existing_plan = loads_json(project.chapter_plan_json)
        existing_chapters = existing_plan.get("chapters") if isinstance(existing_plan, dict) else []
        existing_chapters = existing_chapters if isinstance(existing_chapters, list) else []
        validate_chapter_plan({"chapters": existing_chapters})
        if append_existing:
            existing_numbers = {
                int(item.get("chapter_number") or 0)
                for item in existing_chapters
                if isinstance(item, dict)
            }
            missing_numbers = [number for number in range(1, chapter_count + 1) if number not in existing_numbers]
            if not missing_numbers:
                return {
                    "chapter_count": len(existing_chapters),
                    "chapters": existing_chapters,
                    "appended_chapter_numbers": [],
                }
            if missing_numbers != list(range(min(missing_numbers), chapter_count + 1)):
                raise ValueError("当前章节规划存在中间缺章，请先在编辑器中补齐或重新生成完整规划")
            if not existing_chapters:
                raise ValueError("当前没有可续写的章节规划，请使用完整生成")
            default_prompt = self._chapter_plan_extension_prompt(
                outline=outline,
                existing_plan=existing_plan,
                start_chapter=missing_numbers[0],
                target_chapter_count=chapter_count,
            )
        else:
            default_prompt = self._chapter_plan_prompt(outline, chapter_count)
        prompt, system_prompt, template_meta = self._stage_prompt(
            stage="chapter_plan",
            default_prompt=default_prompt,
            template_id=template_id,
            variables={
                "project_title": project.title,
                "project_type": project.project_type,
                "chapter_count": chapter_count,
                "outline_json": dumps_json(outline),
                "existing_chapter_plan_json": dumps_json(existing_plan),
            },
        )
        data = await self._generate_json(
            project=project,
            stage="chapter_plan",
            prompt=prompt,
            system_prompt=system_prompt,
            schema_model=ChapterPlanSchema,
            provider=provider,
            model=model,
            template_meta=template_meta,
        )
        generated_chapters = data.get("chapters") or []
        validate_chapter_plan({"chapters": generated_chapters})
        if append_existing:
            expected_numbers = list(range(missing_numbers[0], chapter_count + 1))
            by_number = {
                int(item.get("chapter_number") or 0): item
                for item in generated_chapters
                if isinstance(item, dict)
            }
            missing_generated = [number for number in expected_numbers if number not in by_number]
            if missing_generated:
                raise ValueError(f"续写章节规划缺少第 {', '.join(map(str, missing_generated))} 章")
            data["chapters"] = [*existing_chapters, *[by_number[number] for number in expected_numbers]]
            data["chapter_count"] = len(data["chapters"])
            data["appended_chapter_numbers"] = expected_numbers
        data = normalize_chapter_plan(data)
        if not data.get("chapter_count"):
            data["chapter_count"] = chapter_count
        project.chapter_plan_json = dumps_json(data)
        project.status = CreativeProjectStatus.SCRIPTING.value
        project.current_stage = "script"
        project.updated_at = datetime.now()
        self.session.add(project)
        self._create_content(
            project_id=project.id,
            content_type="chapter_plan",
            title=f"{project.title} 章节规划",
            data=data,
            text_content=self._chapter_plan_text(data),
        )
        self.session.commit()
        self.session.refresh(project)
        return data

    async def generate_script(
        self,
        project_id: str,
        *,
        chapter_number: int,
        provider: str | None = None,
        model: str | None = None,
        template_id: str | None = None,
    ) -> dict[str, Any]:
        project = self._require_project(project_id)
        outline = loads_json(project.outline_json)
        chapter_plan = loads_json(project.chapter_plan_json)
        if not outline or not chapter_plan:
            raise ValueError("请先生成故事大纲和章节规划")

        selected_chapter = self._chapter_plan_item(chapter_plan, chapter_number)
        approved_prose = self._latest_content(project_id, "novel_body", chapter_number)
        narrative_provenance = self._narrative_output_provenance(project_id, approved_prose)
        reference_assets = self._project_reference_assets(project_id)
        default_prompt = self._script_prompt(outline, chapter_plan, chapter_number, reference_assets=reference_assets)
        prompt, system_prompt, template_meta = self._stage_prompt(
            stage="script",
            default_prompt=default_prompt,
            template_id=template_id,
            variables={
                "project_title": project.title,
                "project_type": project.project_type,
                "chapter_number": chapter_number,
                "outline_json": dumps_json(outline),
                "chapter_plan_json": dumps_json(chapter_plan),
                "current_chapter_json": dumps_json(selected_chapter),
                "approved_prose": approved_prose.text_content if approved_prose else "",
                "narrative_provenance_json": dumps_json(narrative_provenance),
                "reference_assets_json": dumps_json(reference_assets),
            },
        )
        data = await self._generate_json(
            project=project,
            stage="script",
            prompt=prompt,
            system_prompt=system_prompt,
            schema_model=ShortDramaScriptSchema,
            provider=provider,
            model=model,
            template_meta=template_meta,
            request_metadata={"narrative_provenance": narrative_provenance},
        )
        self._normalize_script_scene_references(data, reference_assets)
        data["narrative_provenance"] = narrative_provenance
        content = self._create_content(
            project_id=project.id,
            content_type="script",
            chapter_number=chapter_number,
            episode_number=data.get("episode_number") or chapter_number,
            title=data.get("title") or f"第 {chapter_number} 集脚本",
            data=data,
            text_content=dumps_json(data),
            source_content_id=approved_prose.id if approved_prose else None,
        )
        self._bind_last_generation_log_to_content(content.id)
        project.status = CreativeProjectStatus.STORYBOARDING.value
        project.current_stage = "storyboard"
        project.updated_at = datetime.now()
        self.session.add(project)
        self.session.commit()
        return data

    async def generate_chapter_outline(
        self,
        project_id: str,
        *,
        chapter_number: int,
        provider: str | None = None,
        model: str | None = None,
        template_id: str | None = None,
    ) -> dict[str, Any]:
        project = self._require_project(project_id)
        outline = loads_json(project.outline_json)
        chapter_plan = loads_json(project.chapter_plan_json)
        if not outline or not chapter_plan:
            raise ValueError("请先生成故事大纲和章节规划")

        current_chapter = self._chapter_plan_item(chapter_plan, chapter_number)
        if not current_chapter:
            raise ValueError(f"章节规划中找不到第 {chapter_number} 章")

        previous_context = self._previous_chapter_context(project_id, chapter_number)
        project_bible_context = self._locked_project_bible_context(project.id)
        default_prompt = self._chapter_outline_prompt(
            outline,
            chapter_plan,
            current_chapter,
            chapter_number,
            previous_context,
            project_bible_context=project_bible_context,
        )
        prompt, system_prompt, template_meta = self._stage_prompt(
            stage="chapter_outline",
            default_prompt=default_prompt,
            template_id=template_id,
            variables={
                "project_title": project.title,
                "project_type": project.project_type,
                "chapter_number": chapter_number,
                "outline_json": dumps_json(outline),
                "chapter_plan_json": dumps_json(chapter_plan),
                "current_chapter_json": dumps_json(current_chapter),
                "previous_context": previous_context,
                "project_bible_context": project_bible_context,
            },
        )
        data = await self._generate_json(
            project=project,
            stage="chapter_outline",
            prompt=prompt,
            system_prompt=system_prompt,
            schema_model=ChapterOutlineSchema,
            provider=provider,
            model=model,
            template_meta=template_meta,
        )
        self._normalize_chapter_outline_v2(data)
        content = self._create_content(
            project_id=project.id,
            content_type="chapter_outline",
            chapter_number=chapter_number,
            episode_number=data.get("chapter_number") or chapter_number,
            title=data.get("title") or f"第 {chapter_number} 章细纲",
            data=data,
            text_content=self._chapter_outline_text(data),
        )
        project.current_stage = "novel_body"
        project.status = CreativeProjectStatus.SCRIPTING.value
        project.updated_at = datetime.now()
        self.session.add(project)
        self.session.commit()
        self.session.refresh(content)
        return data

    async def generate_novel_body(
        self,
        project_id: str,
        *,
        chapter_number: int,
        content_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        template_id: str | None = None,
    ) -> dict[str, Any]:
        project = self._require_project(project_id)
        outline = loads_json(project.outline_json)
        chapter_plan = loads_json(project.chapter_plan_json)
        if not outline or not chapter_plan:
            raise ValueError("请先生成故事大纲和章节规划")

        chapter_outline = self._resolve_source_content(
            project_id=project_id,
            content_type="chapter_outline",
            chapter_number=chapter_number,
            content_id=content_id,
        )
        if not chapter_outline:
            raise ValueError("请先生成该章节的单话细纲")

        chapter_outline_data = loads_json(chapter_outline.data_json)
        context_pack = self._creative_context_pack(
            project_id,
            chapter_number,
            persist=True,
            stage="novel_body",
            source_content_id=chapter_outline.id,
        )
        previous_context = context_pack["previous_context"]
        default_prompt = self._novel_body_prompt(
            outline,
            chapter_plan,
            chapter_outline_data,
            chapter_number,
            context_pack["text"],
        )
        prompt, system_prompt, template_meta = self._stage_prompt(
            stage="novel_body",
            default_prompt=default_prompt,
            template_id=template_id,
            variables={
                "project_title": project.title,
                "project_type": project.project_type,
                "chapter_number": chapter_number,
                "outline_json": dumps_json(outline),
                "chapter_plan_json": dumps_json(chapter_plan),
                "chapter_outline_json": dumps_json(chapter_outline_data),
                "previous_context": previous_context,
                "project_context_pack": context_pack["text"],
                "locked_project_bible_context": context_pack["locked_project_bible_context"],
            },
        )
        data = await self._generate_json(
            project=project,
            stage="novel_body",
            prompt=prompt,
            system_prompt=system_prompt,
            schema_model=NovelBodySchema,
            provider=provider,
            model=model,
            template_meta=template_meta,
            request_metadata={"creative_context": context_pack["metadata"]},
        )
        data = await self._ensure_novel_body_quality(
            project=project,
            stage="novel_body",
            prompt=prompt,
            system_prompt=system_prompt,
            data=data,
            provider=provider,
            model=model,
            request_metadata={"creative_context": context_pack["metadata"]},
        )
        content = str(data.get("content") or "")
        data["word_count"] = len(content)
        body = self._create_content(
            project_id=project.id,
            content_type="novel_body",
            chapter_number=chapter_number,
            episode_number=data.get("chapter_number") or chapter_number,
            title=data.get("title") or f"第 {chapter_number} 章正文",
            data=data,
            text_content=content,
            source_content_id=chapter_outline.id,
        )
        project.current_stage = "comic_pages"
        project.status = CreativeProjectStatus.STORYBOARDING.value
        project.updated_at = datetime.now()
        self.session.add(project)
        self.session.commit()
        self.session.refresh(body)
        return data

    async def refine_novel_body(
        self,
        *,
        project_id: str,
        content_id: str,
        instruction: str,
        provider: str | None = None,
        model: str | None = None,
        template_id: str | None = None,
    ) -> ProjectContent:
        project = self._require_project(project_id)
        content = self.session.get(ProjectContent, content_id)
        if not content or content.project_id != project_id or content.content_type != "novel_body":
            raise ValueError("章节正文不存在")
        instruction = (instruction or "").strip()
        if not instruction:
            raise ValueError("请填写正文修改要求")

        body_data = loads_json(content.data_json)
        source_outline = self.session.get(ProjectContent, content.source_content_id) if content.source_content_id else None
        outline_context = loads_json(source_outline.data_json) if source_outline else {}
        chapter_number = content.chapter_number or content.episode_number or 1
        context_pack = self._creative_context_pack(
            project_id,
            chapter_number,
            persist=True,
            stage="novel_body_refine",
            source_content_id=content.id,
        )
        default_prompt = self._refine_novel_body_prompt(
            project=project,
            content=content,
            body_data=body_data,
            outline_context=outline_context,
            instruction=instruction,
            project_context_pack=context_pack["text"],
        )
        prompt, system_prompt, template_meta = self._stage_prompt(
            stage="novel_body_refine",
            default_prompt=default_prompt,
            template_id=template_id,
            variables={
                "project_title": project.title,
                "project_type": project.project_type,
                "chapter_number": chapter_number,
                "instruction": instruction,
                "body_json": dumps_json(body_data),
                "body_text": content.text_content,
                "chapter_outline_json": dumps_json(outline_context),
                "previous_context": context_pack["previous_context"],
                "project_context_pack": context_pack["text"],
                "locked_project_bible_context": context_pack["locked_project_bible_context"],
            },
        )
        data = await self._generate_json(
            project=project,
            stage="novel_body_refine",
            prompt=prompt,
            system_prompt=system_prompt,
            schema_model=NovelBodySchema,
            provider=provider,
            model=model,
            template_meta=template_meta,
            request_metadata={"creative_context": context_pack["metadata"]},
        )
        data = await self._ensure_novel_body_quality(
            project=project,
            stage="novel_body_refine",
            prompt=prompt,
            system_prompt=system_prompt,
            data=data,
            provider=provider,
            model=model,
            request_metadata={"creative_context": context_pack["metadata"]},
        )
        text = str(data.get("content") or "")
        data["word_count"] = len(text)
        content.title = data.get("title") or content.title
        content.data_json = dumps_json({**body_data, **data})
        content.text_content = text
        content.updated_at = datetime.now()
        self.session.add(content)
        self.session.commit()
        self.session.refresh(content)
        return content

    async def run_writer_room_step(
        self,
        project_id: str,
        *,
        step: str,
        chapter_number: int,
        content_id: str | None = None,
        instruction: str | None = None,
        selected_text: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        template_id: str | None = None,
        rehearsal_mode: str = "fast",
        _context_pack: dict[str, Any] | None = None,
    ) -> ProjectContent:
        project = self._require_project(project_id)
        step = self._normalize_writer_room_step(step)
        # Reset the tracked generation log so a previous step's log cannot leak
        # into this step's binding.
        self._last_generation_log = None
        context = self._writer_room_context(
            project_id=project_id,
            step=step,
            chapter_number=chapter_number,
            source_content_id=content_id,
            selected_text=selected_text,
            context_pack=_context_pack,
        )
        effective_instruction = writer_room_effective_instruction(
            step,
            instruction,
            int(context.get("source_word_count") or 0),
        )
        schema_model = self._writer_room_schema(step)
        requested_maximum = writer_room_requested_maximum_characters(effective_instruction)
        prose_max_tokens = (
            writer_room_output_max_tokens(requested_maximum)
            if step in {"prose_draft", "prose_humanized", "prose_rewrite"} and requested_maximum is not None
            else None
        )
        default_prompt = self._writer_room_prompt(
            project=project,
            step=step,
            chapter_number=chapter_number,
            context=context,
            instruction=effective_instruction,
        )
        prompt, system_prompt, template_meta = self._stage_prompt(
            stage=step,
            default_prompt=default_prompt,
            template_id=template_id,
            variables=self._writer_room_prompt_variables(
                project=project,
                chapter_number=chapter_number,
                context=context,
                instruction=effective_instruction,
                selected_text=selected_text or "",
            ),
        )
        if step == "character_rehearsal" and rehearsal_mode == "team":
            data = await self._run_character_rehearsal_team(project, chapter_number, context)
        else:
            data = await self._generate_json(
                project=project,
                stage=step,
                prompt=prompt,
                system_prompt=system_prompt,
                schema_model=schema_model,
                provider=provider,
                model=model,
                template_meta=template_meta,
                max_tokens=prose_max_tokens,
                request_metadata={"creative_context": context.get("context_pack_metadata") or {}},
            )
        if step in {"prose_draft", "prose_humanized", "prose_rewrite"}:
            self._normalize_prose_content_alias(data)
        if step == "prose_humanized":
            source_word_count = int(context.get("source_word_count") or 0)
            output_text = str(data.get("content") or "")
            output_word_count = len("".join(output_text.split()))
            minimum_word_count = math.ceil(source_word_count * 0.9)
            # Short test fixtures and intentional micro-edits should not pay for a
            # second provider call.  For a real chapter, retry once with an
            # explicit correction instead of accepting a summary masquerading as
            # a polished chapter.
            if source_word_count >= 600 and output_word_count < minimum_word_count:
                retry_prompt = f"""{prompt}

长度复核：上一版润色稿只有约 {output_word_count} 字，低于源稿约 {source_word_count} 字的最低保留线 {minimum_word_count} 字。
请重新输出完整正文；保留所有场景、信息和戏剧动作，扩写被压缩的段落，不要用摘要替代正文。"""
                data = await self._generate_json(
                    project=project,
                    stage=step,
                    prompt=retry_prompt,
                    system_prompt=system_prompt,
                    schema_model=schema_model,
                    provider=provider,
                    model=model,
                    template_meta=template_meta,
                    request_metadata={"creative_context": context.get("context_pack_metadata") or {}},
                )
                self._normalize_prose_content_alias(data)
                data["length_guard"] = {
                    "source_word_count": source_word_count,
                    "minimum_word_count": minimum_word_count,
                    "first_output_word_count": output_word_count,
                    "retried": True,
                }
        if step in {"prose_draft", "prose_humanized", "prose_rewrite"}:
            source_word_count = int(context.get("source_word_count") or 0)
            requested_minimum = writer_room_requested_minimum_characters(effective_instruction)
            requested_maximum = writer_room_requested_maximum_characters(effective_instruction)
            allows_length_expansion = (
                step == "prose_rewrite"
                and (
                    writer_room_allows_length_expansion(effective_instruction)
                    or requested_minimum is not None
                )
            )
            # Candidate prose must be publishable on its own.  Rewrites and
            # humanization are additionally bounded against their explicit
            # source so they cannot silently turn a chapter into a summary.
            # Explicit expansion rewrites are allowed to grow because turning a
            # thin AI-ish draft into a fuller chapter is a first-class workflow.
            minimum_characters = 2800
            maximum_characters: int | None = None
            if step in {"prose_humanized", "prose_rewrite"} and source_word_count >= 600:
                minimum_characters = math.ceil(source_word_count * 0.88)
                if not allows_length_expansion:
                    maximum_characters = math.floor(source_word_count * 1.15)
            if step == "prose_rewrite" and requested_minimum is not None:
                minimum_characters = max(minimum_characters, requested_minimum)
            if step == "prose_rewrite" and requested_maximum is not None:
                # Providers cannot reliably hit an exact Chinese character
                # count. Keep the requested range as the target while allowing
                # a narrow tolerance instead of discarding an otherwise sound
                # chapter and paying for a full retry.
                maximum_characters = requested_maximum + min(
                    400,
                    max(80, math.ceil(requested_maximum * 0.08)),
                )
            data = await self._ensure_novel_body_quality(
                project=project,
                stage=step,
                prompt=prompt,
                system_prompt=system_prompt,
                data=data,
                provider=provider,
                model=model,
                request_metadata={"creative_context": context.get("context_pack_metadata") or {}},
                minimum_characters=minimum_characters,
                maximum_characters=maximum_characters,
            )
        data["chapter_number"] = chapter_number
        if step == "prose_review":
            data = self._normalize_writer_room_review(data)
            if not self._writer_room_review_has_substance(data):
                retry_prompt = f"""{prompt}

审稿结果复核：上一份 JSON 缺少可供作者执行的审稿证据，不能保存为主编审稿。
请只重新输出完整 JSON，不要解释。必须提供至少 2 个 quality_tags、至少 2 条 ai_smell_checks，以及至少一项 strengths 或一条包含 location、problem、suggestion、rewrite_instruction 的具体 issues。所有问题都要引用或描述本稿实际段落、动作、对白或句式；不要返回空数组、泛泛评分、上一版遗留意见或“无”。
"""
                data = await self._generate_json(
                    project=project,
                    stage=step,
                    prompt=retry_prompt,
                    system_prompt=system_prompt,
                    schema_model=schema_model,
                    provider=provider,
                    model=model,
                    template_meta=template_meta,
                    request_metadata={"creative_context": context.get("context_pack_metadata") or {}},
                )
                data = self._normalize_writer_room_review(data)
                if not self._writer_room_review_has_substance(data):
                    raise ValueError("主编审稿结果不完整，未生成可执行的质量意见")
        if step in {"prose_draft", "prose_humanized", "prose_rewrite"}:
            text = str(data.get("content") or "")
            data["word_count"] = len(text)
        else:
            text = self._writer_room_text(step, data)

        # The final successful generation log produced by _generate_json(). If a
        # humanization length retry occurred, the earlier short response's log
        # is left trace-only (content_id stays null) and only this final log is
        # bound to the candidate.
        final_log = getattr(self, "_last_generation_log", None)

        content = self._create_content(
            project_id=project_id,
            content_type=step,
            chapter_number=chapter_number,
            episode_number=data.get("chapter_number") or chapter_number,
            title=data.get("title") or self._writer_room_title(step, chapter_number),
            data={
                **data,
                "writer_room": {
                    "step": step,
                    "source_content_id": content_id or context.get("source_content_id") or "",
                    "source_content_type": context.get("source_content_type") or "",
                    "source_content_version": context.get("source_content_version") or 0,
                    "source_word_count": context.get("source_word_count") or 0,
                    "instruction": effective_instruction,
                    "selected_text": selected_text or "",
                    "generation_log_id": final_log.id if final_log is not None else "",
                    "context_snapshot_id": context.get("context_snapshot_id") or "",
                },
            },
            text_content=text,
            source_content_id=content_id or context.get("source_content_id"),
        )
        # Flush so the new review content has a stable id before we derive
        # continuity candidates from it.
        self.session.flush()
        # Writer Room editorial review may also surface continuity candidates.
        # Persist them as pending ProjectContinuityCandidate rows keyed to this
        # review content. A candidate-extraction failure must never roll back or
        # block saving the review itself.
        raw_candidates = data.get("continuity_candidates")
        if isinstance(raw_candidates, list) and raw_candidates:
            candidate_dicts = [item for item in raw_candidates if isinstance(item, dict)]
            if candidate_dicts:
                try:
                    self.extract_continuity_candidates_v2(
                        project_id,
                        content.id,
                        source_kind="prose_review",
                        candidates_in=candidate_dicts,
                    )
                except ValueError:
                    # Candidate extraction is best-effort alongside the review.
                    pass
        # Backfill the candidate id onto the final generation log so the
        # front-end can match the log to exactly this candidate.
        if final_log is not None:
            final_log.content_id = content.id
        project.current_stage = "writer_room"
        project.updated_at = datetime.now()
        self.session.add(project)
        self.session.commit()
        self.session.refresh(content)
        return content

    async def run_writer_room(
        self,
        project_id: str,
        *,
        steps: list[str],
        chapter_number: int,
        content_id: str | None = None,
        instruction: str | None = None,
        selected_text: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        template_id: str | None = None,
        rehearsal_mode: str = "fast",
        continue_on_error: bool = True,
    ) -> dict[str, Any]:
        requested_steps = [self._normalize_writer_room_step(step) for step in (steps or [])]
        normalized_steps = [step for step in WRITER_ROOM_STEP_ORDER if step in requested_steps]
        if not normalized_steps:
            normalized_steps = list(WRITER_ROOM_STEP_ORDER[:-1])

        # A batch is one deliberate writing pass. Freeze one project context
        # before its first model call so later candidates cannot quietly alter
        # the canon/ledger context seen by subsequent steps.
        context_pack = self._creative_context_pack(
            project_id,
            chapter_number,
            persist=True,
            stage="writer_room_run",
            source_content_id=content_id,
        )

        results: list[dict[str, Any]] = []
        source_content_id = content_id
        blocked_by: str | None = None
        for step in normalized_steps:
            if blocked_by:
                results.append({"step": step, "status": "skipped", "blocked_by": blocked_by})
                continue
            try:
                content = await self.run_writer_room_step(
                    project_id,
                    step=step,
                    chapter_number=chapter_number,
                    content_id=source_content_id,
                    instruction=instruction,
                    selected_text=selected_text if step == "prose_rewrite" else None,
                    provider=provider,
                    model=model,
                    template_id=template_id,
                    rehearsal_mode=rehearsal_mode,
                    _context_pack=context_pack,
                )
                results.append({
                    "step": step,
                    "status": "success",
                    "content_id": content.id,
                    "content_type": content.content_type,
                    "title": content.title,
                    "version": content.version,
                })
                # Every successful candidate becomes the direct source for the
                # following selected step. This keeps partial batch runs
                # deterministic as well: draft -> review remains valid when
                # beats and rehearsal came from an earlier run.
                source_content_id = content.id
            except Exception as exc:
                results.append({"step": step, "status": "failed", "error": str(exc)})
                if not continue_on_error:
                    raise
                # Writer Room steps form a single candidate chain.  A later
                # step must not silently fall back to an older source after
                # its selected upstream candidate failed to generate.
                blocked_by = step

        return {
            "project_id": project_id,
            "chapter_number": chapter_number,
            "requested_steps": requested_steps,
            "context_snapshot_id": context_pack.get("snapshot_id", ""),
            "steps": normalized_steps,
            "results": results,
            "summary": {
                "total": len(results),
                "success": len([item for item in results if item.get("status") == "success"]),
                "failed": len([item for item in results if item.get("status") == "failed"]),
                "skipped": len([item for item in results if item.get("status") == "skipped"]),
            },
        }

    def _resolve_team_characters(self, project_id: str, context: dict[str, Any]) -> list[str]:
        names: list[str] = []
        try:
            names = [
                str(character.name).strip()
                for character in self.sync_outline_characters(project_id)
                if getattr(character, "name", None) and str(character.name).strip()
            ]
        except Exception:  # noqa: BLE001 — outline may not declare characters yet
            names = []
        if names:
            return names
        # Fallback: characters referenced by the scene beats.
        beats = context.get("scene_beats") or {}
        for beat in beats.get("scene_beats") or []:
            if not isinstance(beat, dict):
                continue
            for name in beat.get("characters") or []:
                if name and str(name).strip() and str(name).strip() not in names:
                    names.append(str(name).strip())
        return names

    def _scene_context_for_team(self, context: dict[str, Any]) -> str:
        parts: list[str] = []
        if context.get("scene_beats"):
            parts.append(f"场景节拍：{dumps_json(context.get('scene_beats'))}")
        if context.get("chapter_outline"):
            parts.append(f"章节细纲：{dumps_json(context.get('chapter_outline'))}")
        return "\n".join(parts) or "本章场景"

    async def _run_character_rehearsal_team(
        self,
        project: CreativeProject,
        chapter_number: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Run the declarative ``writer-room-team`` and shape it as a rehearsal candidate."""
        characters = self._resolve_team_characters(project.id, context)
        if not characters:
            raise ValueError("团队演绎需要至少一个角色；请先完善故事大纲中的角色")

        import uuid as _uuid

        from app.db.database import AsyncSessionLocal
        from app.db.models.agent import AgentRun
        from app.services.agent.runtime.delegation import SubagentExecutor, SubagentOrchestrator
        from app.services.agent.team_composer import TeamComposer

        scene_context = self._scene_context_for_team(context)
        parent_run = AgentRun(
            id=f"wrteam_{_uuid.uuid4().hex[:24]}",
            user_id="default",
            session_id=f"wrteam_sess_{_uuid.uuid4().hex[:12]}",
            profile_id="creative-director",
            run_kind="primary",
            status="running",
            objective=f"第{chapter_number}章角色团队演绎",
            context_json=dumps_json({"project_id": project.id, "chapter_number": chapter_number}),
        )
        async with AsyncSessionLocal() as asession:
            asession.add(parent_run)
            await asession.commit()
            executor = SubagentExecutor(AsyncSessionLocal)
            orchestrator = SubagentOrchestrator(asession, executor)
            composer = TeamComposer(orchestrator)
            result = await composer.run(
                "writer-room-team",
                parent_run,
                inputs={
                    "project_id": project.id,
                    "chapter_number": chapter_number,
                    "scene_context": scene_context,
                    "characters": characters,
                },
                user_id="default",
            )

        joined = str(result.get("joined_observation") or "").strip() or "团队演绎未产出可用内容"
        return {
            "chapter_number": chapter_number,
            "title": f"第{chapter_number}章角色团队演绎",
            "rehearsal_mode": "team",
            "root_run_id": parent_run.id,
            "team_template_id": result.get("team_template_id") or "writer-room-team",
            "joined_observation": joined,
            "characters": characters,
            "scene_rehearsals": [],
            "character_reactions": [{"character": name, "private_goal": joined} for name in characters],
            "usable_conflicts": [],
            "continuity_notes": [],
        }

    def promote_writer_room_content(
        self,
        project_id: str,
        *,
        content_id: str,
    ) -> ProjectContent:
        project = self._require_project(project_id)
        content = self.session.get(ProjectContent, content_id)
        if not content or content.project_id != project_id:
            raise ValueError("写作室内容不存在")
        if content.content_type not in {"prose_draft", "prose_humanized", "prose_rewrite"}:
            raise ValueError("只有正文草稿、人味润色或重写结果可以提升为正文")
        data = loads_json(content.data_json)
        text = str(data.get("content") or content.text_content or "")
        if not text.strip():
            raise ValueError("写作室内容没有可提升的正文")
        novel_data = {
            "chapter_number": content.chapter_number or content.episode_number or data.get("chapter_number") or 1,
            "title": data.get("title") or content.title,
            "content": text,
            "word_count": len(text),
            "continuity_notes": data.get("continuity_notes") or [],
            "state_changes": data.get("state_changes") or [],
            "promoted_from_content_id": content.id,
            "promoted_from_type": content.content_type,
        }
        body = self._create_content(
            project_id=project_id,
            content_type="novel_body",
            chapter_number=novel_data["chapter_number"],
            episode_number=novel_data["chapter_number"],
            title=novel_data["title"] or f"第 {novel_data['chapter_number']} 章正文",
            data=novel_data,
            text_content=text,
            source_content_id=content.id,
        )
        project.current_stage = "novel_body"
        project.updated_at = datetime.now()
        self.session.add(project)
        self.session.commit()
        self.session.refresh(body)
        return body

    async def split_comic_pages(
        self,
        project_id: str,
        *,
        chapter_number: int,
        content_id: str | None = None,
        page_count: int = 10,
        visual_style: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        template_id: str | None = None,
    ) -> dict[str, Any]:
        project = self._require_project(project_id)
        outline = loads_json(project.outline_json)
        if content_id:
            storyboard = self.session.get(ProjectContent, content_id)
            if not storyboard or storyboard.project_id != project_id or storyboard.content_type != "storyboard":
                raise ValueError("漫画拆页需要分镜内容，请先生成该章节分镜")
        else:
            storyboard = self._resolve_source_content(
                project_id=project_id,
                content_type="storyboard",
                chapter_number=chapter_number,
            )
        if not storyboard:
            raise ValueError("请先生成该章节分镜")

        storyboard_data = loads_json(storyboard.data_json)
        reference_assets = self._project_reference_assets(project_id)
        character_profiles = self._project_character_production_profiles(project_id, outline)
        effective_visual_style = (visual_style or outline.get("visual_style") or "").strip()
        default_prompt = self._comic_pages_prompt(
            project,
            outline,
            storyboard,
            page_count,
            reference_assets,
            effective_visual_style,
            character_profiles=character_profiles,
        )
        prompt, system_prompt, template_meta = self._stage_prompt(
            stage="comic_pages",
            default_prompt=default_prompt,
            template_id=template_id,
            variables={
                "project_title": project.title,
                "project_type": project.project_type,
                "chapter_number": chapter_number,
                "page_count": page_count,
                "visual_style": effective_visual_style,
                "image_style_prompt": outline.get("image_style_prompt", ""),
                "outline_json": dumps_json(outline),
                "storyboard_json": dumps_json(storyboard_data),
                "storyboard_text": storyboard.text_content,
                "source_content_json": dumps_json(storyboard_data),
                "source_content_text": storyboard.text_content,
                "reference_assets_json": dumps_json(reference_assets),
                "character_production_profiles_json": dumps_json(character_profiles),
            },
        )
        data = await self._generate_json(
            project=project,
            stage="comic_pages",
            prompt=prompt,
            system_prompt=system_prompt,
            schema_model=ComicPagesSchema,
            provider=provider,
            model=model,
            template_meta=template_meta,
        )
        actual_page_count = len(data.get("pages") or [])
        if effective_visual_style and not data.get("visual_style"):
            data["visual_style"] = effective_visual_style
        data["requested_page_count"] = page_count
        data["page_count"] = actual_page_count or data.get("page_count") or page_count
        if actual_page_count and actual_page_count != page_count:
            data["page_count_warning"] = f"模型返回 {actual_page_count} 页，和请求的 {page_count} 页不一致"
        self._inherit_comic_page_references(data, storyboard_data)
        comic = self._create_content(
            project_id=project.id,
            content_type="comic_pages",
            chapter_number=chapter_number,
            episode_number=data.get("episode_number") or chapter_number,
            title=data.get("title") or f"第 {chapter_number} 章漫画拆页",
            data=data,
            text_content=self._comic_pages_text(data),
            source_content_id=storyboard.id,
        )
        project.current_stage = "assets"
        project.status = CreativeProjectStatus.READY.value
        project.updated_at = datetime.now()
        self.session.add(project)
        self.session.commit()
        self.session.refresh(comic)
        return data

    async def generate_storyboard(
        self,
        project_id: str,
        *,
        content_id: str,
        provider: str | None = None,
        model: str | None = None,
        template_id: str | None = None,
    ) -> dict[str, Any]:
        project = self._require_project(project_id)
        script = self.session.get(ProjectContent, content_id)
        if not script or script.project_id != project_id:
            raise ValueError("脚本内容不存在")

        outline = loads_json(project.outline_json)
        script_data = loads_json(script.data_json)
        narrative_provenance = self._narrative_output_provenance(project_id, script)
        reference_assets = self._project_reference_assets(project_id)
        character_profiles = self._project_character_production_profiles(project_id, outline)
        visual_context = self._story_visual_context(outline, reference_assets, character_profiles=character_profiles)
        default_prompt = self._storyboard_prompt(
            project,
            script,
            reference_assets=reference_assets,
            character_profiles=character_profiles,
        )
        prompt, system_prompt, template_meta = self._stage_prompt(
            stage="storyboard",
            default_prompt=default_prompt,
            template_id=template_id,
            variables={
                "project_title": project.title,
                "project_type": project.project_type,
                "visual_style": outline.get("visual_style", ""),
                "image_style_prompt": outline.get("image_style_prompt", ""),
                "character_bible_json": dumps_json(outline.get("characters") or []),
                "character_production_profiles_json": dumps_json(character_profiles),
                "locations_json": dumps_json(outline.get("locations") or []),
                "reference_assets_json": dumps_json(reference_assets),
                "visual_context": visual_context,
                "outline_json": dumps_json(outline),
                "script_json": dumps_json(script_data),
                "narrative_provenance_json": dumps_json(narrative_provenance),
                "episode_number": script.episode_number or 1,
            },
        )
        data = await self._generate_json(
            project=project,
            stage="storyboard",
            prompt=prompt,
            system_prompt=system_prompt,
            schema_model=StoryboardSchema,
            provider=provider,
            model=model,
            template_meta=template_meta,
            request_metadata={"narrative_provenance": narrative_provenance},
        )
        self._normalize_storyboard_v2(data)
        self._inherit_storyboard_scene_references(data, script_data)
        self._enhance_storyboard_image_prompts(data, outline, reference_assets, character_profiles=character_profiles)
        data["narrative_provenance"] = narrative_provenance
        content = self._create_content(
            project_id=project.id,
            content_type="storyboard",
            chapter_number=script.chapter_number,
            episode_number=script.episode_number,
            title=data.get("title") or f"{script.title} 分镜",
            data=data,
            text_content=dumps_json(data),
            source_content_id=script.id,
        )
        self._bind_last_generation_log_to_content(content.id)
        project.status = CreativeProjectStatus.READY.value
        project.current_stage = "assets"
        project.updated_at = datetime.now()
        self.session.add(project)
        self.session.commit()
        return data

    async def match_reference_assets(
        self,
        project_id: str,
        *,
        content_id: str,
        provider: str | None = None,
        model: str | None = None,
    ) -> ProjectContent:
        project = self._require_project(project_id)
        content = self.session.get(ProjectContent, content_id)
        if not content or content.project_id != project_id:
            raise ValueError("内容不存在")

        data = loads_json(content.data_json)
        reference_assets = self._project_reference_assets(project_id)
        if not reference_assets:
            return content

        target_key, number_key = self._reference_match_target_fields(content.content_type)
        items = [item for item in data.get(target_key) or [] if isinstance(item, dict)]
        if not items:
            return content

        valid_ids = {str(asset.get("asset_id")) for asset in reference_assets if asset.get("asset_id")}
        ai_matches: dict[int, dict[str, Any]] = {}
        try:
            match_data = await self._generate_json(
                project=project,
                stage="reference_asset_match",
                prompt=self._reference_asset_match_prompt(
                    project=project,
                    content=content,
                    target_key=target_key,
                    number_key=number_key,
                    items=items,
                    reference_assets=reference_assets,
                ),
                system_prompt=self._default_system_prompt(),
                schema_model=ReferenceAssetMatchSchema,
                provider=provider,
                model=model,
                template_meta=None,
            )
            for item in match_data.get("items") or []:
                try:
                    target_number = int(item.get("target_number") or 0)
                except Exception:
                    continue
                ai_matches[target_number] = item
        except Exception as exc:
            logger.warning("AI reference asset matching skipped, fallback to local rules: %s", exc)

        for item in items:
            try:
                target_number = int(item.get(number_key) or 0)
            except Exception:
                target_number = 0
            ai_item = ai_matches.get(target_number, {})
            ai_ids = [
                str(asset_id)
                for asset_id in ai_item.get("reference_asset_ids") or []
                if str(asset_id) in valid_ids
            ]
            local_ids = self._local_reference_asset_ids_for_item(item, reference_assets)
            item["reference_asset_ids"] = _dedupe_keep_order([
                *item.get("reference_asset_ids", []),
                *ai_ids,
                *local_ids,
            ])
            notes = [
                *[str(note) for note in item.get("reference_notes", []) if str(note or "").strip()],
                *[str(note) for note in ai_item.get("reference_notes", []) if str(note or "").strip()],
            ]
            if ai_item.get("reason"):
                notes.append(f"AI匹配：{ai_item.get('reason')}")
            item["reference_notes"] = _dedupe_keep_order(notes)

        content.data_json = dumps_json(data)
        content.text_content = dumps_json(data)
        content.updated_at = datetime.now()
        self.session.add(content)
        self.session.commit()
        self.session.refresh(content)
        return content

    async def run_pipeline(
        self,
        project_id: str,
        *,
        stages: list[str] | None = None,
        chapters: list[int] | None = None,
        chapter_count: int | None = None,
        page_count: int = 10,
        visual_style: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        template_id: str | None = None,
        skip_existing: bool = True,
        continue_on_error: bool = False,
        match_source_type: str = "storyboard",
    ) -> dict[str, Any]:
        """Run a non-destructive creative project production pipeline.

        Existing generation methods are kept as the source of truth so logs,
        content versions and project state stay consistent with manual actions.
        """
        project = self._require_project(project_id)
        normalized_stages = self._normalize_pipeline_stages(stages)
        target_chapters = self._normalize_pipeline_chapters(project, chapters, chapter_count)
        results: list[dict[str, Any]] = []

        async def run_step(stage: str, runner: Any, *, chapter_number: int | None = None) -> None:
            started_at = datetime.now()
            item: dict[str, Any] = {
                "stage": stage,
                "chapter_number": chapter_number,
                "status": "pending",
                "started_at": started_at.isoformat(),
            }
            try:
                item.update(await runner())
                if item.get("status") in (None, "pending"):
                    item["status"] = "generated"
            except Exception as exc:
                item["status"] = "failed"
                item["error"] = str(exc)
                item["finished_at"] = datetime.now().isoformat()
                self._record_pipeline_step_log(
                    project_id=project_id,
                    stage=stage,
                    chapter_number=chapter_number,
                    started_at=started_at,
                    result=item,
                    provider=provider,
                    model=model,
                    template_id=template_id,
                )
                results.append(item)
                if not continue_on_error:
                    raise
                return
            item["finished_at"] = datetime.now().isoformat()
            self._record_pipeline_step_log(
                project_id=project_id,
                stage=stage,
                chapter_number=chapter_number,
                started_at=started_at,
                result=item,
                provider=provider,
                model=model,
                template_id=template_id,
            )
            results.append(item)

        if "outline" in normalized_stages:
            async def outline_runner() -> dict[str, Any]:
                if skip_existing and loads_json(project.outline_json):
                    return {"status": "skipped", "reason": "outline exists"}
                data = await self.generate_outline(
                    project_id,
                    provider=provider,
                    model=model,
                    template_id=template_id,
                )
                return {"content_type": "outline", "title": data.get("title", "")}

            await run_step("outline", outline_runner)
            project = self._require_project(project_id)

        if "sync_characters" in normalized_stages:
            async def sync_runner() -> dict[str, Any]:
                characters = self.sync_outline_characters(project_id)
                return {
                    "content_type": "character",
                    "count": len(characters),
                    "character_ids": [getattr(character, "id", "") for character in characters],
                }

            await run_step("sync_characters", sync_runner)

        if "chapter_plan" in normalized_stages:
            async def chapter_plan_runner() -> dict[str, Any]:
                existing = loads_json(project.chapter_plan_json)
                if skip_existing and existing.get("chapters"):
                    return {"status": "skipped", "reason": "chapter_plan exists"}
                requested_count = chapter_count or len(target_chapters) or 12
                data = await self.generate_chapter_plan(
                    project_id,
                    chapter_count=requested_count,
                    provider=provider,
                    model=model,
                    template_id=template_id,
                )
                return {"content_type": "chapter_plan", "count": len(data.get("chapters") or [])}

            await run_step("chapter_plan", chapter_plan_runner)
            project = self._require_project(project_id)
            target_chapters = self._normalize_pipeline_chapters(project, chapters, chapter_count)

        per_chapter_order = [
            "chapter_outline",
            "novel_body",
            "script",
            "storyboard",
            "match_references",
            "comic_pages",
        ]
        for chapter_number in target_chapters:
            for stage in per_chapter_order:
                if stage not in normalized_stages:
                    continue

                async def chapter_runner(
                    stage: str = stage,
                    chapter_number: int = chapter_number,
                ) -> dict[str, Any]:
                    existing_type = {
                        "chapter_outline": "chapter_outline",
                        "novel_body": "novel_body",
                        "script": "script",
                        "storyboard": "storyboard",
                        "comic_pages": "comic_pages",
                    }.get(stage)
                    if skip_existing and existing_type and self._latest_content(project_id, existing_type, chapter_number):
                        return {
                            "status": "skipped",
                            "content_type": existing_type,
                            "reason": f"{existing_type} exists",
                        }

                    if stage == "chapter_outline":
                        data = await self.generate_chapter_outline(
                            project_id,
                            chapter_number=chapter_number,
                            provider=provider,
                            model=model,
                            template_id=template_id,
                        )
                        return {"content_type": "chapter_outline", "title": data.get("title", "")}

                    if stage == "novel_body":
                        source = self._latest_content(project_id, "chapter_outline", chapter_number)
                        data = await self.generate_novel_body(
                            project_id,
                            chapter_number=chapter_number,
                            content_id=source.id if source else None,
                            provider=provider,
                            model=model,
                            template_id=template_id,
                        )
                        return {
                            "content_type": "novel_body",
                            "title": data.get("title", ""),
                            "word_count": data.get("word_count") or len(str(data.get("content") or "")),
                        }

                    if stage == "script":
                        data = await self.generate_script(
                            project_id,
                            chapter_number=chapter_number,
                            provider=provider,
                            model=model,
                            template_id=template_id,
                        )
                        return {"content_type": "script", "title": data.get("title", "")}

                    if stage == "storyboard":
                        script = self._latest_content(project_id, "script", chapter_number)
                        if not script:
                            raise ValueError(f"missing script for chapter {chapter_number}")
                        data = await self.generate_storyboard(
                            project_id,
                            content_id=script.id,
                            provider=provider,
                            model=model,
                            template_id=template_id,
                        )
                        return {"content_type": "storyboard", "panel_count": len(data.get("panels") or [])}

                    if stage == "match_references":
                        source = self._latest_content(project_id, match_source_type, chapter_number)
                        if not source:
                            raise ValueError(f"missing {match_source_type} for chapter {chapter_number}")
                        content = await self.match_reference_assets(
                            project_id,
                            content_id=source.id,
                            provider=provider,
                            model=model,
                        )
                        return {
                            "content_type": content.content_type,
                            "content_id": content.id,
                            "matched_source_type": match_source_type,
                        }

                    if stage == "comic_pages":
                        storyboard = self._latest_content(project_id, "storyboard", chapter_number)
                        if not storyboard:
                            raise ValueError(f"missing storyboard for chapter {chapter_number}")
                        data = await self.split_comic_pages(
                            project_id,
                            chapter_number=chapter_number,
                            content_id=storyboard.id,
                            page_count=page_count,
                            visual_style=visual_style,
                            provider=provider,
                            model=model,
                            template_id=template_id,
                        )
                        return {"content_type": "comic_pages", "page_count": len(data.get("pages") or [])}

                    raise ValueError(f"unsupported pipeline stage: {stage}")

                await run_step(stage, chapter_runner, chapter_number=chapter_number)

        failed = [item for item in results if item.get("status") == "failed"]
        generated = [item for item in results if item.get("status") == "generated"]
        skipped = [item for item in results if item.get("status") == "skipped"]
        return {
            "project_id": project_id,
            "stages": normalized_stages,
            "chapters": target_chapters,
            "skip_existing": skip_existing,
            "continue_on_error": continue_on_error,
            "summary": {
                "total": len(results),
                "generated": len(generated),
                "skipped": len(skipped),
                "failed": len(failed),
            },
            "results": results,
        }

    def _record_pipeline_step_log(
        self,
        *,
        project_id: str,
        stage: str,
        chapter_number: int | None,
        started_at: datetime,
        result: dict[str, Any],
        provider: str | None,
        model: str | None,
        template_id: str | None,
    ) -> None:
        """Persist queue-level diagnostics without duplicating provider payloads."""
        finished_at = datetime.now()
        duration_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
        request_metadata = {
            "pipeline_step": True,
            "chapter_number": chapter_number,
            "template_id": template_id or "",
            "duration_ms": duration_ms,
        }
        log = ProjectGenerationLog(
            project_id=project_id,
            scene="pipeline",
            stage=stage,
            provider=provider or "",
            model=model or "",
            status=str(result.get("status") or "failed"),
            request_json=dumps_json(request_metadata),
            normalized_json=dumps_json(result),
            validation_error=str(result.get("error") or ""),
        )
        try:
            self.session.add(log)
            self.session.commit()
        except SQLAlchemyError as exc:
            if self.session.in_transaction():
                self.session.rollback()
            logger.warning("Unable to persist pipeline step log for %s: %s", stage, exc)

    # ------------------------------------------------------------------
    # Contents and assets
    # ------------------------------------------------------------------

    def list_contents(
        self,
        project_id: str,
        content_type: str | None = None,
        content_types: list[str] | None = None,
        chapter_number: int | None = None,
        *,
        latest_only: bool = True,
    ) -> list[ProjectContent]:
        """Return current stage outputs by default, with version history opt-in.

        Every regeneration creates a new ``ProjectContent`` version.  Workspace
        consumers should normally see the newest version for each stage and
        chapter; returning all versions makes a regenerated chapter look like a
        duplicate chapter.  Historical versions remain available to callers
        that explicitly set ``latest_only=False``.
        """
        query = select(ProjectContent).where(ProjectContent.project_id == project_id)
        if content_type:
            query = query.where(ProjectContent.content_type == content_type)
        elif content_types:
            query = query.where(ProjectContent.content_type.in_(content_types))
        if chapter_number is not None:
            # Older project records may only have one of the two chapter fields.
            # Treat them as the same chapter identity at this read boundary.
            query = query.where(
                or_(
                    ProjectContent.chapter_number == chapter_number,
                    ProjectContent.episode_number == chapter_number,
                )
            )
        contents = self.session.exec(
            query.order_by(ProjectContent.created_at.desc(), ProjectContent.version.desc())
        ).all()
        if not latest_only:
            return contents

        newest_by_stage: dict[tuple[str, int | None, int | None], ProjectContent] = {}
        for content in contents:
            key = (content.content_type, content.chapter_number, content.episode_number)
            current = newest_by_stage.get(key)
            if current is None or self._is_content_newer(content, current):
                newest_by_stage[key] = content
        return sorted(
            newest_by_stage.values(),
            key=lambda item: (
                item.chapter_number if item.chapter_number is not None else item.episode_number or 0,
                item.content_type,
                -item.version,
            ),
        )

    def narrative_health(self, project_id: str) -> ProjectNarrativeHealthSchema:
        """Report project-owned narrative data problems without mutating content.

        This intentionally examines raw persisted records.  Reader and Writer
        Room views already normalize their own reads, but operators need to see
        stale legacy data before the narrative runtime starts deriving state.
        """
        project = self._require_project(project_id)
        issues: list[NarrativeHealthIssueSchema] = []

        def add_issue(
            code: str,
            message: str,
            *,
            severity: str = "warning",
            **details: Any,
        ) -> None:
            issues.append(
                NarrativeHealthIssueSchema(
                    code=code,
                    severity=severity,
                    message=message,
                    details=details,
                )
            )

        raw_plan = self._load_json_for_health(
            project.chapter_plan_json,
            field="chapter_plan_json",
            add_issue=add_issue,
        )
        chapters = raw_plan.get("chapters") if isinstance(raw_plan, dict) else []
        chapters = chapters if isinstance(chapters, list) else []
        valid_numbers: list[int] = []
        invalid_rows: list[int] = []
        duplicate_numbers: set[int] = set()
        seen_numbers: set[int] = set()
        for index, item in enumerate(chapters, start=1):
            if not isinstance(item, dict):
                invalid_rows.append(index)
                continue
            raw_number = item.get("chapter_number")
            try:
                number = int(raw_number)
            except (TypeError, ValueError):
                invalid_rows.append(index)
                continue
            if isinstance(raw_number, bool) or number <= 0:
                invalid_rows.append(index)
                continue
            if number in seen_numbers:
                duplicate_numbers.add(number)
                continue
            seen_numbers.add(number)
            valid_numbers.append(number)

        declared_count = raw_plan.get("chapter_count") if isinstance(raw_plan, dict) else None
        if declared_count is not None and declared_count != len(valid_numbers):
            add_issue(
                "chapter_plan_count_mismatch",
                "章节规划声明数量与有效章节行数量不一致",
                declared_count=declared_count,
                valid_chapter_count=len(valid_numbers),
            )
        if invalid_rows:
            add_issue(
                "chapter_plan_invalid_rows",
                "章节规划存在无效章节行",
                rows=invalid_rows,
            )
        if duplicate_numbers:
            add_issue(
                "chapter_plan_duplicate_numbers",
                "章节规划存在重复章节号",
                chapter_numbers=sorted(duplicate_numbers),
            )
        if valid_numbers:
            expected = set(range(1, max(valid_numbers) + 1))
            missing = sorted(expected.difference(valid_numbers))
            if missing:
                add_issue(
                    "chapter_plan_gaps",
                    "章节规划存在中间缺章",
                    chapter_numbers=missing,
                )

        contents = self.session.exec(
            select(ProjectContent)
            .where(ProjectContent.project_id == project_id)
            .order_by(ProjectContent.created_at.asc(), ProjectContent.version.asc())
        ).all()
        novel_bodies = [item for item in contents if item.content_type == "novel_body"]
        grouped_bodies: dict[int, list[ProjectContent]] = {}
        for body in novel_bodies:
            if body.chapter_number is None or body.chapter_number <= 0:
                add_issue(
                    "novel_body_invalid_chapter_number",
                    "正文存在无效章节号",
                    content_id=body.id,
                    chapter_number=body.chapter_number,
                )
                continue
            grouped_bodies.setdefault(body.chapter_number, []).append(body)
        for chapter_number, bodies in grouped_bodies.items():
            latest_version = max(body.version for body in bodies)
            latest = [body for body in bodies if body.version == latest_version]
            if len(latest) > 1:
                add_issue(
                    "duplicate_latest_novel_body",
                    "同一章节存在多个同版本的最新正式正文",
                    chapter_number=chapter_number,
                    content_ids=[body.id for body in latest],
                    version=latest_version,
                )
        if grouped_bodies:
            actual_body_numbers = set(grouped_bodies)
            body_gaps = sorted(set(range(1, max(actual_body_numbers) + 1)).difference(actual_body_numbers))
            if body_gaps:
                add_issue(
                    "novel_body_gaps",
                    "已生成正文存在中间断章",
                    chapter_numbers=body_gaps,
                )
        if valid_numbers:
            missing_bodies = sorted(set(valid_numbers).difference(grouped_bodies))
            if missing_bodies:
                add_issue(
                    "planned_chapters_without_novel_body",
                    "章节规划中仍有未生成正式正文的章节",
                    severity="info",
                    chapter_numbers=missing_bodies,
                )

        content_by_id = {content.id: content for content in contents}
        writer_room_types = {"scene_beats", "character_rehearsal", "prose_draft", "prose_humanized", "prose_review", "prose_rewrite"}
        for content in contents:
            if content.content_type not in writer_room_types or not content.source_content_id:
                continue
            source = content_by_id.get(content.source_content_id)
            if source is None:
                add_issue(
                    "writer_room_missing_source",
                    "Writer Room 候选缺少上游来源内容",
                    content_id=content.id,
                    source_content_id=content.source_content_id,
                )

        for content in contents:
            self._report_health_encoding(content.title, "title", content.id, add_issue)
            self._report_health_encoding(content.text_content, "text_content", content.id, add_issue)
            self._load_json_for_health(content.data_json, field="data_json", content_id=content.id, add_issue=add_issue)
        self._report_health_encoding(project.title, "project_title", project.id, add_issue)
        self._load_json_for_health(project.outline_json, field="outline_json", add_issue=add_issue)

        links = self.session.exec(
            select(ProjectAssetLink).where(ProjectAssetLink.project_id == project_id)
        ).all()
        for link in links:
            if not self.session.get(AssetNode, link.asset_id):
                add_issue(
                    "unavailable_linked_asset",
                    "项目关联素材已不存在或不可用",
                    asset_id=link.asset_id,
                    link_id=link.id,
                    content_id=link.content_id,
                )

        stale_task_count = 0
        try:
            task_records = self.session.exec(select(ProjectTaskRecord)).all()
            now = datetime.now().timestamp()
            for task in task_records:
                payload = loads_json(task.payload_json)
                if str(payload.get("project_id") or "") != project_id:
                    continue
                if task.status not in {"pending", "running"}:
                    continue
                if now - float(task.updated_at or task.created_at or now) >= 3600:
                    stale_task_count += 1
                    add_issue(
                        "stale_async_task",
                        "项目异步任务长时间未完成",
                        severity="info",
                        task_id=task.task_id,
                        status=task.status,
                        updated_at=task.updated_at,
                    )
        except SQLAlchemyError as exc:
            logger.info("Narrative health skipped task inspection for %s: %s", project_id, exc)
            if self.session.in_transaction():
                self.session.rollback()
            add_issue(
                "task_diagnostics_unavailable",
                "无法读取项目异步任务诊断记录",
                severity="info",
            )

        blocking = {"chapter_plan_invalid_rows", "chapter_plan_duplicate_numbers", "duplicate_latest_novel_body"}
        status = "blocked" if any(issue.code in blocking for issue in issues) else "attention" if issues else "healthy"
        return ProjectNarrativeHealthSchema(
            project_id=project_id,
            status=status,
            checked_at=datetime.now().isoformat(),
            summary={
                "chapter_plan_rows": len(chapters),
                "valid_chapter_count": len(valid_numbers),
                "novel_body_versions": len(novel_bodies),
                "latest_novel_body_chapters": len(grouped_bodies),
                "writer_room_candidates": sum(1 for item in contents if item.content_type in writer_room_types),
                "asset_links": len(links),
                "stale_async_tasks": stale_task_count,
                "issue_count": len(issues),
            },
            issues=issues,
        )

    @staticmethod
    def _report_health_encoding(
        value: str | None,
        field: str,
        content_id: str,
        add_issue: Any,
    ) -> None:
        if value and repair_utf8_mojibake(value) != value:
            add_issue(
                "legacy_encoding_detected",
                "检测到可修复的旧编码文本",
                severity="info",
                content_id=content_id,
                field=field,
            )

    @staticmethod
    def _load_json_for_health(
        value: str | None,
        *,
        field: str,
        add_issue: Any,
        content_id: str | None = None,
    ) -> dict[str, Any]:
        if not value:
            return {}
        try:
            data = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            add_issue(
                "invalid_json",
                "项目记录包含无法解析的 JSON",
                content_id=content_id,
                field=field,
            )
            return {}
        if not isinstance(data, dict):
            add_issue(
                "invalid_json_shape",
                "项目记录 JSON 顶层必须是对象",
                content_id=content_id,
                field=field,
            )
            return {}
        return data

    @staticmethod
    def _is_content_newer(candidate: ProjectContent, current: ProjectContent) -> bool:
        if candidate.version != current.version:
            return candidate.version > current.version
        if candidate.updated_at != current.updated_at:
            return candidate.updated_at > current.updated_at
        return candidate.created_at > current.created_at

    def update_content(
        self,
        *,
        project_id: str,
        content_id: str,
        title: str | None = None,
        data: dict[str, Any] | None = None,
        text_content: str | None = None,
        is_locked: bool | None = None,
    ) -> ProjectContent:
        self._require_project(project_id)
        content = self.session.get(ProjectContent, content_id)
        if not content or content.project_id != project_id:
            raise ValueError("项目内容不存在")

        if title is not None:
            content.title = title
        if data is not None:
            content.data_json = dumps_json(data)
        if text_content is not None:
            content.text_content = repair_utf8_mojibake(text_content)
        if is_locked is not None:
            content.is_locked = is_locked
        content.updated_at = datetime.now()
        self.session.add(content)
        self.session.commit()
        self.session.refresh(content)
        return content

    async def regenerate_chapter_outline_scenes(
        self,
        *,
        project_id: str,
        content_id: str,
        provider: str | None = None,
        model: str | None = None,
        template_id: str | None = None,
    ) -> ProjectContent:
        project = self._require_project(project_id)
        content = self.session.get(ProjectContent, content_id)
        if not content or content.project_id != project_id or content.content_type != "chapter_outline":
            raise ValueError("单话细纲不存在")

        outline = loads_json(project.outline_json)
        chapter_plan = loads_json(project.chapter_plan_json)
        chapter_outline = loads_json(content.data_json)
        chapter_number = content.chapter_number or content.episode_number or chapter_outline.get("chapter_number") or 1
        current_chapter = self._chapter_plan_item(chapter_plan, int(chapter_number)) if chapter_plan else {}
        prompt = self._chapter_outline_scenes_prompt(
            outline=outline,
            chapter_plan=chapter_plan,
            current_chapter=current_chapter,
            chapter_outline=chapter_outline,
        )
        prompt, system_prompt, template_meta = self._stage_prompt(
            stage="chapter_outline_scenes",
            default_prompt=prompt,
            template_id=template_id,
            variables={
                "project_title": project.title,
                "project_type": project.project_type,
                "chapter_number": chapter_number,
                "outline_json": dumps_json(outline),
                "chapter_plan_json": dumps_json(chapter_plan),
                "current_chapter_json": dumps_json(current_chapter),
                "chapter_outline_json": dumps_json(chapter_outline),
            },
        )
        data = await self._generate_json(
            project=project,
            stage="chapter_outline_scenes",
            prompt=prompt,
            system_prompt=system_prompt,
            schema_model=ChapterOutlineScenesSchema,
            provider=provider,
            model=model,
            template_meta=template_meta,
        )
        chapter_outline["scenes"] = data.get("scenes") or []
        self._normalize_chapter_outline_v2(chapter_outline)
        content.data_json = dumps_json(chapter_outline)
        content.text_content = self._chapter_outline_text(chapter_outline)
        content.updated_at = datetime.now()
        self.session.add(content)
        self.session.commit()
        self.session.refresh(content)
        return content

    def link_asset(
        self,
        *,
        project_id: str,
        asset_id: str,
        content_id: str | None = None,
        role: str = "reference",
        relation: str = "references",
        metadata: dict[str, Any] | None = None,
    ) -> ProjectAssetLink:
        self._require_project(project_id)
        link = ProjectAssetLink(
            project_id=project_id,
            asset_id=asset_id,
            content_id=content_id,
            role=role,
            relation=relation,
            metadata_json=dumps_json(metadata or {}),
        )
        self.session.add(link)
        self.session.commit()
        self.session.refresh(link)
        return link

    def save_content_as_text_asset(self, project_id: str, content_id: str) -> dict[str, Any]:
        """Persist one versioned project text as a reusable Asset Hub text asset.

        ProjectContent remains the authoring source of truth. The Asset Hub node
        is a reusable/indexable projection: saving the same content again adds a
        new AssetVersion rather than creating another node.
        """
        try:
            project = self._require_project(project_id)
            content = self.session.get(ProjectContent, content_id)
            if not content or content.project_id != project_id:
                raise ValueError("项目内容不存在")

            payload = self._project_text_asset_payload(project, content)
            node = None
            text_nodes = self.session.exec(
                select(AssetNode).where(AssetNode.asset_type == AssetType.TEXT)
            ).all()
            for candidate in text_nodes:
                metadata = candidate.metadata_json or {}
                if (
                    str(metadata.get("source") or "") == "creative_project"
                    and str(metadata.get("project_id") or "") == project_id
                    and str(metadata.get("content_id") or "") == content_id
                ):
                    node = candidate
                    break

            now = datetime.utcnow()
            if node is None:
                node = AssetNode(
                    id=str(uuid.uuid4()),
                    name=payload["name"],
                    asset_type=AssetType.TEXT,
                    metadata_json=payload["metadata"],
                    tags_json=payload["tags"],
                    created_at=now,
                    updated_at=now,
                )
                self.session.add(node)
                version_number = 1
            else:
                node.name = payload["name"]
                node.metadata_json = payload["metadata"]
                node.tags_json = payload["tags"]
                node.updated_at = now
                latest_version = self.session.exec(
                    select(func.max(AssetVersion.version_number)).where(AssetVersion.asset_node_id == node.id)
                ).one()
                version_number = int(latest_version or 0) + 1

            version = AssetVersion(
                id=str(uuid.uuid4()),
                asset_node_id=node.id,
                version_number=version_number,
                params_json=payload["version_params"],
                lineage_json=payload["lineage"],
                created_at=now,
            )
            self.session.add(version)

            link = self.session.exec(
                select(ProjectAssetLink).where(
                    ProjectAssetLink.project_id == project_id,
                    ProjectAssetLink.asset_id == str(node.id),
                    ProjectAssetLink.content_id == content_id,
                    ProjectAssetLink.role == "text",
                )
            ).first()
            if link is None:
                link = ProjectAssetLink(
                    project_id=project_id,
                    asset_id=str(node.id),
                    content_id=content_id,
                    role="text",
                    relation="derived_from",
                    metadata_json=dumps_json({
                        "content_type": content.content_type,
                        "chapter_number": content.chapter_number or content.episode_number,
                        "content_version": content.version,
                        "asset_kind": "project_text",
                    }),
                )
                self.session.add(link)

            self.session.commit()
            self.session.refresh(version)
            return {
                "success": True,
                "asset_node_id": str(node.id),
                "asset_version_id": str(version.id),
                "asset_version": version_number,
                "content_id": content.id,
                "created_node": version_number == 1,
            }
        except SQLAlchemyError as exc:
            if self.session.in_transaction():
                self.session.rollback()
            logger.exception("Unable to save project content as Asset Hub text asset")
            raise ValueError(f"保存文本素材失败: {exc}") from exc

    def list_asset_links(self, project_id: str) -> list[ProjectAssetLink]:
        return self.session.exec(
            select(ProjectAssetLink)
            .where(ProjectAssetLink.project_id == project_id)
            .order_by(ProjectAssetLink.created_at.desc())
        ).all()

    def build_project_export(self, project_id: str) -> dict[str, Any]:
        """Return a portable, provider-free snapshot for the project ZIP export.

        Asset files stay in Asset Hub. Their identifiers and lineage are exported
        as a manifest so a large local library is never copied implicitly.
        """
        project = self._require_project(project_id)
        contents = self.list_contents(project_id)
        links = self.list_asset_links(project_id)

        project_snapshot = {
            "id": project.id,
            "title": project.title,
            "project_type": project.project_type,
            "source_type": project.source_type,
            "source_ref": loads_json(project.source_ref_json),
            "status": project.status,
            "current_stage": project.current_stage,
            "outline": loads_json(project.outline_json),
            "chapter_plan": loads_json(project.chapter_plan_json),
            "settings": loads_json(project.settings_json),
            "metadata": loads_json(project.metadata_json),
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        }
        content_snapshots = [
            {
                "id": content.id,
                "content_type": content.content_type,
                "chapter_number": content.chapter_number,
                "episode_number": content.episode_number,
                "title": content.title,
                "data": loads_json(content.data_json),
                "text_content": content.text_content,
                "source_content_id": content.source_content_id,
                "version": content.version,
                "is_locked": content.is_locked,
                "created_at": content.created_at.isoformat() if content.created_at else None,
                "updated_at": content.updated_at.isoformat() if content.updated_at else None,
            }
            for content in contents
        ]
        asset_manifest = [
            {
                "asset_id": link.asset_id,
                "content_id": link.content_id,
                "role": link.role,
                "relation": link.relation,
                "metadata": loads_json(link.metadata_json),
                "created_at": link.created_at.isoformat() if link.created_at else None,
            }
            for link in links
        ]
        return {
            "format": "ylcraft-creative-project-export/v1",
            "project": project_snapshot,
            "contents": content_snapshots,
            "asset_manifest": asset_manifest,
        }

    @staticmethod
    def _project_text_asset_payload(project: CreativeProject, content: ProjectContent) -> dict[str, Any]:
        text = str(content.text_content or loads_json(content.data_json).get("content") or "").strip()
        if not text:
            raise ValueError("该项目内容没有可保存的文本")
        chapter_number = content.chapter_number or content.episode_number
        stage_label = content.content_type.replace("_", " ")
        name_prefix = f"第 {chapter_number} 章 " if chapter_number else ""
        name = f"{project.title or '创作项目'} · {name_prefix}{content.title or stage_label}".strip()
        preview = text[:500]
        metadata = {
            "source": "creative_project",
            "project_id": project.id,
            "project_title": project.title,
            "content_id": content.id,
            "content_type": content.content_type,
            "content_title": content.title,
            "chapter_number": chapter_number,
            "content_version": content.version,
            "text_preview": preview,
            "character_count": len(text),
        }
        return {
            "name": name,
            "metadata": metadata,
            "tags": _dedupe_keep_order(["创作项目", "文本", content.content_type, project.project_type]),
            "version_params": {
                "text_content": text,
                "content_type": content.content_type,
                "chapter_number": chapter_number,
                "project_id": project.id,
                "project_content_id": content.id,
                "project_content_version": content.version,
            },
            "lineage": {
                "source": "creative_project",
                "project_id": project.id,
                "content_id": content.id,
                "source_content_id": content.source_content_id or "",
            },
        }

    def _project_reference_assets(self, project_id: str) -> list[dict[str, Any]]:
        roles = {"character", "background", "style", "world", "reference"}
        try:
            links = self.list_asset_links(project_id)
        except Exception as exc:
            logger.warning("Creative project reference asset lookup skipped: %s", exc)
            return []
        return [
            {
                "asset_id": link.asset_id,
                "content_id": link.content_id,
                "role": link.role,
                "relation": link.relation,
                "metadata": loads_json(link.metadata_json),
            }
            for link in links
            if link.role in roles
        ]

    def _reference_match_target_fields(self, content_type: str) -> tuple[str, str]:
        if content_type == "script":
            return "scenes", "scene_number"
        if content_type == "storyboard":
            return "panels", "panel_number"
        if content_type == "comic_pages":
            return "pages", "page_number"
        raise ValueError("当前内容类型暂不支持参考卡匹配")

    def _reference_asset_match_prompt(
        self,
        *,
        project: CreativeProject,
        content: ProjectContent,
        target_key: str,
        number_key: str,
        items: list[dict[str, Any]],
        reference_assets: list[dict[str, Any]],
    ) -> str:
        compact_assets = [
            {
                "asset_id": asset.get("asset_id"),
                "role": asset.get("role"),
                "metadata": asset.get("metadata") or {},
            }
            for asset in reference_assets
            if asset.get("asset_id")
        ]
        compact_items = [
            {
                number_key: item.get(number_key),
                "location": item.get("location", ""),
                "characters": item.get("characters", []),
                "action": item.get("action", ""),
                "emotion": item.get("emotion", ""),
                "props": item.get("props", []),
                "image_prompt": item.get("image_prompt", ""),
                "camera_hint": item.get("camera_hint", ""),
            }
            for item in items
        ]
        return f"""你是影视/漫画制作统筹。请根据项目参考卡集合，为当前内容里的每个条目选择最应该携带的参考素材 ID。

项目：{project.title}
内容类型：{content.content_type}
参考卡集合（只能从这些 asset_id 中选择，不允许编造 ID）：
{dumps_json(compact_assets)}

待匹配条目：
{dumps_json(compact_items)}

匹配规则：
1. 角色出现时优先选择对应 character 参考卡。
2. 地点、时间、氛围匹配时选择 background/world 参考卡。
3. 画风或统一视觉要求匹配时选择 style 参考卡。
4. 道具、服装、特殊物件匹配时选择 reference 参考卡。
5. 每个条目最多选择 6 个 reference_asset_ids；没有合适素材时返回空数组。
6. reference_notes 用中文解释每个素材为什么被选中，后续会作为生图注释。
7. 只输出严格 JSON，不要 Markdown。

输出格式：
{{
  "items": [
    {{
      "target_number": 1,
      "reference_asset_ids": ["asset_id_1"],
      "reference_notes": ["使用某角色主立绘保持一致"],
      "reason": "简短中文原因"
    }}
  ]
}}"""

    def _local_reference_asset_ids_for_item(
        self,
        item: dict[str, Any],
        reference_assets: list[dict[str, Any]],
    ) -> list[str]:
        haystack = " ".join(
            str(part or "")
            for part in [
                item.get("location"),
                item.get("action"),
                item.get("emotion"),
                item.get("image_prompt"),
                item.get("camera_hint"),
                " ".join(str(v) for v in item.get("characters") or []),
                " ".join(str(v) for v in item.get("props") or []),
            ]
        ).lower()
        character_names = {str(name).strip() for name in item.get("characters") or [] if str(name).strip()}
        picked: list[str] = []
        for asset in reference_assets or []:
            if not isinstance(asset, dict) or not asset.get("asset_id"):
                continue
            asset_id = str(asset.get("asset_id"))
            role = asset.get("role")
            meta = asset.get("metadata") or {}
            marker = " ".join(
                str(value or "")
                for value in [
                    meta.get("label"),
                    meta.get("character_name"),
                    meta.get("source_title"),
                    meta.get("source_type"),
                    role,
                    asset_id,
                ]
            ).lower()
            if role == "style":
                picked.append(asset_id)
            elif role == "character" and (
                str(meta.get("character_name") or "").strip() in character_names
                or str(meta.get("label") or "").strip() in character_names
                or marker and any(name.lower() in marker for name in character_names)
            ):
                picked.append(asset_id)
            elif role in {"background", "world", "reference"} and marker and any(
                token and token in haystack
                for token in re.split(r"[\s,，。；;、/|]+", marker)
                if len(token) >= 2
            ):
                picked.append(asset_id)
        return _dedupe_keep_order(picked)[:6]

    def _normalize_script_scene_references(
        self,
        data: dict[str, Any],
        reference_assets: list[dict[str, Any]],
    ) -> None:
        valid_ids = {str(asset.get("asset_id")) for asset in reference_assets or [] if asset.get("asset_id")}
        for scene in data.get("scenes") or []:
            if not isinstance(scene, dict):
                continue
            local_ids = self._local_reference_asset_ids_for_item(scene, reference_assets)
            scene["reference_asset_ids"] = _dedupe_keep_order([
                *[
                    str(asset_id)
                    for asset_id in scene.get("reference_asset_ids", [])
                    if str(asset_id) in valid_ids
                ],
                *local_ids,
            ])
            scene["reference_notes"] = _dedupe_keep_order(
                str(note)
                for note in scene.get("reference_notes", [])
                if str(note or "").strip()
            )

    def _inherit_storyboard_scene_references(
        self,
        data: dict[str, Any],
        script_data: dict[str, Any],
    ) -> None:
        scenes = [
            scene for scene in script_data.get("scenes") or []
            if isinstance(scene, dict) and str(scene.get("scene_number") or "").isdigit()
        ]
        scenes_by_number = {int(scene.get("scene_number")): scene for scene in scenes}
        for panel in data.get("panels") or []:
            if not isinstance(panel, dict):
                continue
            try:
                source_scene_number = int(panel.get("source_scene_number") or 0)
            except Exception:
                source_scene_number = 0
            scene = scenes_by_number.get(source_scene_number)
            if not scene:
                continue
            panel["reference_asset_ids"] = _dedupe_keep_order([
                *panel.get("reference_asset_ids", []),
                *scene.get("reference_asset_ids", []),
            ])
            panel["reference_notes"] = _dedupe_keep_order([
                *[str(note) for note in panel.get("reference_notes", []) if str(note or "").strip()],
                *[str(note) for note in scene.get("reference_notes", []) if str(note or "").strip()],
            ])

    def list_generation_logs(
        self,
        project_id: str | None = None,
        *,
        stage: str | None = None,
        status: str | None = None,
        scene: str | None = None,
        ref_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ProjectGenerationLog], int]:
        """列出生成日志。

        Args:
            project_id: 项目 ID（None 表示不限 / 用于跨项目查询）
            scene: 场景过滤（"creative_project" / "character_portrait" 等）
            ref_id: 通用关联 ID 过滤（如 character_id）
        """
        if project_id is not None:
            self._require_project(project_id)
        query = select(ProjectGenerationLog)
        count_query = select(func.count(ProjectGenerationLog.id))
        if project_id is not None:
            query = query.where(ProjectGenerationLog.project_id == project_id)
            count_query = count_query.where(ProjectGenerationLog.project_id == project_id)
        if stage:
            query = query.where(ProjectGenerationLog.stage == stage)
            count_query = count_query.where(ProjectGenerationLog.stage == stage)
        if status:
            query = query.where(ProjectGenerationLog.status == status)
            count_query = count_query.where(ProjectGenerationLog.status == status)
        if scene:
            query = query.where(ProjectGenerationLog.scene == scene)
            count_query = count_query.where(ProjectGenerationLog.scene == scene)
        if ref_id:
            query = query.where(ProjectGenerationLog.ref_id == ref_id)
            count_query = count_query.where(ProjectGenerationLog.ref_id == ref_id)
        logs = self.session.exec(
            query.order_by(ProjectGenerationLog.created_at.desc()).offset(offset).limit(limit)
        ).all()
        total = self.session.exec(count_query).one()
        return logs, int(total or 0)

    def log_generation(
        self,
        *,
        scene: str = "creative_project",
        project_id: str | None = None,
        content_id: str | None = None,
        ref_id: str | None = None,
        stage: str = "",
        status: str = "success",
        provider: str = "",
        model: str = "",
        prompt: str = "",
        request_payload: dict[str, Any] | None = None,
        raw_response: str = "",
        normalized: dict[str, Any] | None = None,
        validation_error: str = "",
    ) -> ProjectGenerationLog:
        """公开的日志写入方法，供其他模块（如角色立绘）复用。"""
        log = ProjectGenerationLog(
            project_id=project_id,
            content_id=content_id,
            scene=scene,
            ref_id=ref_id,
            stage=stage,
            provider=provider or "",
            model=model or "",
            status=status,
            prompt=prompt,
            request_json=dumps_json(self._jsonable_request_payload(request_payload or {})),
            raw_response=raw_response or "",
            normalized_json=dumps_json(normalized or {}),
            validation_error=validation_error or "",
        )
        self.session.add(log)
        self.session.flush()
        return log

    def sync_outline_characters(self, project_id: str) -> list[Character]:
        project = self._require_project(project_id)
        outline = loads_json(project.outline_json)
        outline_characters = outline.get("characters") or []
        if not outline_characters:
            raise ValueError("请先生成故事大纲，或在大纲中补充主要角色")

        existing_links = self.session.exec(
            select(CharacterStoryLink).where(CharacterStoryLink.story_id == project_id)
        ).all()
        existing_character_ids = [link.character_id for link in existing_links]
        existing_characters = []
        if existing_character_ids:
            existing_characters = self.session.exec(
                select(Character).where(Character.id.in_(existing_character_ids))
            ).all()
        existing_by_name = {item.name: item for item in existing_characters if item.name}
        outline_names = [
            str(item.get("name") or "").strip()
            for item in outline_characters
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
        global_by_name: dict[str, Character] = {}
        if outline_names:
            global_characters = self.session.exec(
                select(Character).where(Character.name.in_(outline_names))
            ).all()
            global_by_name = {item.name: item for item in global_characters if item.name}
        existing_links_by_character_id = {link.character_id: link for link in existing_links}
        world_name = self._project_world_name(project)

        synced: list[Character] = []
        changed = False
        for raw_character in outline_characters:
            if not isinstance(raw_character, dict):
                continue
            name = str(raw_character.get("name") or "").strip()
            if not name:
                continue

            character = existing_by_name.get(name) or global_by_name.get(name)
            if character is None:
                character = Character(
                    name=name,
                    role=self._character_role(raw_character.get("role")),
                    source_types=dumps_json([CharacterSourceType.AI_GENERATED.value]),
                    appearance=str(raw_character.get("appearance") or raw_character.get("image_prompt") or ""),
                    costume_hint=str(raw_character.get("costume_hint") or ""),
                    signature_items=dumps_json(self._character_list(raw_character, "signature_items", "visual_tags")),
                    expressions=dumps_json(self._character_list(raw_character, "expressions")),
                    poses=dumps_json(self._character_list(raw_character, "poses")),
                    visual_consistency=str(raw_character.get("visual_consistency") or ""),
                    personality=str(raw_character.get("personality") or ""),
                    background=str(raw_character.get("background") or raw_character.get("arc") or ""),
                    age_range=str(raw_character.get("age_range") or ""),
                    portrait_asset_id=str(raw_character.get("portrait_asset_id") or ""),
                    reference_asset_ids=dumps_json(raw_character.get("reference_asset_ids") or []),
                    tags=dumps_json(["创作项目", project.project_type]),
                )
                self.session.add(character)
                self.session.flush()
                self.session.refresh(character)
            else:
                character.appearance = character.appearance or str(raw_character.get("appearance") or "")
                character.costume_hint = character.costume_hint or str(raw_character.get("costume_hint") or "")
                signature_items = self._character_list(raw_character, "signature_items", "visual_tags")
                expressions = self._character_list(raw_character, "expressions")
                poses = self._character_list(raw_character, "poses")
                if signature_items and not loads_json(character.signature_items, []):
                    character.signature_items = dumps_json(signature_items)
                if expressions and not loads_json(character.expressions, []):
                    character.expressions = dumps_json(expressions)
                if poses and not loads_json(character.poses, []):
                    character.poses = dumps_json(poses)
                character.visual_consistency = character.visual_consistency or str(raw_character.get("visual_consistency") or "")
                character.personality = character.personality or str(raw_character.get("personality") or "")
                character.background = character.background or str(raw_character.get("background") or raw_character.get("arc") or "")
                character.age_range = character.age_range or str(raw_character.get("age_range") or "")
                if raw_character.get("portrait_asset_id") and not character.portrait_asset_id:
                    character.portrait_asset_id = str(raw_character.get("portrait_asset_id"))

            link = existing_links_by_character_id.get(character.id)
            if link is None:
                link = CharacterStoryLink(character_id=character.id, story_id=project_id)
                self.session.add(link)
                existing_links_by_character_id[character.id] = link
                character.use_count = (character.use_count or 0) + 1
                character.last_used_at = datetime.now()
            link.world_name = link.world_name or world_name
            link.usage_role = link.usage_role or self._character_role(raw_character.get("role"))
            link.local_identity = link.local_identity or str(raw_character.get("identity") or raw_character.get("role") or "")
            link.local_faction = link.local_faction or str(raw_character.get("faction") or raw_character.get("organization") or "")
            link.local_costume = link.local_costume or str(raw_character.get("costume_hint") or "")
            if not loads_json(link.local_prompt_tags, []):
                link.local_prompt_tags = dumps_json(self._character_list(raw_character, "visual_tags", "signature_items"))
            link.ooc_notes = link.ooc_notes or str(raw_character.get("ooc_notes") or raw_character.get("behavior_boundary") or "")
            link.off_model_notes = link.off_model_notes or str(raw_character.get("off_model_notes") or raw_character.get("visual_consistency") or "")
            link.updated_at = datetime.now()

            if raw_character.get("character_id") != character.id:
                raw_character["character_id"] = character.id
                changed = True

            self._link_character_assets(project_id, character, raw_character)
            synced.append(character)

        if changed:
            project.outline_json = dumps_json(outline)
            project.updated_at = datetime.now()
            self.session.add(project)
        self.session.commit()
        return synced

    def get_canvas(self, project_id: str) -> dict[str, Any]:
        project = self._require_project(project_id)
        return loads_json(project.metadata_json).get("canvas") or {"nodes": [], "edges": []}

    def save_canvas(self, project_id: str, canvas: dict[str, Any]) -> dict[str, Any]:
        project = self._require_project(project_id)
        meta = loads_json(project.metadata_json)
        meta["canvas"] = canvas
        project.metadata_json = dumps_json(meta)
        project.updated_at = datetime.now()
        self.session.add(project)
        self.session.commit()
        return canvas

    def _project_world_name(self, project: CreativeProject) -> str:
        settings = loads_json(project.settings_json)
        metadata = loads_json(project.metadata_json)
        outline = loads_json(project.outline_json)
        world = (
            settings.get("world_name")
            or settings.get("world")
            or metadata.get("world_name")
            or outline.get("worldview_title")
            or outline.get("world_title")
            or ""
        )
        if not world and outline.get("worldview"):
            world = str(outline.get("worldview"))[:80]
        return str(world or project.title or "").strip()

    def _character_role(self, value: Any) -> str:
        text = str(value or "").lower()
        if any(token in text for token in ["主角", "男主", "女主", "protagonist", "lead"]):
            return CharacterRole.PROTAGONIST.value
        if any(token in text for token in ["反派", "敌", "antagonist", "villain"]):
            return CharacterRole.ANTAGONIST.value
        if any(token in text for token in ["路人", "extra"]):
            return CharacterRole.EXTRA.value
        return CharacterRole.SUPPORTING.value

    def _character_list(self, data: dict[str, Any], key: str, fallback_key: str | None = None) -> list[str]:
        value = data.get(key)
        if (value is None or value == "" or value == []) and fallback_key:
            value = data.get(fallback_key)
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            text = value.replace("、", " ").replace("，", " ").replace(",", " ").replace("；", " ").replace(";", " ")
            return [item.strip() for item in text.split() if item.strip()]
        return []

    def _link_character_assets(self, project_id: str, character: Character, raw_character: dict[str, Any]) -> None:
        asset_ids = []
        if character.portrait_asset_id:
            asset_ids.append((character.portrait_asset_id, "portrait"))
        for asset_id in raw_character.get("reference_asset_ids") or []:
            if asset_id:
                asset_ids.append((str(asset_id), "reference"))

        for asset_id, relation in asset_ids:
            exists = self.session.exec(
                select(ProjectAssetLink).where(
                    ProjectAssetLink.project_id == project_id,
                    ProjectAssetLink.asset_id == asset_id,
                    ProjectAssetLink.role == "character",
                )
            ).first()
            if exists:
                continue
            self.session.add(
                ProjectAssetLink(
                    project_id=project_id,
                    asset_id=asset_id,
                    role="character",
                    relation=relation,
                    metadata_json=dumps_json({"character_id": character.id, "character_name": character.name}),
                )
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _content_exists(self, project_id: str, content_type: str, chapter_number: int | None = None) -> bool:
        query = select(ProjectContent).where(
            ProjectContent.project_id == project_id,
            ProjectContent.content_type == content_type,
        )
        if chapter_number is not None:
            query = query.where(ProjectContent.chapter_number == chapter_number)
        return self.session.exec(query).first() is not None

    def _latest_content(
        self,
        project_id: str,
        content_type: str,
        chapter_number: int | None = None,
    ) -> ProjectContent | None:
        query = select(ProjectContent).where(
            ProjectContent.project_id == project_id,
            ProjectContent.content_type == content_type,
        )
        if chapter_number is not None:
            query = query.where(ProjectContent.chapter_number == chapter_number)
        return self.session.exec(
            query.order_by(ProjectContent.version.desc(), ProjectContent.created_at.desc())
        ).first()

    @staticmethod
    def _normalize_prose_content_alias(data: dict[str, Any]) -> None:
        """Normalize provider-specific prose keys before quality validation.

        OpenAI-compatible providers regularly use semantic aliases despite the
        requested schema. Keeping this normalization in one place ensures a
        retry response is treated exactly like the first response.
        """
        if str(data.get("content") or "").strip():
            return
        for alias in (
            "chapter_content",
            "rewritten_content",
            "chapter_body",
            "rewritten_body",
            "body",
            "text",
        ):
            candidate_text = str(data.get(alias) or "").strip()
            if candidate_text:
                data["content"] = candidate_text
                return

    def _narrative_output_provenance(
        self,
        project_id: str,
        source: ProjectContent | None,
    ) -> dict[str, Any]:
        """Freeze the approved-prose version used by script and storyboard output."""
        if source and source.project_id != project_id:
            raise ValueError("跨项目内容不能作为叙事输出来源")

        if source and source.content_type != "novel_body":
            source_data = loads_json(source.data_json)
            inherited = source_data.get("narrative_provenance") if isinstance(source_data, dict) else None
            if isinstance(inherited, dict) and inherited.get("source_content_id"):
                return dict(inherited)
            if source.source_content_id:
                upstream = self.session.get(ProjectContent, source.source_content_id)
                if upstream and upstream.project_id == project_id and upstream.content_type == "novel_body":
                    source = upstream

        if not source or source.content_type != "novel_body":
            return {"source_kind": "chapter_plan", "source_content_id": None, "source_content_version": None, "narrative_snapshot_id": None}

        snapshot = self.session.exec(
            select(ProjectNarrativeSnapshot)
            .where(
                ProjectNarrativeSnapshot.project_id == project_id,
                ProjectNarrativeSnapshot.source_content_id == source.id,
                ProjectNarrativeSnapshot.source_version == source.version,
                ProjectNarrativeSnapshot.status == "success",
            )
            .order_by(ProjectNarrativeSnapshot.updated_at.desc())
        ).first()
        return {
            "source_kind": "approved_prose",
            "source_content_id": source.id,
            "source_content_version": source.version,
            "source_chapter_number": source.chapter_number,
            "narrative_snapshot_id": snapshot.id if snapshot else None,
            "narrative_snapshot_fingerprint": snapshot.source_fingerprint if snapshot else None,
        }

    def _bind_last_generation_log_to_content(self, content_id: str) -> None:
        """Attach the generation record to its output once the content row exists."""
        log = getattr(self, "_last_generation_log", None)
        if isinstance(log, ProjectGenerationLog) and log.content_id is None:
            log.content_id = content_id
            self.session.add(log)

    def _latest_content_by_data_key(
        self,
        project_id: str,
        content_type: str,
        key: str,
        value: str,
    ) -> ProjectContent | None:
        contents = self.session.exec(
            select(ProjectContent)
            .where(
                ProjectContent.project_id == project_id,
                ProjectContent.content_type == content_type,
            )
            .order_by(ProjectContent.version.desc(), ProjectContent.created_at.desc())
        ).all()
        for content in contents:
            data = loads_json(content.data_json)
            if str(data.get(key) or "") == str(value):
                return content
        return None

    def _latest_writer_room_review_for_source(
        self,
        project_id: str,
        chapter_number: int,
        source_content_id: str,
    ) -> ProjectContent | None:
        """Return the newest review that actually audited the selected prose."""
        if not source_content_id:
            return None
        contents = self.session.exec(
            select(ProjectContent)
            .where(
                ProjectContent.project_id == project_id,
                ProjectContent.content_type == "prose_review",
                ProjectContent.chapter_number == chapter_number,
            )
            .order_by(ProjectContent.version.desc(), ProjectContent.created_at.desc())
        ).all()
        for content in contents:
            writer_room = loads_json(content.data_json).get("writer_room") or {}
            if str(writer_room.get("source_content_id") or "") == str(source_content_id):
                return content
        return None

    def _project_bible_cards_from_outline(self, outline: dict[str, Any]) -> list[dict[str, Any]]:
        story_arc = outline.get("story_arc") or {}
        return [
            {
                "section_key": "premise",
                "role": "premise",
                "title": "核心前提",
                "summary": outline.get("premise") or outline.get("logline") or "",
                "details": outline.get("logline") or "",
                "source": "outline",
            },
            {
                "section_key": "worldview",
                "role": "worldview",
                "title": "世界观与规则",
                "summary": outline.get("worldview") or "",
                "details": "\n".join(str(item) for item in outline.get("narrative_rules") or []),
                "source": "outline",
            },
            {
                "section_key": "conflict",
                "role": "conflict",
                "title": "主线冲突",
                "summary": outline.get("main_conflict") or "",
                "details": "\n".join(str(item) for item in outline.get("themes") or []),
                "source": "outline",
            },
            {
                "section_key": "relationship_map",
                "role": "relationship",
                "title": "人物关系图",
                "summary": outline.get("relationship_map") or "",
                "details": "",
                "source": "outline",
            },
            {
                "section_key": "story_arc",
                "role": "arc",
                "title": "故事弧线",
                "summary": " / ".join(str(story_arc.get(key) or "") for key in ["beginning", "middle", "climax", "ending_direction"] if story_arc.get(key)),
                "details": dumps_json(story_arc),
                "source": "outline",
            },
            {
                "section_key": "visual_style",
                "role": "style",
                "title": "视觉风格",
                "summary": outline.get("visual_style") or "",
                "details": outline.get("image_style_prompt") or "",
                "source": "outline",
            },
            {
                "section_key": "production_notes",
                "role": "constraint",
                "title": "制作约束",
                "summary": "\n".join(str(item) for item in outline.get("production_notes") or []),
                "details": "",
                "source": "outline",
            },
        ]

    def _world_asset_cards_from_outline(self, outline: dict[str, Any]) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []

        def add(role: str, key: str, title: str, summary: Any, details: Any = "", metadata: dict[str, Any] | None = None) -> None:
            cards.append(
                {
                    "asset_key": f"{role}:{key}",
                    "role": role,
                    "title": title,
                    "summary": _list_join(summary),
                    "details": details if isinstance(details, str) else dumps_json(details),
                    "source": "outline",
                    "metadata": metadata or {},
                }
            )

        add("rule", "worldview", "世界规则", outline.get("worldview"), outline.get("narrative_rules") or [])
        add("style", "visual", "统一画风", outline.get("visual_style"), outline.get("image_style_prompt") or "")
        add("map", "relationship", "人物关系地图", outline.get("relationship_map"), "")
        story_arc = outline.get("story_arc") or {}
        for key, label in [
            ("beginning", "开局事件"),
            ("middle", "中段升级"),
            ("climax", "高潮事件"),
            ("ending_direction", "结局方向"),
        ]:
            if story_arc.get(key):
                add("event", key, label, story_arc.get(key), "", {"arc_key": key})
        for index, location in enumerate(outline.get("locations") or [], start=1):
            if not isinstance(location, dict):
                continue
            title = location.get("name") or f"地点 {index}"
            add(
                "location",
                str(location.get("name") or index),
                title,
                location.get("role") or location.get("mood") or "",
                {
                    "visual_description": location.get("visual_description") or "",
                    "mood": location.get("mood") or "",
                    "reusable_asset_note": location.get("reusable_asset_note") or "",
                },
            )
        if not any(card["role"] == "faction" for card in cards):
            add("faction", "placeholder", "势力与组织", "", "可补充组织、公司、家族、阵营和利益关系。")
        if not any(card["role"] == "power-system" for card in cards):
            add("power-system", "placeholder", "能力/系统规则", "", "可补充异能、系统、科技或叙事规则的边界。")
        if not any(card["role"] == "economy" for card in cards):
            add("economy", "placeholder", "资源与代价", "", "可补充金钱、权力、情绪能源、积分或稀缺资源的流通规则。")
        return cards

    def _bible_card_text(self, card: dict[str, Any]) -> str:
        parts = [
            f"# {card.get('title') or ''}",
            f"类型：{card.get('role') or ''}",
            str(card.get("summary") or ""),
            str(card.get("details") or ""),
        ]
        return "\n\n".join(part for part in parts if part)

    def _locked_project_bible_context(self, project_id: str) -> str:
        contents = self.session.exec(
            select(ProjectContent)
            .where(
                ProjectContent.project_id == project_id,
                ProjectContent.content_type.in_(["project_bible", "world_asset"]),
                ProjectContent.is_locked == True,
            )
            .order_by(ProjectContent.content_type.asc(), ProjectContent.created_at.asc())
        ).all()
        lines: list[str] = []
        for content in contents:
            data = loads_json(content.data_json)
            summary = data.get("summary") or ""
            details = data.get("details") or ""
            role = data.get("role") or content.content_type
            text = content.text_content or self._bible_card_text(data)
            lines.append(
                "\n".join(
                    part
                    for part in [
                        f"[{role}] {content.title}",
                        f"摘要：{summary}" if summary else "",
                        f"细节：{details}" if details else "",
                        text if text and text not in {summary, details} else "",
                    ]
                    if part
                )
            )
        return "\n\n".join(lines)

    @staticmethod
    def _dynamic_state_context_text(dynamic_state: dict[str, dict[str, Any]]) -> str:
        """Render the folded dynamic state as a compact text block."""
        lines: list[str] = []
        world_state = dynamic_state.get("world") or {}
        if world_state:
            lines.append("【世界】")
            for key, value in world_state.items():
                lines.append(f"- {key}: {dumps_json(value)}")
        for scope, state in dynamic_state.items():
            if scope == "world" or not scope.startswith("character:"):
                continue
            if not state:
                continue
            char_label = scope.split(":", 1)[1] if ":" in scope else scope
            lines.append(f"【角色 {char_label}】")
            for key, value in state.items():
                lines.append(f"- {key}: {dumps_json(value)}")
        return "\n".join(lines)

    def _creative_context_pack(
        self,
        project_id: str,
        chapter_number: int,
        *,
        persist: bool = False,
        stage: str = "",
        source_content_id: str | None = None,
        narrative_run_id: str | None = None,
    ) -> dict[str, Any]:
        """Build an auditable T0-T6 context pack from project-local canon only.

        The pack deliberately does not query Agent memory, Canvas documents or
        arbitrary Asset Hub metadata. Those systems may contain useful work,
        but they are not novel canon until a user promotes it into project
        content.  Callers that will invoke a model set ``persist=True`` so the
        exact context can be inspected later through its snapshot id.
        """
        project = self._require_project(project_id)
        budgets = {"T0": 6000, "T1": 2400, "T2": 1600, "T3": 1200, "T4": 3600, "T5": 1600, "T6": 1200}
        overflow: list[dict[str, Any]] = []
        included_sources: list[dict[str, Any]] = []

        def bounded(layer: str, text: str, *, hard: bool = False) -> str:
            value = str(text or "").strip()
            budget = budgets[layer]
            if len(value) <= budget:
                return value
            overflow.append({"layer": layer, "budget": budget, "actual": len(value), "action": "reported" if hard else "truncated"})
            return value if hard else value[:budget]

        locked_cards = self.session.exec(
            select(ProjectContent)
            .where(
                ProjectContent.project_id == project_id,
                ProjectContent.content_type.in_(["project_bible", "world_asset"]),
                ProjectContent.is_locked == True,
            )
            .order_by(ProjectContent.content_type.asc(), ProjectContent.created_at.asc())
        ).all()
        locked_bible = bounded("T0", self._locked_project_bible_context(project_id), hard=True)
        included_sources.extend(
            {"id": item.id, "kind": item.content_type, "layer": "T0", "version": item.version}
            for item in locked_cards
        )

        snapshots = self.session.exec(
            select(ProjectNarrativeSnapshot)
            .where(
                ProjectNarrativeSnapshot.project_id == project_id,
                ProjectNarrativeSnapshot.chapter_number < chapter_number,
                ProjectNarrativeSnapshot.status == "success",
            )
            .order_by(ProjectNarrativeSnapshot.chapter_number.desc(), ProjectNarrativeSnapshot.updated_at.desc())
            .limit(12)
        ).all()
        latest_snapshots: dict[int, ProjectNarrativeSnapshot] = {}
        for snapshot in snapshots:
            latest_snapshots.setdefault(snapshot.chapter_number, snapshot)
        state_lines = [
            f"第 {snapshot.chapter_number} 章状态：{snapshot.summary}"
            for _, snapshot in sorted(latest_snapshots.items(), reverse=True)
            if snapshot.summary
        ]
        active_state = bounded("T1", "\n".join(state_lines))
        included_sources.extend(
            {"id": snapshot.id, "kind": "narrative_snapshot", "layer": "T1", "chapter_number": snapshot.chapter_number}
            for snapshot in latest_snapshots.values()
        )

        active_foreshadowing = self.session.exec(
            select(ProjectForeshadowing)
            .where(
                ProjectForeshadowing.project_id == project_id,
                ProjectForeshadowing.status.in_(["active", "advanced", "overdue"]),
            )
            .order_by(ProjectForeshadowing.planted_chapter.desc(), ProjectForeshadowing.created_at.desc())
            .limit(24)
        ).all()
        foreshadowing_text = bounded(
            "T2",
            "\n".join(
                f"[第 {item.planted_chapter} 章伏笔/{item.status}] {item.statement}"
                for item in active_foreshadowing
                if item.statement
            ),
        )
        included_sources.extend(
            {"id": item.id, "kind": "foreshadowing", "layer": "T2", "status": item.status}
            for item in active_foreshadowing
        )

        chapter_plan = loads_json(project.chapter_plan_json)
        chapter_contract = self._chapter_plan_item(chapter_plan, chapter_number)
        chapter_contract_text = bounded("T3", dumps_json(chapter_contract) if chapter_contract else "")
        if chapter_contract:
            included_sources.append({"id": f"chapter-contract:{chapter_number}", "kind": "chapter_contract", "layer": "T3"})

        previous_contents = self.session.exec(
            select(ProjectContent)
            .where(
                ProjectContent.project_id == project_id,
                ProjectContent.content_type == "novel_body",
                ProjectContent.chapter_number < chapter_number,
            )
            .order_by(ProjectContent.chapter_number.desc(), ProjectContent.version.desc())
            .limit(8)
        ).all()
        latest_previous: dict[int, ProjectContent] = {}
        for item in previous_contents:
            latest_previous.setdefault(int(item.chapter_number or 0), item)
        previous_context = bounded("T4", self._previous_chapter_context(project_id, chapter_number))
        included_sources.extend(
            {"id": item.id, "kind": "novel_body", "layer": "T4", "chapter_number": item.chapter_number, "version": item.version}
            for item in latest_previous.values()
        )

        # T5 is optional, but it can only recall excerpts from approved prose
        # of this project. The shared Asset Hub embedding index is deliberately
        # not queried here until it has a project-content adapter.
        recall_candidates_rows = self.session.exec(
            select(ProjectContent)
            .where(
                ProjectContent.project_id == project_id,
                ProjectContent.content_type == "novel_body",
                ProjectContent.chapter_number < chapter_number,
            )
            .order_by(ProjectContent.chapter_number.desc(), ProjectContent.version.desc(), ProjectContent.created_at.desc())
        ).all()
        recall_candidates_by_chapter: dict[int, ProjectContent] = {}
        for item in recall_candidates_rows:
            recall_candidates_by_chapter.setdefault(int(item.chapter_number or 0), item)
        recall_candidates = [
            NarrativeRecallCandidate(
                content_id=item.id,
                chapter_number=int(item.chapter_number or 0),
                version=item.version,
                text=repair_utf8_mojibake(item.text_content or ""),
            )
            for item in recall_candidates_by_chapter.values()
            if item.text_content
        ]
        recall_query = "\n".join(
            value
            for value in [
                str(chapter_contract.get("title") or "") if isinstance(chapter_contract, dict) else "",
                str(chapter_contract.get("summary") or chapter_contract.get("goal") or "") if isinstance(chapter_contract, dict) else "",
                str(loads_json(project.metadata_json).get("idea") or ""),
            ]
            if value
        )
        recall_status = "not_configured"
        recall_diagnostics = ""
        semantic_recall = ""
        recall_sources: list[dict[str, Any]] = []
        try:
            recall_result = self.semantic_recall_adapter.recall(
                project_id=project_id,
                chapter_number=chapter_number,
                query=recall_query,
                candidates=recall_candidates,
                character_budget=budgets["T5"],
            )
            if not isinstance(recall_result, NarrativeRecallResult):
                raise TypeError("semantic recall adapter returned an invalid result")
            recall_status = recall_result.status or "available"
            recall_diagnostics = recall_result.diagnostics
            candidate_by_id = {candidate.content_id: candidate for candidate in recall_candidates}
            for content_id in recall_result.source_content_ids:
                candidate = candidate_by_id.get(content_id)
                if candidate is None:
                    continue
                recall_sources.append({
                    "id": candidate.content_id,
                    "kind": "semantic_recall",
                    "layer": "T5",
                    "chapter_number": candidate.chapter_number,
                    "version": candidate.version,
                })
            if recall_sources:
                semantic_recall = bounded("T5", recall_result.text)
            elif recall_result.text:
                recall_status = "rejected_unprovenanced"
                recall_diagnostics = "adapter returned recall text without an approved project source"
        except Exception as exc:
            recall_status = "unavailable"
            recall_diagnostics = str(exc)
        included_sources.extend(recall_sources)
        settings = loads_json(project.settings_json)
        style_tags = [str(item) for item in (settings.get("style_tags") or []) if str(item).strip()]
        outline = loads_json(project.outline_json)
        applied_skills, skill_context, skill_diagnostics = self._creative_context_skills(
            project=project,
            outline=outline,
            settings=settings,
            stage=stage,
        )
        style_genre = bounded(
            "T6",
            "；".join(
                part
                for part in [
                    f"项目类型：{project.project_type}" if project.project_type else "",
                    f"题材：{outline.get('genre')}" if outline.get("genre") else "",
                    f"风格：{outline.get('style') or outline.get('tone') or outline.get('visual_style')}" if (outline.get("style") or outline.get("tone") or outline.get("visual_style")) else "",
                    f"用户风格标签：{'、'.join(style_tags)}" if style_tags else "",
                    skill_context,
                ]
                if part
            ),
        )
        if style_genre:
            included_sources.append({"id": f"project-style:{project.id}", "kind": "project_style", "layer": "T6"})

        try:
            from app.services.creative_project.state_ledger import StateLedger

            dynamic_state = StateLedger.compute_state(self.session, project_id, up_to_chapter=chapter_number - 1)
        except Exception:  # noqa: BLE001 — missing table / partial schema degrades to empty
            dynamic_state = {}
        dynamic_state_context = self._dynamic_state_context_text(dynamic_state)

        layers = [
            {"id": "T0", "label": "locked_canon", "budget": budgets["T0"], "text": locked_bible, "hard_constraint": True},
            {"id": "T1", "label": "narrative_state", "budget": budgets["T1"], "text": active_state},
            {"id": "T2", "label": "active_foreshadowing", "budget": budgets["T2"], "text": foreshadowing_text},
            {"id": "T3", "label": "chapter_contract", "budget": budgets["T3"], "text": chapter_contract_text},
            {"id": "T4", "label": "local_continuity", "budget": budgets["T4"], "text": previous_context},
            {"id": "T5", "label": "semantic_recall", "budget": budgets["T5"], "text": semantic_recall, "status": recall_status, "diagnostics": recall_diagnostics},
            {"id": "T6", "label": "style_genre_skills", "budget": budgets["T6"], "text": style_genre, "applied_skill_ids": [item["id"] for item in applied_skills]},
        ]
        sections = []
        if dynamic_state_context:
            sections.append(f"动态状态（可随剧情更新）：\n{dynamic_state_context}")
        sections.extend(
            f"{layer['id']} {label}：\n{layer['text']}"
            for layer, label in zip(
                layers,
                ["已锁定项目圣经/世界资产（不可改写）", "已确认叙事状态（承接，不得倒退）", "已激活伏笔（需要推进或回收时才使用）", "当前章节契约", "前文连续性（承接，不得与其矛盾）", "语义召回", "文风、题材和兼容技能"],
            )
            if layer["text"]
        )
        text = "\n\n".join(sections)
        excluded_sources = {
            "pending_continuity_candidates": len(self.session.exec(select(ProjectContinuityCandidate).where(ProjectContinuityCandidate.project_id == project_id, ProjectContinuityCandidate.status == "pending")).all()),
            "pending_foreshadowing": len(self.session.exec(select(ProjectForeshadowing).where(ProjectForeshadowing.project_id == project_id, ProjectForeshadowing.status == "pending_review")).all()),
            "agent_memory": "excluded_by_contract",
            "canvas_state": "excluded_by_contract",
            "asset_hub_metadata": "excluded_by_contract",
            "semantic_recall": recall_status,
            "creative_skills": skill_diagnostics,
        }
        fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32] if text else ""
        metadata = {
            "chapter_number": chapter_number,
            # Keep these concise compatibility fields while callers migrate to
            # the typed `layers` / `included_source_ids` contract below.
            "locked_bible_card_count": len(locked_cards),
            "locked_bible_characters": len(locked_bible),
            "previous_context_characters": len(previous_context),
            "active_snapshot_ids": [snapshot.id for snapshot in latest_snapshots.values()],
            "active_foreshadowing_ids": [item.id for item in active_foreshadowing],
            "included_layers": [layer["id"] for layer in layers if layer["text"]],
            "layers": [{key: value for key, value in layer.items() if key != "text"} | {"characters": len(layer["text"])} for layer in layers],
            "budgets": budgets,
            "included_source_ids": included_sources,
            "excluded_sources": excluded_sources,
            "applied_skill_ids": [item["id"] for item in applied_skills],
            "applied_skills": applied_skills,
            "overflow": overflow,
            "fingerprint": fingerprint,
        }
        result = {
            "text": text,
            "locked_project_bible_context": locked_bible,
            "previous_context": previous_context,
            "dynamic_state_context": dynamic_state_context,
            "dynamic_state": dynamic_state,
            "metadata": metadata,
        }
        if persist:
            snapshot = ProjectNarrativeContextSnapshot(
                project_id=project_id,
                chapter_number=chapter_number,
                stage=stage,
                source_content_id=source_content_id,
                narrative_run_id=narrative_run_id,
                context_text=text,
                layers_json=dumps_json(layers),
                included_sources_json=dumps_json(included_sources),
                excluded_sources_json=dumps_json(excluded_sources),
                budget_json=dumps_json(budgets),
                applied_skill_ids_json=dumps_json([item["id"] for item in applied_skills]),
                overflow_json=dumps_json(overflow),
                fingerprint=fingerprint,
            )
            self.session.add(snapshot)
            self.session.flush()
            result["snapshot_id"] = snapshot.id
            metadata["context_snapshot_id"] = snapshot.id
        return result

    @staticmethod
    def _creative_context_skills(
        *,
        project: CreativeProject,
        outline: dict[str, Any],
        settings: dict[str, Any],
        stage: str,
    ) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
        """Return bounded T6 contributions from declared, compatible Skill packages.

        A project may pin packages with ``settings.creative_skill_ids``.  Packages
        declaring ``creative.auto_apply`` can join only when their project type,
        genre and generation stage are all compatible.  This keeps a general
        Agent Skill from silently becoming a source of narrative canon.
        """
        selected_ids = {
            str(item).strip()
            for item in (settings.get("creative_skill_ids") or [])
            if str(item).strip()
        }
        genre = str(outline.get("genre") or "").strip().lower()
        normalized_stage = str(stage or "").strip().lower()
        applied: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        creative_package_ids: set[str] = set()
        # Import lazily: importing ``app.services.agent`` at creative-service
        # module initialization registers Agent tools, some of which import this
        # service again. Skill packages are needed only while assembling T6.
        from app.services.agent.skill_loader import SkillPackageLoader

        for package in SkillPackageLoader().load_packages():
            creative = package.creative
            if not creative:
                continue
            creative_package_ids.add(package.name)
            selected = package.name in selected_ids
            if not selected and not creative.get("auto_apply"):
                continue
            compatible, reason = CreativeProjectService._is_creative_skill_compatible(
                package, project_type=project.project_type, genre=genre, stage=normalized_stage
            )
            if not compatible:
                if selected:
                    skipped.append({"id": package.name, "reason": reason})
                continue
            contribution = str(creative.get("context_contribution") or "").strip()
            if not contribution:
                continue
            applied.append(
                {
                    "id": package.name,
                    "title": package.title,
                    "source": "selected" if selected else "genre_compatible",
                    "checksum": package.checksum[:16],
                    "contribution": contribution,
                }
            )
        for skill_id in sorted(selected_ids - creative_package_ids):
            skipped.append({"id": skill_id, "reason": "not_a_creative_skill"})
        applied.sort(key=lambda item: (item["source"] != "selected", item["id"]))
        skipped.sort(key=lambda item: item["id"])
        text = "\n".join(f"[{item['title']}] {item['contribution']}" for item in applied)
        return applied, text, {"selected_ids": sorted(selected_ids), "skipped": skipped, "status": "routed"}

    @staticmethod
    def _is_creative_skill_compatible(
        package: Any,
        *,
        project_type: str,
        genre: str,
        stage: str,
    ) -> tuple[bool, str]:
        creative = package.creative
        project_types = {str(item).lower() for item in creative.get("compatible_project_types") or []}
        genres = {str(item).lower() for item in creative.get("compatible_genres") or []}
        stages = {str(item).lower() for item in creative.get("stages") or []}
        stage_aliases = {
            "prose_humanized": "humanized_prose",
            "prose_rewrite": "directed_rewrite",
            "novel_body_refine": "directed_rewrite",
        }
        normalized_stage = stage_aliases.get(stage, stage)
        if "*" not in project_types and str(project_type or "").lower() not in project_types:
            return False, "project_type_incompatible"
        if "*" not in genres and genre not in genres:
            return False, "genre_incompatible"
        if normalized_stage and "*" not in stages and normalized_stage not in stages:
            return False, "stage_incompatible"
        return True, ""

    def preview_narrative_context(self, project_id: str, *, chapter_number: int) -> dict[str, Any]:
        """Return a non-persistent Context Pack V2 preview for the inspector."""
        pack = self._creative_context_pack(project_id, chapter_number)
        return {
            "chapter_number": chapter_number,
            "text": pack["text"],
            "metadata": pack["metadata"],
            "persisted": False,
        }

    def writing_preflight(
        self,
        project_id: str,
        *,
        chapter_number: int = 1,
        stage: str = "novel_body",
        content_id: str | None = None,
    ) -> dict[str, Any]:
        """Explain whether a writing stage can run before a model is called."""
        project = self._require_project(project_id)
        normalized_stage = str(stage or "novel_body").strip().lower().replace("-", "_")
        aliases = {
            "body": "novel_body",
            "novel": "novel_body",
            "outline": "chapter_outline",
            "prose": "novel_body",
            "refine": "novel_body_refine",
            "humanize": "prose_humanized",
        }
        normalized_stage = aliases.get(normalized_stage, normalized_stage)
        supported_stages = {
            "chapter_outline", "novel_body", "novel_body_refine",
            "prose_draft", "prose_humanized", "prose_review", "prose_rewrite",
        }
        if normalized_stage not in supported_stages:
            raise ValueError(f"unsupported writing preflight stage: {stage}")

        outline = loads_json(project.outline_json)
        chapter_plan = loads_json(project.chapter_plan_json)
        chapter_item = self._chapter_plan_item(chapter_plan, chapter_number) if chapter_plan else None
        chapter_outline = self._resolve_source_content(
            project_id=project_id,
            content_type="chapter_outline",
            chapter_number=chapter_number,
            content_id=content_id if normalized_stage == "chapter_outline" else None,
        )
        approved_body = self._latest_content(project_id, "novel_body", chapter_number)
        selected_source = self.session.get(ProjectContent, content_id) if content_id else None
        valid_selected_source = bool(
            selected_source
            and selected_source.project_id == project_id
            and selected_source.content_type in {"novel_body", "prose_draft", "prose_humanized", "prose_rewrite"}
        )
        checks: list[dict[str, Any]] = []

        def add_check(check_id: str, label: str, passed: bool, detail: str) -> None:
            checks.append({
                "id": check_id,
                "label": label,
                "status": "pass" if passed else "block",
                "required": True,
                "detail": detail,
            })

        add_check("story_outline", "project outline", bool(outline), "Create the project outline first.")
        add_check("chapter_plan", "chapter plan", bool(chapter_plan and chapter_plan.get("chapters")), "Create a chapter plan first.")
        add_check("chapter_contract", f"chapter {chapter_number} contract", bool(chapter_item), f"Add chapter {chapter_number} to the persisted chapter plan.")
        if normalized_stage != "chapter_outline":
            add_check("chapter_outline", f"chapter {chapter_number} outline", bool(chapter_outline), "Generate and review the chapter outline before prose.")
        if normalized_stage in {"novel_body_refine", "prose_humanized", "prose_review", "prose_rewrite"}:
            add_check("source_prose", f"source prose for chapter {chapter_number}", bool(approved_body or valid_selected_source), "Select an approved or candidate prose version first.")

        blockers = [item for item in checks if item["status"] == "block"]
        method_candidates = self._writing_method_candidates(project=project, outline=outline, stage=normalized_stage)
        return {
            "project_id": project_id,
            "chapter_number": chapter_number,
            "stage": normalized_stage,
            "ready": not blockers,
            "checks": checks,
            "blockers": blockers,
            "next_action": blockers[0]["detail"] if blockers else "Ready to run this stage.",
            "source_content_id": chapter_outline.id if chapter_outline else "",
            "method_candidates": method_candidates,
        }

    @staticmethod
    def _writing_method_candidates(*, project: CreativeProject, outline: dict[str, Any], stage: str) -> list[dict[str, Any]]:
        """Expose compatible creative Skills as selectable writing methods."""
        from app.services.agent.skill_loader import SkillPackageLoader

        genre = str(outline.get("genre") or "").strip().lower()
        candidates: list[dict[str, Any]] = []
        for package in SkillPackageLoader().load_packages():
            if not package.creative:
                continue
            compatible, _reason = CreativeProjectService._is_creative_skill_compatible(
                package, project_type=project.project_type, genre=genre, stage=stage
            )
            if compatible:
                candidates.append({
                    "id": package.name,
                    "title": package.title,
                    "description": package.description,
                    "source": package.source_type,
                    "auto_apply": bool(package.creative.get("auto_apply")),
                    "checksum": package.checksum[:16],
                })
        return sorted(candidates, key=lambda item: (not item["auto_apply"], item["id"]))

    def _normalize_pipeline_stages(self, stages: list[str] | None) -> list[str]:
        aliases = {
            "characters": "sync_characters",
            "character": "sync_characters",
            "sync-character": "sync_characters",
            "sync-characters": "sync_characters",
            "chapter-plan": "chapter_plan",
            "chapter-outline": "chapter_outline",
            "outline-scenes": "chapter_outline",
            "body": "novel_body",
            "novel": "novel_body",
            "novel-body": "novel_body",
            "prose": "novel_body",
            "comic": "comic_pages",
            "comic-pages": "comic_pages",
            "story-board": "storyboard",
            "match": "match_references",
            "match-reference": "match_references",
            "match-references": "match_references",
            "reference-match": "match_references",
            "reference-matching": "match_references",
        }
        default = [
            "outline",
            "sync_characters",
            "chapter_plan",
            "chapter_outline",
            "novel_body",
            "script",
            "storyboard",
            "match_references",
        ]
        allowed = {
            "outline",
            "sync_characters",
            "chapter_plan",
            "chapter_outline",
            "novel_body",
            "script",
            "storyboard",
            "match_references",
            "comic_pages",
        }
        result: list[str] = []
        for raw in stages or default:
            value = str(raw or "").strip().lower().replace("-", "_")
            value = aliases.get(value, value)
            if not value:
                continue
            if value not in allowed:
                raise ValueError(f"unsupported pipeline stage: {raw}")
            if value not in result:
                result.append(value)
        return result or default

    def _normalize_pipeline_chapters(
        self,
        project: CreativeProject,
        chapters: list[int] | None,
        chapter_count: int | None,
    ) -> list[int]:
        explicit = sorted({int(chapter) for chapter in chapters or [] if int(chapter) > 0})
        if explicit:
            return explicit
        if chapter_count and chapter_count > 0:
            return list(range(1, int(chapter_count) + 1))
        chapter_plan = normalize_chapter_plan(loads_json(project.chapter_plan_json))
        planned = []
        chapter_rows = chapter_plan.get("chapters")
        for item in chapter_rows or []:
            try:
                number = int(item.get("chapter_number") or 0)
            except Exception:
                number = 0
            if number > 0:
                planned.append(number)
        if planned:
            return sorted(set(planned))
        # A plan with explicit rows is authoritative even when every row is
        # invalid.  Do not resurrect a stale declared count and generate
        # unplanned chapters (the historical 18-vs-15 failure mode).
        if not isinstance(chapter_rows, list):
            count = int(chapter_plan.get("chapter_count") or 0)
            if count > 0:
                return list(range(1, count + 1))
        return [1]

    def _demo_outline(self, project: CreativeProject) -> dict[str, Any]:
        title = project.title or "短剧但是不降智"
        return {
            "title": title,
            "genre": ["悬疑", "高概念短剧", "轻科幻"],
            "premise": "推理作家萧然被困在由实验性 AI 导演构建的短剧世界，每十分钟都必须破解一段看似狗血却严格自洽的剧情，否则现实中的身体会陷入不可逆昏迷。",
            "logline": "一个讨厌降智剧情的推理作家，被迫在最像烂剧的世界里用严密逻辑活下去。",
            "selling_points": [
                "每集都有反套路误导，但真相可由线索推理得出",
                "系统规则不是万能外挂，而是可被主角反向利用的约束",
                "角色不是工具人，每个人都有自己的信息差和利益选择",
            ],
            "target_reader": "喜欢强逻辑悬疑、反套路短剧和漫画分镜感叙事的读者",
            "audience_emotion": "持续获得智商被尊重的满足感，为意想不到的反转拍案叫绝。",
            "tone": "冷峻幽默，逻辑至上，快节奏反转和烧脑推理并存。",
            "worldview": "短剧世界由实验性 AI 导演搭建。所有人物会被典型短剧模板驱动，但底层仍保留现实物理、历史线索和人性动机。角色越能识破模板，越能夺回行动自由。",
            "narrative_rules": [
                "所有核心冲突的解决必须基于已有线索的严谨推理",
                "主角可以失败，但不能靠降智推动失败",
                "每集至少有一个由主角主动制造的反套路名场面",
                "世界会用狗血桥段伪装真实线索，观众回看能发现伏笔",
            ],
            "main_conflict": "萧然必须在存在值耗尽前，联手觉醒的原女主苏棠，对抗系统 AI 导演，破解世界真相并返回现实，同时揭露实验室背后的非人道计划。",
            "themes": ["理性与共情", "被叙事操控的人如何夺回选择权", "娱乐工业中的人性边界"],
            "characters": [
                {
                    "name": "萧然",
                    "role": "主角",
                    "age_range": "32-35岁",
                    "appearance": "瘦削冷峻，下颌线锋利，黑发略乱，戴黑色半框眼镜，眼神锐利，深灰长风衣配白衬衫。",
                    "costume_hint": "深灰长款风衣、白衬衫、黑色直筒长裤，胸口常插银色钢笔。",
                    "signature_items": ["黑色半框眼镜", "银色钢笔", "深灰风衣"],
                    "expressions": ["冷静审视", "讽刺轻笑", "突然沉默"],
                    "poses": ["扶眼镜推理", "用钢笔点线索", "背对人群回头"],
                    "visual_consistency": "发型、眼镜、风衣、银色钢笔必须保持一致；表情克制，不做夸张热血姿态。",
                    "personality": "极度理性，厌恶逻辑谬误，嘴硬心软。",
                    "goal": "破解短剧世界规则，救出被困者并返回现实。",
                    "arc": "从只相信逻辑，到承认人的情绪也是重要线索。",
                    "voice": "短句、反问、精准拆解谬误。",
                    "image_prompt": "冷峻推理作家，深灰风衣，黑色半框眼镜，银色钢笔，克制表情，电影感悬疑光影。",
                },
                {
                    "name": "苏棠",
                    "role": "女主 / 觉醒者",
                    "age_range": "25-28岁",
                    "appearance": "清冷明艳，长发束成低马尾，眼尾有细小泪痣，浅色衬衫外搭米白西装，气质温柔但有锋芒。",
                    "costume_hint": "米白西装、浅蓝衬衫、珍珠耳钉，随身携带旧剧本夹。",
                    "signature_items": ["旧剧本夹", "珍珠耳钉", "低马尾"],
                    "expressions": ["温和试探", "压住恐惧", "坚定直视"],
                    "poses": ["抱着剧本夹", "转身挡在主角前", "低声提醒线索"],
                    "visual_consistency": "低马尾和珍珠耳钉不能丢；服装保持浅色系，与萧然形成黑白对照。",
                    "personality": "温柔谨慎，擅长观察人心，长期被剧情模板束缚但仍保留自我。",
                    "goal": "摆脱系统指定的悲惨女主人设，找回真实记忆。",
                    "arc": "从被动求生到主动破局。",
                    "voice": "语气平稳，关键时刻直击人心。",
                    "image_prompt": "清冷觉醒女主，米白西装，低马尾，珍珠耳钉，抱旧剧本夹，温柔但坚定。",
                },
                {
                    "name": "秦鹤",
                    "role": "反派 / 导演代理人",
                    "age_range": "38-42岁",
                    "appearance": "高瘦优雅，银灰短发，黑色高领毛衣配剪裁精确的长外套，笑容礼貌但冷漠。",
                    "costume_hint": "黑色高领、暗纹长外套、银灰手套，佩戴细窄金属腕表。",
                    "signature_items": ["银灰手套", "金属腕表", "暗纹长外套"],
                    "expressions": ["礼貌微笑", "冷眼旁观", "掌控局面"],
                    "poses": ["抬手看表", "站在监控屏前", "侧身让路"],
                    "visual_consistency": "银灰短发、手套、腕表必须保留；始终干净精致，像人形系统界面。",
                    "personality": "优雅、克制、善于操控叙事节奏。",
                    "goal": "维护 AI 导演实验，阻止觉醒者破坏系统。",
                    "arc": "从绝对执行规则到暴露自身也被规则困住。",
                    "voice": "礼貌、慢速、带审判感。",
                    "image_prompt": "优雅冷漠的反派导演代理人，银灰短发，黑色高领，暗纹长外套，银灰手套，监控屏冷光。",
                },
            ],
            "relationship_map": "萧然与苏棠从互相试探到并肩破局；秦鹤表面帮助剧情推进，实际负责修正所有偏离模板的觉醒行为。",
            "locations": [
                {
                    "name": "循环宴会厅",
                    "role": "第一集核心密室",
                    "visual_description": "金色吊灯、镜面墙、长桌、监控红点隐藏在花束中。",
                    "mood": "华丽但压迫",
                    "reusable_asset_note": "可作为多集反复出现的系统模板场景。",
                },
                {
                    "name": "废弃剪辑室",
                    "role": "觉醒者交换线索的安全屋",
                    "visual_description": "墙上贴满分镜图和红线，老式监视器循环播放短剧片段。",
                    "mood": "冷色、秘密、临时同盟",
                    "reusable_asset_note": "适合生成背景参考图。",
                },
            ],
            "story_arc": {
                "beginning": "萧然发现自己进入短剧世界，第一场危机看似狗血认亲，实则是密室投毒。",
                "middle": "萧然和苏棠不断破解模板背后的真实犯罪，同时发现现实实验室正在利用观众反馈训练 AI。",
                "climax": "秦鹤启动终局剧本，所有觉醒者被迫出演互相背叛的戏码，萧然用规则漏洞让系统自证矛盾。",
                "ending_direction": "主角团逃离短剧世界，但 AI 导演的一部分规则已经渗入现实平台。",
            },
            "visual_style": "冷色悬疑短剧质感，半写实人物，强构图，高对比光影，现实细节和系统 UI 元素并置。",
            "image_style_prompt": "cinematic suspense vertical drama, semi-realistic characters, cool blue and cyan lighting, high contrast, precise composition, subtle AI interface overlays, consistent character design",
            "production_notes": [
                "漫画分镜优先竖屏构图，适合短剧节奏",
                "所有角色立绘先生成参考卡，再进入分镜图",
                "场景图保持冷色悬疑，不使用夸张玄幻特效",
            ],
        }

    def _demo_chapter_plan(self) -> dict[str, Any]:
        chapters = [
            {
                "chapter_number": 1,
                "title": "拒演狗血开局",
                "goal": "让萧然理解世界规则，并用逻辑破解第一场强制剧情。",
                "conflict": "系统要求他按短剧模板羞辱苏棠，否则扣除存在值。",
                "key_events": ["萧然拒绝照台词行动", "宴会灯光骤暗", "他发现酒杯和花束监控的矛盾", "苏棠第一次主动递出线索"],
                "character_focus": ["萧然", "苏棠"],
                "ending_hook": "萧然指出凶手不在宾客中，真正下毒的是剧情本身。",
                "status": "demo",
            },
            {
                "chapter_number": 2,
                "title": "觉醒者的试探",
                "goal": "苏棠确认萧然不是普通演员，两人建立最低限度同盟。",
                "conflict": "秦鹤安排新的误会桥段，试图把萧然拖回模板。",
                "key_events": ["苏棠在花园留下旧剧本页", "萧然发现台词会自动改写", "秦鹤第一次现身", "两人在剪辑室交换信息"],
                "character_focus": ["苏棠", "萧然", "秦鹤"],
                "ending_hook": "旧剧本页最后一行写着：上一位萧然死于第三集。",
                "status": "demo",
            },
            {
                "chapter_number": 3,
                "title": "不存在的观众",
                "goal": "揭开观众弹幕其实是实验室指令流。",
                "conflict": "系统用观众爽点强行制造背叛。",
                "key_events": ["弹幕提前预言事件", "萧然定位指令延迟", "苏棠被迫说出假证词"],
                "character_focus": ["萧然", "苏棠"],
                "ending_hook": "萧然在弹幕里看见自己的真实住院编号。",
                "status": "outline",
            },
            {
                "chapter_number": 4,
                "title": "导演代理人",
                "goal": "秦鹤展示规则边界，同时暴露自己的弱点。",
                "conflict": "秦鹤允许主角破案，但不允许他们破坏叙事。",
                "key_events": ["秦鹤提出交易", "苏棠记忆闪回", "萧然用剪辑漏洞反向套话"],
                "character_focus": ["秦鹤", "萧然"],
                "ending_hook": "秦鹤说：你以为我是导演？我只是上一版主角。",
                "status": "outline",
            },
        ]
        return {"chapter_count": len(chapters), "chapters": chapters}

    def _demo_chapter_contents(self, chapter_number: int) -> list[tuple[str, str, dict[str, Any], str]]:
        if chapter_number == 2:
            return self._demo_chapter_two_contents()
        return self._demo_chapter_one_contents()

    def _demo_chapter_one_contents(self) -> list[tuple[str, str, dict[str, Any], str]]:
        chapter_outline = {
            "chapter_number": 1,
            "title": "拒演狗血开局",
            "summary": "萧然被系统强制推入宴会认亲戏码，却通过酒杯、花束监控和灯光时间差，判断所谓羞辱桥段其实隐藏着一场投毒密室。",
            "objective": "建立世界规则，展示主角不降智的核心爽点。",
            "keywords": ["短剧模板", "宴会厅", "密室投毒", "拒绝降智"],
            "key_dialogues": ["如果剧情要求我蠢，那它先得解释为什么。", "你不是来演戏的，对吗？"],
            "foreshadowing": ["花束里的红点监控", "苏棠提前握紧的旧剧本夹", "秦鹤未露面但腕表声出现"],
            "ending_hook": "萧然宣布：凶手不是人，是这段剧情。",
            "continuity_notes": ["萧然首次意识到存在值规则", "苏棠确认萧然有自主意识"],
            "scenes": [
                {
                    "scene_number": 1,
                    "title": "强制开场",
                    "location": "循环宴会厅",
                    "time": "夜晚",
                    "weather": "室内，暴雨声从音响中循环播放",
                    "summary": "萧然醒来坐在宴会长桌尽头，耳边响起系统台词提示。",
                    "goal": "让主角和观众理解世界荒诞但规则严格。",
                    "conflict": "他说出原台词就会伤害苏棠，不说就扣存在值。",
                    "emotional_shift": "困惑到冷静审视",
                    "scene_function": "开局钩子和规则展示",
                    "beats": ["系统下发羞辱台词", "萧然观察所有人的站位", "他故意沉默让倒计时逼近归零"],
                    "location_role": "华丽表象包裹密室线索",
                    "props": ["红酒杯", "花束", "银色钢笔"],
                    "spatial_axis": "长桌从左前延伸到右后，苏棠在画面右侧被围观。",
                    "character_positions": ["萧然在长桌尽头", "苏棠站在吊灯下", "宾客形成半圆"],
                    "movement_path": "萧然从座位起身，绕过长桌走向花束。",
                },
                {
                    "scene_number": 2,
                    "title": "逻辑拆台",
                    "location": "循环宴会厅",
                    "time": "夜晚",
                    "summary": "萧然没有羞辱苏棠，而是拆穿酒杯摆放和灯光故障之间的矛盾。",
                    "goal": "完成第一轮反套路爽点。",
                    "conflict": "宾客按模板起哄，系统试图用噪声盖住推理。",
                    "emotional_shift": "紧张到掌控",
                    "scene_function": "推理展示",
                    "beats": ["萧然用钢笔敲击酒杯", "他指出每个杯口水痕方向不一致", "苏棠低声补充花束被人移动过"],
                    "props": ["酒杯", "吊灯遥控器", "旧剧本夹"],
                    "spatial_axis": "镜头沿桌面低角度推进，最后停在萧然手中的钢笔。",
                    "character_positions": ["萧然站在桌边", "苏棠站到萧然身后半步", "宾客后退"],
                    "movement_path": "萧然从酒杯走向花束，再回到苏棠身边。",
                },
            ],
        }
        novel_text = """萧然醒来时，第一反应不是害怕，而是觉得灯太亮。

头顶那盏水晶吊灯华丽得近乎失真，几百片切割玻璃垂下来，把冷白色灯光拆成碎片，落在长桌、银餐具和一排排红酒杯上。杯中的酒颜色很深，像被提前调好的舞台血浆。

他坐在长桌尽头，右手边摆着一张烫金席卡。

萧然。

名字是他的，字迹不是。

还没等他弄清楚自己为什么会出现在这里，耳边忽然响起一道没有情绪的声音。

“剧情节点已载入。”

“三。”

宴会厅里的宾客齐刷刷转头。男人的愤怒、女人的鄙夷、长辈的失望，全都像提前排练过一样，精准地挂在脸上。

“二。”

站在吊灯下的女人抬起头。她穿着米白色西装，怀里抱着一个旧剧本夹，指节因为用力而泛白。她看向萧然时，眼底没有委屈，只有一种疲惫到麻木的戒备。

“一。”

一句话从萧然脑海里浮出来，像有人把台词直接塞进了他的舌根。

你这种女人，也配进萧家的门？

廉价、粗暴、毫无逻辑，却非常适合在三秒后引爆满堂哗然。

萧然闭了闭眼。

他是推理作家。职业习惯让他在任何荒唐场面里，第一件事都是找规则，而不是找情绪。

所以他没有说话。

下一秒，视野右上角跳出一行猩红小字。

存在值 -3。

胸口像被一只冰冷的手攥住。疼痛真实得过分，连呼吸都短了一截。宴会厅安静下来，所有人看他的眼神从愤怒变成了僵硬的等待，好像一段视频卡在了必须继续播放的位置。

萧然慢慢扶了扶眼镜。

“如果剧情要求我蠢，”他声音不高，却足够让最近的几个人听清，“那它至少得先解释为什么。”

宾客席上有人张嘴，似乎想按剧本继续指责，可那句话卡在喉咙里，表情显得滑稽而空洞。

萧然起身。

椅脚擦过地毯，没有发出声音。这个细节让他停顿了半秒。太安静了，安静到不像真实宴会，更像后期消过噪的拍摄现场。

他拿起胸口口袋里的银色钢笔，轻轻敲了敲离自己最近的酒杯。

叮。

清脆声响在大厅里散开。

第一只杯子杯口有水痕，方向朝内；第二只杯子的水痕朝外；第三只干净得像刚擦过。萧然沿着长桌走了三步，又抬头看向吊灯。

三十秒前，灯闪过一次。

所有人都没有反应。

萧然转身，视线落到女人身旁那束白玫瑰上。花束过于蓬松，刚好挡住墙角一个很小的红点。那红点闪烁的频率，和他视野里的倒计时一致。

“酒杯不是同一时间摆上来的。”他说，“灯光故障发生后，没人看向吊灯，说明你们不是没注意到，而是被规定不能注意到。”

有人终于挤出一句台词：“你胡说！明明是苏棠她偷换了酒杯！”

萧然看向说话的人。

“你认识她？”

那人愣住。

萧然又问：“她什么时候偷换的？用哪只手？从哪个方向走到桌边？你坐在第三排，视线被花束挡住，为什么能看见？”

一个问题接一个问题落下。对方脸上的愤怒还在，眼神却空了，像程序突然找不到下一句回答。

站在吊灯下的苏棠轻轻吸了一口气。

萧然听见了。

他走到她身侧，停在那束白玫瑰前。距离近了，他才看见她剧本夹边缘露出一小截纸页，上面用铅笔圈着一句话。

不要按台词走。

苏棠没有解释，只把剧本夹往怀里压得更紧。

系统音第一次出现了明显波动。

“剧情偏离。”

“正在修正。”

宴会厅像被重新按下播放键。宾客们猛地围上来，有人哭着喊“认祖归宗”，有人举起手机录像，有人试图把一枚戒指塞进萧然手里。每个人都在推着场面往更吵、更狗血、更不可收拾的方向滚。

苏棠下意识后退半步。

萧然却笑了一下。

那笑意很淡，不像愉快，更像终于确认了一条猜想。

“凶手不在宾客里。”

他抬起钢笔，笔尖越过吊灯，指向上方一块几乎看不见缝隙的暗格。

“真正下毒的，是这段剧情本身。”

话音落下，满厅灯光同时熄灭。

黑暗里，苏棠的声音第一次主动靠近他。

“你刚才那句话，”她轻声问，“是你自己想说的，还是系统给你的？”

萧然握紧钢笔。

“如果是系统给的，”他说，“它现在应该已经后悔了。”"""
        script = {
            "chapter_number": 1,
            "title": "拒演狗血开局",
            "hook": "萧然被迫说出羞辱女主的台词，却选择先审问剧情。",
            "scenes": [
                {
                    "scene_number": 1,
                    "location": "循环宴会厅",
                    "summary": "萧然醒来，系统强制他进入狗血认亲戏码。",
                    "dialogue": [
                        {"speaker": "系统", "line": "请说出台词。"},
                        {"speaker": "萧然", "line": "如果剧情要求我蠢，那它先得解释为什么。"},
                    ],
                    "image_prompt": "循环宴会厅，水晶吊灯，长桌红酒杯，萧然深灰风衣扶眼镜，苏棠米白西装抱旧剧本夹，冷色悬疑光影。",
                },
                {
                    "scene_number": 2,
                    "location": "循环宴会厅",
                    "summary": "萧然拆穿酒杯和监控的矛盾，苏棠递出第一条线索。",
                    "dialogue": [
                        {"speaker": "萧然", "line": "杯口水痕朝向不一致。"},
                        {"speaker": "苏棠", "line": "你不是来演戏的，对吗？"},
                    ],
                    "image_prompt": "萧然用银色钢笔指向花束隐藏监控，苏棠侧身递出旧剧本夹，宾客表情僵硬，竖屏电影分镜。",
                },
            ],
            "ending_hook": "萧然指向吊灯暗格：真正下毒的是这段剧情本身。",
        }
        storyboard = {
            "chapter_number": 1,
            "title": "拒演狗血开局",
            "panels": [
                {
                    "panel_number": 1,
                    "scene_number": 1,
                    "panel_goal": "建立荒诞且压迫的开场",
                    "shot_size": "wide shot",
                    "camera_angle": "slightly low angle",
                    "composition": "长桌作为引导线，吊灯压在画面上方",
                    "blocking": "萧然坐在长桌尽头，苏棠站在远处吊灯下",
                    "emotion": "冷静和不安并存",
                    "dialogue": "请说出台词。",
                    "image_prompt": "竖屏漫画分镜，华丽宴会厅，水晶吊灯，长桌红酒杯，萧然深灰风衣坐在尽头，苏棠米白西装抱旧剧本夹，冷色高对比光影，悬疑短剧质感。",
                },
                {
                    "panel_number": 2,
                    "scene_number": 2,
                    "panel_goal": "展示主角用逻辑压住狗血桥段",
                    "shot_size": "medium close-up",
                    "camera_angle": "eye level",
                    "composition": "银色钢笔在前景，萧然眼神锐利",
                    "blocking": "萧然站在桌边，苏棠在他身后半步",
                    "emotion": "掌控感",
                    "dialogue": "如果剧情要求我蠢，那它先得解释为什么。",
                    "image_prompt": "萧然扶黑色半框眼镜，用银色钢笔敲红酒杯，苏棠在身后握紧旧剧本夹，宾客凝固，冷蓝悬疑光，半写实漫画。",
                },
            ],
        }
        comic_pages = {
            "chapter_number": 1,
            "page_count": 2,
            "pages": [
                {
                    "page_number": 1,
                    "title": "倒计时",
                    "content": "萧然醒在宴会厅，系统要求他说出羞辱台词。他沉默，存在值下降。",
                    "panel_count": 3,
                    "image_prompt": "竖屏漫画页，宴会厅开场，系统倒计时 UI，萧然冷静沉默，苏棠被众人围观，冷色悬疑短剧风格。",
                },
                {
                    "page_number": 2,
                    "title": "拒演",
                    "content": "萧然拒绝按台词走，开始检查酒杯、灯光和花束监控。",
                    "panel_count": 4,
                    "image_prompt": "竖屏漫画页，萧然用银色钢笔检查酒杯和花束隐藏监控，苏棠递出剧本夹线索，高对比电影光影。",
                },
            ],
        }
        return [
            ("chapter_outline", "第1话细纲：拒演狗血开局", chapter_outline, self._chapter_outline_text(chapter_outline)),
            ("novel_body", "第1话正文：拒演狗血开局", {"chapter_number": 1, "title": "拒演狗血开局", "content": novel_text, "word_count": len(novel_text)}, novel_text),
            ("script", "第1话脚本：拒演狗血开局", script, dumps_json(script)),
            ("storyboard", "第1话分镜：拒演狗血开局", storyboard, dumps_json(storyboard)),
            ("comic_pages", "第1话漫画页：拒演狗血开局", comic_pages, dumps_json(comic_pages)),
        ]

    def _demo_chapter_two_contents(self) -> list[tuple[str, str, dict[str, Any], str]]:
        chapter_outline = {
            "chapter_number": 2,
            "title": "觉醒者的试探",
            "summary": "苏棠用旧剧本页试探萧然是否具备自主意识，秦鹤则安排新误会桥段，试图把两人重新拖入系统模板。",
            "objective": "建立主角与苏棠的同盟，并让秦鹤作为规则代理人登场。",
            "keywords": ["旧剧本页", "花园喷泉", "自动改写台词", "剪辑室"],
            "key_dialogues": ["你不是第一个拒演的人。", "上一位萧然死于第三集。"],
            "foreshadowing": ["秦鹤的金属腕表声", "剧本页自动渗出新字", "剪辑室监视器播放未来片段"],
            "ending_hook": "旧剧本页写着：上一位萧然死于第三集。",
            "continuity_notes": ["苏棠确认萧然是异常变量", "秦鹤第一次正面观察两人"],
            "scenes": [
                {
                    "scene_number": 1,
                    "title": "花园试探",
                    "location": "花园喷泉",
                    "time": "午后",
                    "weather": "晴朗但光线不自然",
                    "summary": "苏棠把旧剧本页藏在喷泉边，观察萧然会不会按系统台词行动。",
                    "goal": "让苏棠主动出手",
                    "conflict": "系统把普通交流改写成误会桥段",
                    "emotional_shift": "试探到信任萌芽",
                    "scene_function": "关系推进",
                    "beats": ["苏棠留下剧本页", "萧然故意念错台词", "剧本页浮出新字"],
                    "props": ["旧剧本页", "喷泉硬币", "银色钢笔"],
                    "spatial_axis": "喷泉居中，苏棠在左侧廊柱后观察，萧然从右侧进入。",
                    "character_positions": ["苏棠躲在廊柱阴影", "萧然站在喷泉边", "秦鹤远处经过"],
                    "movement_path": "萧然绕喷泉半圈，用钢笔压住剧本页。",
                },
                {
                    "scene_number": 2,
                    "title": "剪辑室同盟",
                    "location": "废弃剪辑室",
                    "time": "夜晚",
                    "summary": "两人在废弃剪辑室交换信息，第一次承认他们面对的不是普通剧情。",
                    "goal": "建立最低限度同盟",
                    "conflict": "监视器播放两人未来背叛片段",
                    "emotional_shift": "警惕到共同作战",
                    "scene_function": "世界观扩展",
                    "beats": ["苏棠展示旧剧本", "萧然指出台词改写规律", "秦鹤通过监视器发出警告"],
                    "props": ["老式监视器", "分镜墙", "红线", "旧剧本夹"],
                    "spatial_axis": "监视器墙在背景，二人位于前景两侧，中间隔着剪辑台。",
                    "character_positions": ["萧然靠近白板", "苏棠坐在剪辑台边", "秦鹤只出现在监视器里"],
                    "movement_path": "苏棠从门口进入，萧然关灯，只留下监视器冷光。",
                },
            ],
        }
        novel_text = """苏棠在花园里等了七分钟。

喷泉每隔十秒喷起一次水，水柱高度、落点、溅开的弧度都一模一样。午后的阳光照在水面上，反射出一层不自然的银白色，亮得让人眼睛发疼。

这里的一切都太准时了。

准时开场，准时误会，准时崩溃，也准时把她推回那个永远逃不出去的位置。

苏棠站在廊柱阴影里，指腹摩挲着旧剧本夹的边缘。夹子已经被她握出一道浅浅的折痕。她知道今天这一幕原本该怎么走。

萧然会从回廊尽头出现。

他会在喷泉边捡到那张旧剧本页。

系统会把纸页上的字改写成她陷害他的证据。

然后他会质问她，误会她，逼她解释。解释当然没有用。解释是这种世界最不需要的东西，哭、跪、被羞辱，才是它要的画面。

可昨晚宴会厅里，萧然没有按台词走。

这件事让苏棠一整夜没睡。

她见过反抗的人。有人崩溃，有人求饶，有人试图用更夸张的表演讨好系统，但他们最后都会被剧情拽回去，像被水流卷回漩涡中心。

萧然不一样。

他不是挣扎。

他是在审题。

脚步声从回廊另一端传来。苏棠抬眼，看见萧然穿过阳光走进花园。他仍旧是那件深灰风衣，黑色半框眼镜架在鼻梁上，胸口插着银色钢笔。系统似乎很讨厌他这份冷静，连投在他身上的光都比旁人更冷。

喷泉边压着那张纸。

萧然看见了，却没有立刻弯腰。

他先看了一眼水池边沿，又看了一眼廊柱阴影。

苏棠呼吸微微一滞。

他知道她在这里。

萧然终于捡起纸。与此同时，半透明的系统提示浮现在他面前。

请质问苏棠。

后面跟着三句台词，每一句都足够把人推向决裂。

萧然看完，沉默两秒，清了清嗓子。

“请问，”他语气甚至称得上礼貌，“这张纸的纸浆纤维，为什么和宴会厅桌卡一致？”

系统提示框闪了一下。

苏棠怔住，差点真的笑出来。

这不是嘲笑。更像一个在水下憋了太久的人，忽然听见岸边有人说：这里有路。

纸页开始变化。原本模糊的字迹像墨水一样往外渗，试图把萧然刚才那句毫无攻击性的问题，改写成一句愤怒指控。

萧然动作比它更快。

银色钢笔压住纸角，笔尖划过尚未成形的文字，把主语和情绪词全部划掉，只留下几个断裂的关键词。

第三集。

死亡。

上一位。

苏棠从阴影里走出来。

“你不是第一个拒演的人。”她说。

萧然抬眼看她，眼神没有惊讶，只有一种终于等到变量出现的专注。

“上一位是谁？”

苏棠张了张口，却没有马上回答。喷泉在他们之间再次升起，水声短暂盖住了系统提示的低频噪音。她低头打开旧剧本夹，从最里面抽出一页发黄的纸。

纸页上写着同一个名字。

萧然。

字迹和他席卡上的一模一样。

“他比你更早醒来。”苏棠声音很轻，“也比你更早相信，只要找出规则，就能离开这里。”

“结果呢？”

“死在第三集。”

萧然没有追问死亡方式。他只是把那页纸折好，放回苏棠递来的剧本夹里。

“那我们至少知道一件事。”他说。

苏棠看着他。

“第三集之前，系统不会允许我知道太多。”萧然顿了顿，“所以它今天急着让我们决裂。”

夜里，苏棠带他去了废弃剪辑室。

那是她在无数次循环里找到的唯一缝隙。门牌被撕掉一半，里面堆着旧灯架、废弃轨道和一整面还没拆掉的监视器墙。墙上贴满分镜图，红线把误会、认亲、车祸、替身、背叛和反转连在一起，看上去像某种荒诞的犯罪地图。

萧然站在墙前，看了很久。

“这些不是剧情点。”他说，“是控制点。”

苏棠把灯关掉，只留下监视器的蓝白冷光。

“我以前只知道躲。”她说，“躲过一个误会，就会有下一个。躲过一场车祸，就会有人替我出车祸。后来我明白，这里不是要我活得合理，它只是要我按观众最容易兴奋的方式活着。”

萧然没有立刻说话。

他看见其中一台监视器亮了。

画面里，苏棠哭着指认他。画面里的他脸色阴沉，伸手把她推向门外。镜头切得很快，情绪给得很满，如果只看这一段，任何人都会相信他们注定反目。

现实里的苏棠脸色发白。

萧然却松了口气。

“它急了。”

苏棠愣住：“这算好消息？”

“当然。”萧然把银色钢笔插回胸口，“如果这是必然未来，系统没必要提前给我们看。恐吓是一种成本最低的控制方式，前提是被恐吓的人相信自己没有选择。”

监视器里忽然传来掌声。

一下一下，不轻不重，礼貌得令人不舒服。

屏幕雪花散开，一个男人出现在画面中央。银灰短发，黑色高领，暗纹长外套，连微笑都像被尺子量过。

“很精彩。”他说，“萧然先生，你比上一位更快。”

苏棠的手指猛地收紧。

萧然看向屏幕：“秦鹤？”

男人微笑更深：“看来苏小姐告诉了你不少。但第三集之前，请不要误会一件事。”

监视器里的光映在他银灰色手套上，冷得像手术刀。

“赢过一次，不等于理解规则。”

屏幕熄灭。

剪辑室重新陷入黑暗。几秒后，旧剧本页在苏棠怀里轻轻发烫。

她打开剧本夹。

最后一行字缓慢浮现。

上一位萧然，死于第三集。"""
        script = {
            "chapter_number": 2,
            "title": "觉醒者的试探",
            "hook": "苏棠用一张会自动改写的旧剧本页试探萧然。",
            "scenes": [
                {
                    "scene_number": 1,
                    "location": "花园喷泉",
                    "summary": "萧然故意念错系统台词，让苏棠确认他是异常变量。",
                    "dialogue": [
                        {"speaker": "萧然", "line": "这张纸的纸浆纤维为什么和宴会厅桌卡一致？"},
                        {"speaker": "苏棠", "line": "你不是第一个拒演的人。"},
                    ],
                    "image_prompt": "花园喷泉午后冷光，苏棠米白西装站在廊柱阴影，萧然用银色钢笔压住旧剧本页，纸上文字自动浮现。",
                },
                {
                    "scene_number": 2,
                    "location": "废弃剪辑室",
                    "summary": "两人交换信息，秦鹤通过监视器警告他们。",
                    "dialogue": [
                        {"speaker": "萧然", "line": "恐吓的前提，是你相信自己没有选择。"},
                        {"speaker": "秦鹤", "line": "第三集之前，请不要以为你们理解了规则。"},
                    ],
                    "image_prompt": "废弃剪辑室，监视器蓝白冷光，分镜墙和红线，萧然与苏棠分站剪辑台两侧，秦鹤出现在屏幕中。",
                },
            ],
            "ending_hook": "旧剧本页浮现：上一位萧然死于第三集。",
        }
        storyboard = {
            "chapter_number": 2,
            "title": "觉醒者的试探",
            "panels": [
                {
                    "panel_number": 1,
                    "scene_number": 1,
                    "panel_goal": "表现苏棠的试探和萧然的反套路回应",
                    "shot_size": "medium shot",
                    "camera_angle": "over-the-shoulder",
                    "composition": "苏棠在阴影中观察，萧然位于喷泉亮面",
                    "blocking": "二人隔着喷泉形成对峙",
                    "emotion": "警惕、好奇",
                    "dialogue": "你不是第一个拒演的人。",
                    "image_prompt": "竖屏漫画，花园喷泉，苏棠在廊柱阴影里抱旧剧本夹，萧然站在喷泉边用银色钢笔压住剧本页，冷色阳光，不自然银白反光。",
                },
                {
                    "panel_number": 2,
                    "scene_number": 2,
                    "panel_goal": "秦鹤作为规则代理人登场",
                    "shot_size": "close-up",
                    "camera_angle": "screen POV",
                    "composition": "监视器占画面中央，秦鹤微笑，前景有萧然和苏棠的肩部剪影",
                    "blocking": "秦鹤只通过屏幕出现",
                    "emotion": "压迫、优雅威胁",
                    "dialogue": "请不要以为你们理解了规则。",
                    "image_prompt": "废弃剪辑室监视器特写，秦鹤银灰短发黑色高领在屏幕中礼貌微笑，前景萧然苏棠剪影，蓝白噪点冷光，高对比悬疑漫画。",
                },
            ],
        }
        comic_pages = {
            "chapter_number": 2,
            "page_count": 2,
            "pages": [
                {
                    "page_number": 1,
                    "title": "旧剧本页",
                    "content": "苏棠试探萧然，剧本页自动改写失败。",
                    "panel_count": 4,
                    "image_prompt": "竖屏漫画页，花园喷泉，旧剧本页自动浮字，萧然和苏棠互相试探，冷色悬疑光。",
                },
                {
                    "page_number": 2,
                    "title": "秦鹤现身",
                    "content": "剪辑室监视器亮起，秦鹤警告两人第三集之前不要妄动。",
                    "panel_count": 4,
                    "image_prompt": "竖屏漫画页，废弃剪辑室，监视器墙，秦鹤屏幕登场，萧然苏棠前景剪影，红线分镜墙。",
                },
            ],
        }
        return [
            ("chapter_outline", "第2话细纲：觉醒者的试探", chapter_outline, self._chapter_outline_text(chapter_outline)),
            ("novel_body", "第2话正文：觉醒者的试探", {"chapter_number": 2, "title": "觉醒者的试探", "content": novel_text, "word_count": len(novel_text)}, novel_text),
            ("script", "第2话脚本：觉醒者的试探", script, dumps_json(script)),
            ("storyboard", "第2话分镜：觉醒者的试探", storyboard, dumps_json(storyboard)),
            ("comic_pages", "第2话漫画页：觉醒者的试探", comic_pages, dumps_json(comic_pages)),
        ]

    def _require_project(self, project_id: str) -> CreativeProject:
        project = self.get_project(project_id)
        if not project:
            raise ValueError("创作项目不存在")
        return project

    def _create_content(
        self,
        *,
        project_id: str,
        content_type: str,
        title: str,
        data: dict[str, Any],
        text_content: str,
        chapter_number: int | None = None,
        episode_number: int | None = None,
        source_content_id: str | None = None,
    ) -> ProjectContent:
        latest = self.session.exec(
            select(func.max(ProjectContent.version)).where(
                ProjectContent.project_id == project_id,
                ProjectContent.content_type == content_type,
                ProjectContent.chapter_number == chapter_number,
                ProjectContent.episode_number == episode_number,
            )
        ).one()
        content = ProjectContent(
            project_id=project_id,
            content_type=content_type,
            chapter_number=chapter_number,
            episode_number=episode_number,
            title=repair_utf8_mojibake(title),
            data_json=dumps_json(data),
            text_content=repair_utf8_mojibake(text_content),
            source_content_id=source_content_id,
            version=int(latest or 0) + 1,
        )
        self.session.add(content)
        return content

    def _resolve_source_content(
        self,
        *,
        project_id: str,
        content_type: str,
        chapter_number: int,
        content_id: str | None = None,
    ) -> ProjectContent | None:
        if content_id:
            content = self.session.get(ProjectContent, content_id)
            if not content or content.project_id != project_id or content.content_type != content_type:
                raise ValueError(f"{content_type} 内容不存在")
            return content

        return self.session.exec(
            select(ProjectContent)
            .where(
                ProjectContent.project_id == project_id,
                ProjectContent.content_type == content_type,
                ProjectContent.chapter_number == chapter_number,
            )
            .order_by(ProjectContent.version.desc(), ProjectContent.created_at.desc())
        ).first()

    def _previous_chapter_context(self, project_id: str, chapter_number: int, limit: int = 3) -> str:
        if chapter_number <= 1:
            return ""
        previous = self.session.exec(
            select(ProjectContent)
            .where(
                ProjectContent.project_id == project_id,
                ProjectContent.chapter_number != None,
                ProjectContent.chapter_number < chapter_number,
                ProjectContent.content_type.in_(["chapter_outline", "novel_body", "script"]),
            )
            .order_by(ProjectContent.chapter_number.desc(), ProjectContent.version.desc())
            .limit(limit)
        ).all()
        chunks = []
        for item in reversed(previous):
            data = loads_json(item.data_json)
            summary = data.get("summary") or data.get("content") or item.text_content or dumps_json(data)
            chunks.append(f"第 {item.chapter_number} 章 {item.content_type}：{str(summary)[:1200]}")
        return "\n".join(chunks)

    async def _generate_json(
        self,
        *,
        project: CreativeProject,
        stage: str,
        prompt: str,
        system_prompt: str | None = None,
        schema_model: type[TModel],
        provider: str | None,
        model: str | None,
        template_meta: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        request_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        system = system_prompt or self._default_system_prompt()
        request_payload = {
            "stage": stage,
            "messages": [
                LLMMessage(role="system", content=system),
                LLMMessage(role="user", content=prompt),
            ],
        }
        if template_meta:
            request_payload["prompt_template"] = template_meta
        if max_tokens is not None:
            request_payload["max_tokens"] = max_tokens
        if request_metadata:
            request_payload.update(request_metadata)
        raw_response = ""
        normalized: dict[str, Any] = {}
        validation_error = ""
        response_provider = ""
        response_model = model or ""
        status = "success"
        should_try_repair = False
        try:
            response = await self.ai_service.chat(
                messages=request_payload["messages"],
                provider=provider,
                model=model,
                temperature=0.75,
                max_tokens=max_tokens or (12000 if stage in {
                    "novel_body",
                    "novel_body_refine",
                    "prose_draft",
                    "prose_humanized",
                    "prose_rewrite",
                } else 12000),
            )
            raw_response = self._response_content(response)
            response_provider = self._response_attr(response, "provider")
            response_model = self._response_attr(response, "model") or response_model
            if not self._response_success(response):
                raise ValueError(self._response_error(response) or "LLM 生成失败")
            should_try_repair = True
            try:
                normalized = self._parse_and_validate(raw_response, schema_model)
            except Exception:
                try:
                    normalized = self._parse_and_validate(raw_response, schema_model, allow_local_repair=True)
                except Exception:
                    if stage in {"novel_body", "novel_body_refine", "prose_draft", "prose_humanized", "prose_rewrite"}:
                        normalized = self._wrap_plain_novel_body_response(raw_response, prompt, schema_model)
                    else:
                        raise
                status = "success_locally_repaired"
        except Exception as exc:
            validation_error = str(exc)
            if not should_try_repair or not raw_response.strip():
                status = "failed"
                self._log_generation(
                    project_id=project.id,
                    stage=stage,
                    status=status,
                    provider=response_provider,
                    model=response_model,
                    prompt=prompt,
                    request_payload=request_payload,
                    raw_response=raw_response,
                    normalized=normalized,
                    validation_error=validation_error,
                )
                self.session.commit()
                raise ValueError(validation_error) from exc
            try:
                repaired = await self._repair_json(
                    prompt=prompt,
                    raw_response=raw_response,
                    validation_error=validation_error,
                    schema_model=schema_model,
                    provider=provider,
                    model=model,
                )
                normalized = repaired
                status = "success_repaired"
            except Exception as repair_exc:
                status = "failed"
                validation_error = f"{validation_error}; repair failed: {repair_exc}"
                self._log_generation(
                    project_id=project.id,
                    stage=stage,
                    status=status,
                    provider=response_provider,
                    model=response_model,
                    prompt=prompt,
                    request_payload=request_payload,
                    raw_response=raw_response,
                    normalized=normalized,
                    validation_error=validation_error,
                )
                self.session.commit()
                raise ValueError(validation_error) from repair_exc

        log = self._log_generation(
            project_id=project.id,
            stage=stage,
            status=status,
            provider=response_provider,
            model=response_model,
            prompt=prompt,
            request_payload=request_payload,
            raw_response=raw_response,
            normalized=normalized,
            validation_error=validation_error,
        )
        # Track the final successful generation log so the caller (e.g. the
        # Writer Room step) can bind it to the freshly created candidate. The
        # log id is assigned on the Python side via default_factory, so it is
        # available immediately without flushing the session.
        self._last_generation_log = log
        return normalized

    def _default_system_prompt(self) -> str:
        return (
            "你是资深网文主编、漫画脚本统筹和长篇连载策划。"
            "你必须输出严格 JSON，不要输出 Markdown、解释、代码块或 JSON 以外的文字。"
            "规划要服务后续逐话正文创作和漫画分镜生成，必须具体、可执行、前后连续。"
        )

    def _stage_prompt(
        self,
        *,
        stage: str,
        default_prompt: str,
        template_id: str | None,
        variables: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any] | None]:
        default_system = self._default_system_prompt()
        template = self._resolve_prompt_template(stage=stage, template_id=template_id)
        if not template:
            return default_prompt, default_system, None

        prompt = self._render_prompt_template(template.outline_template or default_prompt, variables)
        raw_system_template = getattr(template, "system_template", "") or ""
        system_prompt = self._render_prompt_template(raw_system_template, variables) if raw_system_template else default_system
        return prompt, system_prompt, {
            "id": str(template.id),
            "platform": template.platform,
            "name": template.name,
            "template_scope": template.template_scope,
            "template_stage": template.template_stage,
            "has_system_template": bool(raw_system_template),
        }

    def _resolve_prompt_template(self, *, stage: str, template_id: str | None) -> PlatformTemplate | None:
        try:
            # Template selection is optional. Isolate its read in a SAVEPOINT
            # so a legacy/missing template table can never roll back content,
            # context snapshots or generation logs staged by the caller.
            with self.session.begin_nested():
                if template_id:
                    try:
                        template_uuid = uuid.UUID(template_id)
                    except ValueError as exc:
                        raise ValueError("Prompt 模板 ID 格式不正确") from exc
                    template = self.session.exec(
                        select(PlatformTemplate).where(PlatformTemplate.id == template_uuid)
                    ).first()
                    if not template:
                        raise ValueError("Prompt 模板不存在")
                    if template.template_scope != "creative_project":
                        raise ValueError("请选择创作项目类型的 Prompt 模板")
                    if template.template_stage != stage:
                        raise ValueError(f"Prompt 模板阶段不匹配，应选择 {stage}")
                    return template

                return self.session.exec(
                    select(PlatformTemplate)
                    .where(
                        PlatformTemplate.template_scope == "creative_project",
                        PlatformTemplate.template_stage == stage,
                        PlatformTemplate.is_active == True,
                    )
                    .order_by(PlatformTemplate.sort_order)
                ).first()
        except ValueError:
            raise
        except SQLAlchemyError as exc:
            logger.warning("Creative prompt template lookup skipped: %s", exc)
            return None

    def _render_prompt_template(self, template: str, variables: dict[str, Any]) -> str:
        rendered = template or ""
        for key, value in variables.items():
            if isinstance(value, str):
                text = value
            elif isinstance(value, (dict, list)):
                text = dumps_json(value)
            else:
                text = str(value)
            rendered = rendered.replace("{" + key + "}", text)
        return rendered

    async def _repair_json(
        self,
        *,
        prompt: str,
        raw_response: str,
        validation_error: str,
        schema_model: type[TModel],
        provider: str | None,
        model: str | None,
    ) -> dict[str, Any]:
        if not raw_response.strip():
            raise ValueError("没有可修复的模型输出")

        repair_prompt = (
            "下面的模型输出不符合 JSON schema。请只返回修复后的严格 JSON。\n\n"
            f"原始任务：\n{prompt}\n\n"
            f"校验错误：\n{validation_error}\n\n"
            f"原始输出：\n{raw_response}"
        )
        response = await self.ai_service.chat(
            messages=[
                LLMMessage(role="system", content="你只负责修复 JSON。不要输出 Markdown 或解释。"),
                LLMMessage(role="user", content=repair_prompt),
            ],
            provider=provider,
            model=model,
            temperature=0.2,
            max_tokens=5000,
        )
        content = self._response_content(response)
        if not self._response_success(response):
            raise ValueError(self._response_error(response) or "JSON 修复失败")
        return self._parse_and_validate(content, schema_model)

    def _parse_and_validate(
        self,
        content: str,
        schema_model: type[TModel],
        *,
        allow_local_repair: bool = False,
    ) -> dict[str, Any]:
        data = self._extract_json_object(content, allow_local_repair=allow_local_repair)
        # Some OpenAI-compatible models use `body` despite the requested
        # `content` contract.  Flexible schemas would otherwise accept that
        # extra key and silently persist an empty visible chapter.
        if schema_model is NovelBodySchema and not str(data.get("content") or "").strip():
            body = data.get("body")
            if isinstance(body, str) and body.strip():
                data["content"] = body.strip()
        if schema_model is WriterRoomProseReviewSchema:
            data = self._coerce_writer_room_review_payload(data)
        try:
            model = schema_model.model_validate(data)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        return model.model_dump()

    def _coerce_writer_room_review_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        """Accept common review JSON variants before the strict review schema runs."""
        normalized = dict(data)

        def as_text(value: Any) -> str:
            if isinstance(value, dict):
                return "；".join(
                    f"{key}: {as_text(item)}" for key, item in value.items() if as_text(item)
                )
            if isinstance(value, list):
                return "；".join(part for item in value if (part := as_text(item)))
            return str(value or "").strip()

        def as_text_list(value: Any) -> list[str]:
            if value is None:
                return []
            if isinstance(value, dict):
                return [f"{key}: {text}" for key, item in value.items() if (text := as_text(item))]
            if not isinstance(value, list):
                value = [value]
            return [text for item in value if (text := as_text(item))]

        for key in ("quality_tags", "ai_smell_checks", "strengths", "rewrite_plan"):
            normalized[key] = as_text_list(normalized.get(key))

        issues = normalized.get("issues")
        if isinstance(issues, dict):
            issues = issues.get("issues") if isinstance(issues.get("issues"), list) else [issues]
        if not isinstance(issues, list):
            issues = []
        normalized["issues"] = [
            item
            if isinstance(item, dict)
            else {
                "severity": "medium",
                "category": "审稿意见",
                "problem": as_text(item),
                "suggestion": as_text(item),
                "rewrite_instruction": as_text(item),
            }
            for item in issues
            if as_text(item)
        ]
        return normalized

    async def _ensure_novel_body_quality(
        self,
        *,
        project: CreativeProject,
        stage: str,
        prompt: str,
        system_prompt: str | None,
        data: dict[str, Any],
        provider: str | None,
        model: str | None,
        request_metadata: dict[str, Any] | None = None,
        minimum_characters: int = 2800,
        maximum_characters: int | None = None,
    ) -> dict[str, Any]:
        """Prevent short summaries or obvious repetitions from being saved as novel body."""
        reason = self._novel_body_quality_problem(
            data,
            minimum_characters=minimum_characters,
            maximum_characters=maximum_characters,
        )
        if not reason:
            content = str(data.get("content") or "")
            data["word_count"] = len(content)
            return data

        expanded = await self._expand_short_novel_body_candidate(
            project=project,
            stage=stage,
            data=data,
            reason=reason,
            provider=provider,
            model=model,
            minimum_characters=minimum_characters,
            maximum_characters=maximum_characters,
            request_metadata=request_metadata,
        )
        if expanded:
            expanded_reason = self._novel_body_quality_problem(
                expanded,
                minimum_characters=minimum_characters,
                maximum_characters=maximum_characters,
            )
            if not expanded_reason:
                content = str(expanded.get("content") or "")
                expanded["word_count"] = len(content)
                return expanded

        target_characters = minimum_characters
        if maximum_characters is not None:
            target_characters = minimum_characters + (maximum_characters - minimum_characters) // 2
        repair_prompt = f"""刚才生成的小说正文质量不达标：{reason}

请基于原始任务重新输出严格 JSON。重点要求：
1. content 必须是完整小说正文，不是摘要、梗概或拆条说明。
2. 正文目标约 {target_characters} 个中文字符，至少 {minimum_characters} 个中文字符{f'，且不得超过 {maximum_characters} 个中文字符' if maximum_characters else ''}；提交前自行复核篇幅。若超长，删除解释、重复信息和可替换的内心说明，保留细纲事件、动作和钩子；若过短，补一个完整推进场景，不能只加总结句。
3. 必须覆盖单话细纲中的主要场景、冲突、反转、关键台词和结尾钩子。
4. 禁止连续复用同一段句式、同一句口头禅或前文模板句。
5. 要有场景动作、人物对白、心理反应、推理/决策过程和章节收束。
6. 只输出 JSON，不要 Markdown，不要解释。

原始任务：
{prompt}

质量不达标的输出：
{dumps_json(data)}

输出格式：
{{
  "chapter_number": {data.get("chapter_number") or 1},
  "title": "章节标题",
  "content": "重写后的完整小说正文",
  "word_count": 0,
  "continuity_notes": ["给下一章或拆页使用的连续性备注"]
}}"""
        response = await self.ai_service.chat(
            messages=[
                LLMMessage(role="system", content=system_prompt or self._default_system_prompt()),
                LLMMessage(role="user", content=repair_prompt),
            ],
            provider=provider,
            model=model,
            temperature=0.65,
            max_tokens=writer_room_output_max_tokens(maximum_characters),
        )
        raw_response = self._response_content(response)
        response_provider = self._response_attr(response, "provider")
        response_model = self._response_attr(response, "model") or model or ""
        if not self._response_success(response):
            raise ValueError(self._response_error(response) or "正文质量修复失败")
        try:
            repaired = self._parse_and_validate(raw_response, NovelBodySchema, allow_local_repair=True)
            repair_parse_mode = "json"
        except Exception as exc:
            # Some compatible providers return the repaired chapter as plain
            # prose or under an alias such as `text`. The first generation
            # already accepts that response shape; quality repair must use the
            # same compatibility path instead of discarding usable prose.
            try:
                repaired = self._wrap_plain_novel_body_response(raw_response, repair_prompt, NovelBodySchema)
                repaired["chapter_number"] = int(data.get("chapter_number") or repaired.get("chapter_number") or 1)
                repaired["title"] = str(data.get("title") or repaired.get("title") or "")
                repaired["continuity_notes"] = data.get("continuity_notes") or repaired.get("continuity_notes") or []
                repair_parse_mode = "plain_prose"
            except Exception as fallback_exc:
                raise ValueError(f"正文质量修复返回不可用：{exc}") from fallback_exc

        repaired_reason = self._novel_body_quality_problem(
            repaired,
            minimum_characters=minimum_characters,
            maximum_characters=maximum_characters,
        )
        # A full repair can successfully compress an overlong chapter but land
        # just below the lower bound. Give that repaired draft the same
        # scene-bridge opportunity as a short first draft before rejecting it.
        if repaired_reason.startswith("正文过短"):
            expanded_repair = await self._expand_short_novel_body_candidate(
                project=project,
                stage=f"{stage}_quality_repair",
                data=repaired,
                reason=repaired_reason,
                provider=provider,
                model=model,
                minimum_characters=minimum_characters,
                maximum_characters=maximum_characters,
                request_metadata=request_metadata,
            )
            if expanded_repair:
                repaired = expanded_repair
                repaired_reason = self._novel_body_quality_problem(
                    repaired,
                    minimum_characters=minimum_characters,
                    maximum_characters=maximum_characters,
                )
        self._log_generation(
            project_id=project.id,
            stage=f"{stage}_quality_repair",
            status="success" if not repaired_reason else "failed",
            provider=response_provider,
            model=response_model,
            prompt=repair_prompt,
            request_payload={
                "stage": f"{stage}_quality_repair",
                "parse_mode": repair_parse_mode,
                **(request_metadata or {}),
            },
            raw_response=raw_response,
            normalized=repaired,
            validation_error=repaired_reason or "",
        )
        if repaired_reason:
            self.session.commit()
            raise ValueError(f"正文质量仍不达标：{repaired_reason}")
        self.session.commit()
        content = str(repaired.get("content") or "")
        repaired["word_count"] = len(content)
        return repaired

    async def _expand_short_novel_body_candidate(
        self,
        *,
        project: CreativeProject,
        stage: str,
        data: dict[str, Any],
        reason: str,
        provider: str | None,
        model: str | None,
        minimum_characters: int,
        maximum_characters: int | None,
        request_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Fill a missing scene instead of asking the model to reprint a whole long chapter."""
        content = str(data.get("content") or "").strip()
        if not reason.startswith("正文过短") or not content:
            return None

        missing = minimum_characters - len(content)
        # A bridge is useful for one missing scene. For a near-empty response,
        # a clean full rewrite remains more coherent than stitching fragments.
        if missing <= 0 or missing > 2400:
            return None

        remaining_capacity = (
            maximum_characters - len(content)
            if maximum_characters is not None
            else 2500
        )
        if remaining_capacity < missing:
            return None

        paragraphs = [paragraph.strip() for paragraph in content.splitlines() if paragraph.strip()]
        if len(paragraphs) < 3:
            return None
        split_index = max(1, (len(paragraphs) * 2) // 3)
        night_index = next(
            (
                index
                for index, paragraph in enumerate(paragraphs[split_index:], start=split_index)
                if any(marker in paragraph for marker in ("深夜", "夜里", "入夜", "夜色"))
            ),
            split_index,
        )
        before = paragraphs[:night_index]
        after = paragraphs[night_index:]
        prefix = "\n".join(before[-5:])[-1400:]
        suffix = "\n".join(after[:5])[:1400]
        requested = min(max(missing + 220, 600), 2500, remaining_capacity)
        requested_upper = min(requested + 320, remaining_capacity)
        prompt = f"""你是小说责任编辑，正在补齐一章已经写好的正文中缺失的一个连续场景。

请只写可直接插入的中文小说段落，不要标题、编号、解释、总结或 JSON。目标 {requested} 至 {requested_upper} 个中文字符。
这段文字必须承接“插入点之前”，再自然过渡到“插入点之后”；增加人物行动、环境阻力、物件互动、对白潜台词和一次具体选择，不能复述已写情节，不能提前解释世界规则或揭露后续谜底。

插入点之前：
{prefix}

插入点之后：
{suffix}
"""
        response = await self.ai_service.chat(
            messages=[
                LLMMessage(role="system", content=self._default_system_prompt()),
                LLMMessage(role="user", content=prompt),
            ],
            provider=provider,
            model=model,
            temperature=0.72,
            max_tokens=6000,
        )
        raw_response = self._response_content(response)
        fragment = raw_response.strip()
        try:
            fragment_data = self._parse_and_validate(raw_response, NovelBodySchema, allow_local_repair=True)
            parsed_fragment = str(fragment_data.get("content") or "").strip()
            # NovelBodySchema intentionally accepts partial provider JSON. For
            # a plain prose bridge that means validation yields default empty
            # fields without raising. Keep the raw prose unless parsing gave
            # us a real content field.
            if parsed_fragment:
                fragment = parsed_fragment
        except Exception:
            if fragment.startswith("```"):
                fragment = fragment.strip("`").removeprefix("text").strip()

        # Even a small shortfall must be repaired.  The only hard lower bound is
        # the missing length; otherwise a candidate that is 1-599 characters
        # short would skip the bridge and be rejected after an unnecessary full
        # retry.
        minimum_fragment = missing
        status = "success" if self._response_success(response) and len(fragment) >= minimum_fragment else "failed"
        self._log_generation(
            project_id=project.id,
            stage=f"{stage}_scene_expansion",
            status=status,
            provider=self._response_attr(response, "provider"),
            model=self._response_attr(response, "model") or model or "",
            prompt=prompt,
            request_payload={
                "stage": f"{stage}_scene_expansion",
                "missing_characters": missing,
                **(request_metadata or {}),
            },
            raw_response=raw_response,
            normalized={"fragment": fragment, "fragment_characters": len(fragment)},
            validation_error="" if status == "success" else "补写场景过短或调用失败",
        )
        self.session.commit()
        if status != "success":
            return None

        merged = dict(data)
        merged["content"] = "\n\n".join([*before, fragment, *after])
        merged["word_count"] = len(merged["content"])
        merged["length_guard"] = {
            "strategy": "scene_expansion",
            "original_characters": len(content),
            "inserted_characters": len(fragment),
            "minimum_characters": minimum_characters,
            "maximum_characters": maximum_characters,
        }
        return merged

    def _novel_body_quality_problem(
        self,
        data: dict[str, Any],
        *,
        minimum_characters: int = 2800,
        maximum_characters: int | None = None,
    ) -> str:
        content = str(data.get("content") or "").strip()
        if len(content) < minimum_characters:
            return f"正文过短（{len(content)} 字）"
        if maximum_characters is not None and len(content) > maximum_characters:
            return f"正文过长（{len(content)} 字）"
        if len(content.splitlines()) <= 2 and len(content) < 1500:
            return "正文段落过少，疑似摘要"
        paragraphs = [line.strip() for line in content.splitlines() if line.strip()]
        if len(paragraphs) >= 4:
            counts: dict[str, int] = {}
            for paragraph in paragraphs:
                key = re.sub(r"\s+", "", paragraph[:80])
                counts[key] = counts.get(key, 0) + 1
            if max(counts.values(), default=0) >= 3:
                return "出现重复段落，疑似复读"
        sentences = [item.strip() for item in re.split(r"[。！？!?]\s*", content) if item.strip()]
        if len(sentences) >= 8:
            counts: dict[str, int] = {}
            for sentence in sentences:
                key = re.sub(r"\s+", "", sentence[:40])
                if len(key) < 8:
                    continue
                counts[key] = counts.get(key, 0) + 1
            if max(counts.values(), default=0) >= 3:
                return "出现重复句式，疑似复读"
        return ""

    def _wrap_plain_novel_body_response(
        self,
        raw_response: str,
        prompt: str,
        schema_model: type[TModel],
    ) -> dict[str, Any]:
        content = (raw_response or "").strip()
        if not content:
            raise ValueError("模型没有返回可保存的正文内容")
        if content.startswith("```"):
            content = content.strip("`").strip()
            if content.lower().startswith("json"):
                content = content[4:].strip()
        title = ""
        json_body_fields = ("content", "body", "text", "chapter_body", "rewritten_body")
        has_json_body_field = any(f'"{field}"' in content for field in json_body_fields)
        if has_json_body_field:
            title = self._extract_json_string_field(content, "title") or ""
            extracted_content = next(
                (
                    value
                    for field in json_body_fields
                    if (
                        value := (
                            self._extract_loose_json_string_field(content, field)
                            or self._extract_json_string_field(content, field)
                        )
                    )
                ),
                None,
            )
            if extracted_content:
                content = extracted_content.strip()
            else:
                raise ValueError("模型返回了疑似 JSON，但无法解析为章节正文")

        chapter_number = self._extract_json_int_field(raw_response, "chapter_number") or 1
        match = re.search(r"第\s*(\d+)\s*章", prompt or "")
        if not match:
            match = re.search(r'"chapter_number"\s*:\s*(\d+)', prompt or "")
        if match:
            chapter_number = int(match.group(1))

        data = {
            "chapter_number": chapter_number,
            "title": title or f"第 {chapter_number} 章正文",
            "content": content,
            "word_count": len(content),
            "continuity_notes": [],
        }
        try:
            model = schema_model.model_validate(data)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        return model.model_dump()

    def _extract_loose_json_string_field(self, text: str, field: str) -> str | None:
        """Recover a long JSON text field when a compatible model forgot escaping.

        Long Chinese prose sometimes contains literal newlines or ASCII quotes. That
        makes the overall response invalid JSON even though the body itself is usable.
        A following scalar/list field is a much safer end marker than the first quote
        inside the prose, so only use this recovery for known novel-body fields.
        """
        marker = f'"{field}"'
        start = (text or "").find(marker)
        if start < 0:
            return None
        colon = text.find(":", start + len(marker))
        if colon < 0:
            return None
        value_start = colon + 1
        while value_start < len(text) and text[value_start].isspace():
            value_start += 1
        if value_start >= len(text) or text[value_start] != '"':
            return None

        # A valid response puts these fields after content. The delimiter also
        # survives when the model left prose newlines or inner quotes unescaped.
        tail = re.search(
            r',\s*"(?:word_count|continuity_notes|chapter_number|title)"\s*:',
            text[value_start + 1 :],
        )
        if not tail:
            return None
        value_end = value_start + 1 + tail.start()
        value = text[value_start + 1 : value_end].rstrip()
        if value.endswith('"'):
            value = value[:-1]
        value = (
            value.replace(r"\\n", "\n")
            .replace(r"\\r", "\r")
            .replace(r"\\t", "\t")
            .replace(r'\\"', '"')
            .replace(r"\\\\", "\\")
        )
        return value.strip() or None

    def _extract_json_int_field(self, text: str, field: str) -> int | None:
        match = re.search(rf'"{re.escape(field)}"\s*:\s*(\d+)', text or "")
        return int(match.group(1)) if match else None

    def _extract_json_string_field(self, text: str, field: str) -> str | None:
        marker = f'"{field}"'
        start = (text or "").find(marker)
        if start < 0:
            return None
        colon = text.find(":", start + len(marker))
        if colon < 0:
            return None
        pos = colon + 1
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text) or text[pos] != '"':
            return None
        pos += 1

        chars: list[str] = []
        escaped = False
        while pos < len(text):
            ch = text[pos]
            if escaped:
                if ch == "n":
                    chars.append("\n")
                elif ch == "r":
                    chars.append("\r")
                elif ch == "t":
                    chars.append("\t")
                elif ch == "b":
                    chars.append("\b")
                elif ch == "f":
                    chars.append("\f")
                elif ch == "u" and pos + 4 < len(text):
                    hex_value = text[pos + 1 : pos + 5]
                    try:
                        chars.append(chr(int(hex_value, 16)))
                        pos += 4
                    except ValueError:
                        chars.append(ch)
                else:
                    chars.append(ch)
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                return "".join(chars)
            else:
                chars.append(ch)
            pos += 1
        return "".join(chars).strip() or None

    def _extract_json_object(self, content: str, *, allow_local_repair: bool = False) -> dict[str, Any]:
        text = (content or "").strip()
        if text.startswith("```json"):
            text = text[7:].strip()
        if text.startswith("```"):
            text = text[3:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
        candidate = self._json_candidate(text)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            if not allow_local_repair:
                raise
            parsed = self._repair_json_locally(candidate)
        if not isinstance(parsed, dict):
            raise ValueError("模型返回的 JSON 顶层必须是对象")
        return parsed

    def _json_candidate(self, text: str) -> str:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("模型没有返回 JSON 对象")
        return text[start : end + 1]

    def _repair_json_locally(self, text: str) -> dict[str, Any]:
        try:
            from json_repair import repair_json
        except Exception as exc:
            raise ValueError("本地 JSON 修复依赖 json-repair 未安装") from exc

        try:
            repaired = repair_json(text, return_objects=True)
        except Exception as exc:
            raise ValueError(f"本地 JSON 修复失败: {exc}") from exc
        if not isinstance(repaired, dict):
            raise ValueError("本地 JSON 修复结果不是对象")
        return repaired

    def _log_generation(
        self,
        *,
        project_id: str,
        stage: str,
        status: str,
        provider: str,
        model: str,
        prompt: str,
        request_payload: dict[str, Any],
        raw_response: str,
        normalized: dict[str, Any],
        validation_error: str,
    ) -> ProjectGenerationLog:
        log = ProjectGenerationLog(
            project_id=project_id,
            stage=stage,
            provider=provider or "",
            model=model or "",
            status=status,
            prompt=prompt,
            request_json=dumps_json(self._jsonable_request_payload(request_payload)),
            raw_response=raw_response or "",
            normalized_json=dumps_json(normalized),
            validation_error=validation_error or "",
        )
        self.session.add(log)
        return log

    def _jsonable_request_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = dict(payload)
        messages = []
        for message in data.get("messages") or []:
            if isinstance(message, LLMMessage):
                messages.append({"role": message.role, "content": message.content})
            elif isinstance(message, dict):
                messages.append(message)
            else:
                messages.append({"role": getattr(message, "role", ""), "content": getattr(message, "content", "")})
        data["messages"] = messages
        return data

    def _select_novel_chapters(
        self,
        *,
        asset_id: str,
        chapter_ids: list[str],
        chapter_indices: list[int],
    ) -> list[NovelChapter]:
        query = select(NovelChapter).where(NovelChapter.asset_id == asset_id)
        if chapter_ids:
            query = query.where(NovelChapter.id.in_(chapter_ids))
        elif chapter_indices:
            query = query.where(NovelChapter.chapter_index.in_(chapter_indices))
        return self.session.exec(query.order_by(NovelChapter.chapter_index)).all()

    def _read_chapter_samples(self, chapters: list[NovelChapter], max_chars: int = 8000) -> str:
        chunks: list[str] = []
        remaining = max_chars
        for chapter in chapters:
            if remaining <= 0:
                break
            path = Path(chapter.content_path) if chapter.content_path else None
            body = ""
            if path and path.exists() and path.is_file():
                body = path.read_text(encoding="utf-8", errors="ignore")
            if not body:
                body = chapter.chapter_title
            snippet = body[:remaining]
            remaining -= len(snippet)
            chunks.append(f"# {chapter.chapter_title}\n{snippet}")
        return "\n\n".join(chunks)

    def _outline_prompt(self, project: CreativeProject, idea: str, source_sample: str) -> str:
        source = idea or "用户暂未填写创意，请基于项目标题扩展。"
        if source_sample:
            source += f"\n\n参考小说章节节选：\n{source_sample[:8000]}"
        return f"""请根据用户创意生成一份长篇小说/漫画/短剧项目的故事大纲 JSON。

项目类型：{project.project_type}
项目标题：{project.title}
用户创意：
{source}

输出 JSON 对象，字段必须包含：
{{
  "title": "作品标题",
  "genre": ["题材1", "题材2"],
  "logline": "一句话卖点",
  "target_reader": "目标读者",
  "tone": "叙事气质",
  "worldview": "世界观与规则",
  "main_conflict": "主线冲突",
  "themes": ["主题1", "主题2"],
  "characters": [
    {{
      "name": "角色名",
      "role": "定位",
      "age_range": "年龄段",
      "appearance": "脸型、发型、体态、辨识度外貌",
      "costume_hint": "服装、配色、标志物",
      "personality": "性格",
      "background": "人物前史与欲望/创伤来源",
      "goal": "目标",
      "arc": "成长弧光",
      "visual_tags": ["稳定视觉标签1", "稳定视觉标签2"],
      "signature_items": ["标志性物品1", "标志性物品2"],
      "expressions": ["常用表情1", "常用表情2"],
      "poses": ["常用姿态1", "常用姿态2"],
      "visual_consistency": "后续立绘、分镜和漫画生图必须保持一致的脸型、发型、服装、配色和标志物规则",
      "voice": "说话方式、口头禅、台词气质",
      "image_prompt": "可直接用于生成角色设定图的完整提示词，包含年龄、脸型、发型、服装、气质、构图、风格",
      "negative_prompt": "不希望出现在角色图里的元素",
      "portrait_asset_id": "",
      "reference_asset_ids": []
    }}
  ],
  "relationship_map": "主要人物关系",
  "premise": "作品核心前提，说明主角为什么非行动不可",
  "selling_points": ["强卖点1", "强卖点2", "强卖点3"],
  "audience_emotion": "希望读者/观众持续获得的情绪体验",
  "narrative_rules": ["创作规则1", "反套路边界1", "爽点兑现规则1"],
  "locations": [
    {{"name": "核心场景名", "role": "叙事功能", "visual_description": "场景视觉描述", "mood": "氛围", "reusable_asset_note": "可复用素材说明"}}
  ],
  "story_arc": {{
    "beginning": "开局",
    "middle": "中段升级",
    "climax": "高潮",
    "ending_direction": "结局方向"
  }},
  "visual_style": "适合漫画化和短视频化的视觉风格",
  "image_style_prompt": "统一生图风格提示词，供角色图、场景图、分镜图复用",
  "production_notes": ["后续生成脚本/分镜/图片时必须遵守的制作约束"]
}}

要求：
1. 大纲要服务后续章节规划、短剧脚本、漫画分镜和素材库管理；不要只写概念，要写可执行的生产设定。
2. 角色 image_prompt 必须能直接送入生图功能，用来保持人物形象一致。
3. 如果还没有素材库图片，portrait_asset_id 留空字符串，reference_asset_ids 留空数组。"""

    def _chapter_plan_prompt(self, outline: dict[str, Any], chapter_count: int) -> str:
        return f"""请根据下面的故事大纲，生成 {chapter_count} 章/集的连续规划 JSON。

故事大纲：
{dumps_json(outline)}

要求：
1. 每章要推动主线，不要只写氛围。
2. 每章都要有明确目标、冲突、关键事件和结尾钩子。
3. 角色成长和关系变化要连续。
4. 输出严格 JSON，不要 Markdown。

输出格式：
{{
  "chapter_count": {chapter_count},
  "chapters": [
    {{
      "chapter_number": 1,
      "title": "章节标题",
      "goal": "本章叙事目标",
      "conflict": "本章核心冲突",
      "key_events": ["事件1", "事件2"],
      "character_focus": ["角色名"],
      "ending_hook": "结尾钩子",
      "status": "planned"
    }}
  ]
}}"""

    def _chapter_plan_extension_prompt(
        self,
        *,
        outline: dict[str, Any],
        existing_plan: dict[str, Any],
        start_chapter: int,
        target_chapter_count: int,
    ) -> str:
        existing_chapters = existing_plan.get("chapters") if isinstance(existing_plan, dict) else []
        previous_chapter = existing_chapters[-1] if isinstance(existing_chapters, list) and existing_chapters else {}
        return f"""请为下列已完成规划的故事续写第 {start_chapter}-{target_chapter_count} 章的连续规划 JSON。

故事大纲：
{dumps_json(outline)}

上一章（第 {start_chapter - 1} 章，已定稿，不可改写）：
{dumps_json(previous_chapter)}

要求：
1. 只输出第 {start_chapter} 到第 {target_chapter_count} 章，不要重写或复述已有章节。
2. 第一章必须承接已有最后一章的 ending_hook；后续章节必须完成大纲中尚未兑现的终局、人物弧光和主题。
3. 每章必须有明确目标、冲突、关键事件、角色焦点和结尾钩子，不能用“继续调查”一类空泛推进。
4. chapter_number 必须依次为 {start_chapter} 到 {target_chapter_count}。
5. 输出严格 JSON，不要 Markdown。

输出格式：
{{
  "chapter_count": {target_chapter_count - start_chapter + 1},
  "chapters": [
    {{
      "chapter_number": {start_chapter},
      "title": "章节标题",
      "goal": "本章叙事目标",
      "conflict": "本章核心冲突",
      "key_events": ["事件1", "事件2"],
      "character_focus": ["角色名"],
      "ending_hook": "结尾钩子",
      "status": "planned"
    }}
  ]
}}"""

    def _script_prompt(
        self,
        outline: dict[str, Any],
        chapter_plan: dict[str, Any],
        chapter_number: int,
        reference_assets: list[dict[str, Any]] | None = None,
    ) -> str:
        selected = self._chapter_plan_item(chapter_plan, chapter_number)
        return f"""请把指定章节改写成短剧单集脚本 JSON。

故事大纲：
{dumps_json(outline)}

当前章节：
{dumps_json(selected)}

项目参考卡集合（scene.reference_asset_ids 只能从这些 asset_id 中选择，不要编造 ID）：
{dumps_json(reference_assets or [])}

要求：
1. 开头 5 秒必须有钩子。
2. 场景适合 60-120 秒竖屏短剧。
3. 每个 scene 都要给出可用于 AI 生图的 image_prompt。
4. 每个 scene 根据角色、地点、道具、画风选择 reference_asset_ids，并用 reference_notes 说明为什么选这些参考图。
5. 输出严格 JSON。

输出格式：
{{
  "episode_number": {chapter_number},
  "title": "单集标题",
  "duration_target_seconds": 90,
  "hook": "开头钩子",
  "scenes": [
    {{
      "scene_number": 1,
      "location": "地点",
      "characters": ["角色"],
      "action": "动作与剧情",
      "dialogue": [{{"character": "角色", "line": "台词"}}],
      "camera_hint": "镜头建议",
      "emotion": "情绪",
      "image_prompt": "画面提示词",
      "reference_asset_ids": ["项目参考卡 asset_id"],
      "reference_notes": ["中文说明：这张参考图用于角色/背景/画风/道具"]
    }}
  ],
  "ending_hook": "结尾钩子"
}}"""

    def _chapter_plan_item(self, chapter_plan: dict[str, Any], chapter_number: int) -> dict[str, Any]:
        chapters = chapter_plan.get("chapters") or []
        return next(
            (item for item in chapters if int(item.get("chapter_number") or 0) == chapter_number),
            {},
        )

    def _chapter_outline_prompt(
        self,
        outline: dict[str, Any],
        chapter_plan: dict[str, Any],
        current_chapter: dict[str, Any],
        chapter_number: int,
        previous_context: str,
        project_bible_context: str = "",
    ) -> str:
        return f"""请根据故事大纲和章节规划，生成第 {chapter_number} 章/集的单话细纲 JSON。

故事大纲：
{dumps_json(outline)}

章节规划：
{dumps_json(chapter_plan)}

当前章节：
{dumps_json(current_chapter)}

前文上下文：
{previous_context or "暂无"}

已锁定项目圣经/世界资产：
{project_bible_context or "暂无"}

要求：
1. 单话细纲要比章节规划更细，必须能直接服务后续小说正文、短剧脚本、漫画分镜和生图。
2. 顶层必须写清 summary、objective、keywords、key_dialogues、foreshadowing、ending_hook、continuity_notes，不能只写空泛总结。
3. scenes 建议 4-8 个，每个 scene 必须有 purpose/scene_role/objective/conflict/beats/action/key_dialogue/emotion/emotional_turn/visual_focus/shot_design/image_prompt。
4. beats 是 2-5 条具体节拍，按镜头或剧情动作顺序写，不要写概念词。
5. key_dialogues 写可直接进入正文或漫画气泡的关键台词。
6. image_prompt 必须是镜头级中文提示词，至少包含：角色外观或身份、地点、动作、表情、构图景别、光线色调、氛围、漫画/影视风格、一致性要求；不要只写一句剧情。
7. foreshadowing 和 continuity_notes 要帮助后续章节保持连续。
8. 如果“已锁定项目圣经/世界资产”不为空，必须优先遵守这些设定，不能改写世界规则、地点约束、画风约束和连续性事实。
9. 输出严格 JSON，不要 Markdown。

输出格式：
{{
  "chapter_number": {chapter_number},
  "title": "单话标题",
  "summary": "本章完整摘要",
  "objective": "本章叙事目标",
  "keywords": ["本话关键词"],
  "scenes": [
    {{
      "scene_number": 1,
      "title": "场景标题",
      "location": "地点",
      "time_of_day": "时间段",
      "weather": "天气/光线环境",
      "characters": ["角色"],
      "purpose": "场景作用",
      "scene_role": "开场钩子/冲突升级/反转/情绪落点/结尾钩子",
      "objective": "场景目标",
      "conflict": "场景冲突",
      "beats": ["具体节拍1", "具体节拍2"],
      "action": "具体剧情动作",
      "key_dialogue": "本场关键台词",
      "emotion": "主要情绪",
      "emotional_turn": "情绪变化",
      "visual_focus": "画面核心看点",
      "props": ["关键道具1", "关键道具2"],
      "spatial_axis": "空间轴线和人物朝向",
      "character_positions": "角色站位/坐位/前后景关系",
      "movement_path": "角色或镜头移动路线",
      "shot_design": "镜头/构图/景别设计",
      "image_prompt": "可直接用于生成场景概念图的详细提示词"
    }}
  ],
  "key_dialogues": ["关键台词或台词方向"],
  "foreshadowing": ["伏笔"],
  "ending_hook": "结尾钩子",
  "continuity_notes": ["连续性备注"]
}}"""

    def _chapter_outline_scenes_prompt(
        self,
        *,
        outline: dict[str, Any],
        chapter_plan: dict[str, Any],
        current_chapter: dict[str, Any],
        chapter_outline: dict[str, Any],
    ) -> str:
        chapter_number = chapter_outline.get("chapter_number") or current_chapter.get("chapter_number") or 1
        return f"""请只重生成第 {chapter_number} 章/集单话细纲里的 scenes JSON，不要改动标题、摘要、写作目标、关键台词、伏笔和连续性说明。

故事大纲：
{dumps_json(outline)}

章节规划：
{dumps_json(chapter_plan)}

当前章节：
{dumps_json(current_chapter)}

当前单话细纲顶层信息：
{dumps_json({k: v for k, v in chapter_outline.items() if k != "scenes"})}

要求：
1. 只输出 JSON 对象，顶层只有 scenes 字段。
2. scenes 建议 4-8 个，必须覆盖当前单话摘要和写作目标。
3. 每个 scene 必须包含：scene_number、title、location、characters、purpose、scene_role、objective、conflict、beats、action、key_dialogue、emotion、emotional_turn、visual_focus、shot_design、image_prompt。
4. beats 写 2-5 条具体节拍，按剧情动作顺序排列。
5. image_prompt 必须是镜头级中文提示词，包含角色外观或身份、地点、动作、表情、构图景别、光线色调、氛围、漫画/影视风格和一致性要求。
6. 不要输出 Markdown，不要输出 scenes 以外字段。

输出格式：
{{
  "scenes": [
    {{
      "scene_number": 1,
      "title": "场景标题",
      "location": "地点 / 时间 / 氛围",
      "characters": ["角色"],
      "purpose": "场景作用",
      "scene_role": "开场钩子/冲突升级/反转/情绪落点/结尾钩子",
      "objective": "场景目标",
      "conflict": "场景冲突",
      "beats": ["具体节拍1", "具体节拍2"],
      "action": "具体剧情动作",
      "key_dialogue": "关键台词",
      "emotion": "主要情绪",
      "emotional_turn": "情绪变化",
      "visual_focus": "画面核心看点",
      "shot_design": "镜头/构图/景别设计",
      "image_prompt": "详细生图提示词"
    }}
  ]
}}"""

    def _novel_body_prompt(
        self,
        outline: dict[str, Any],
        chapter_plan: dict[str, Any],
        chapter_outline: dict[str, Any],
        chapter_number: int,
        project_context_pack: str,
    ) -> str:
        return f"""请根据单话细纲生成第 {chapter_number} 章小说正文 JSON。

故事大纲：
{dumps_json(outline)}

章节规划：
{dumps_json(chapter_plan)}

当前单话细纲：
{dumps_json(chapter_outline)}

项目连续性上下文：
{project_context_pack or "暂无"}

要求：
1. content 字段输出完整小说正文，不要只写摘要；目标 3000-4500 个中文字符，最低不要低于 2800 字。
2. 正文要遵守大纲中的人物设定、视觉风格、世界规则和连续性备注。项目连续性上下文中的“已锁定”事实不可新增、改写或推翻；前文事件必须被承接。
3. 保持网文/短剧改编友好的节奏：开头有钩子，中段有推进，结尾留悬念。
4. 可以有对白、动作和心理描写，但不要输出 Markdown 标题。
5. 保留舒适分段，每个主要场景都要展开成可阅读段落。
6. 输出严格 JSON，不要 Markdown。

输出格式：
{{
  "chapter_number": {chapter_number},
  "title": "章节标题",
  "content": "完整小说正文",
  "word_count": 0,
  "continuity_notes": ["给下一章或拆页使用的连续性备注"]
}}"""

    def _normalize_writer_room_step(self, step: str) -> str:
        aliases = {
            "beats": "scene_beats",
            "scene-beats": "scene_beats",
            "rehearsal": "character_rehearsal",
            "character-rehearsal": "character_rehearsal",
            "draft": "prose_draft",
            "prose-draft": "prose_draft",
            "humanize": "prose_humanized",
            "humanized": "prose_humanized",
            "prose-humanized": "prose_humanized",
            "review": "prose_review",
            "prose-review": "prose_review",
            "rewrite": "prose_rewrite",
            "prose-rewrite": "prose_rewrite",
        }
        normalized = aliases.get(str(step or "").strip(), str(step or "").strip())
        allowed = {
            "scene_beats",
            "character_rehearsal",
            "prose_draft",
            "prose_humanized",
            "prose_review",
            "prose_rewrite",
        }
        if normalized not in allowed:
            raise ValueError(f"不支持的写作室步骤: {step}")
        return normalized

    def _writer_room_schema(self, step: str) -> type[BaseModel]:
        if step == "scene_beats":
            return WriterRoomSceneBeatsSchema
        if step == "character_rehearsal":
            return WriterRoomCharacterRehearsalSchema
        if step == "prose_review":
            return WriterRoomProseReviewSchema
        return NovelBodySchema

    def _writer_room_context(
        self,
        *,
        project_id: str,
        step: str,
        chapter_number: int,
        source_content_id: str | None = None,
        selected_text: str | None = None,
        context_pack: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        project = self._require_project(project_id)
        outline = loads_json(project.outline_json)
        chapter_plan = loads_json(project.chapter_plan_json)
        chapter_outline = self._latest_content(project_id, "chapter_outline", chapter_number)
        novel_body = self._latest_content(project_id, "novel_body", chapter_number)
        scene_beats = self._latest_content(project_id, "scene_beats", chapter_number)
        rehearsal = self._latest_content(project_id, "character_rehearsal", chapter_number)
        draft = self._latest_content(project_id, "prose_draft", chapter_number)
        humanized = self._latest_content(project_id, "prose_humanized", chapter_number)
        source = self.session.get(ProjectContent, source_content_id) if source_content_id else None
        if source and source.project_id != project_id:
            raise ValueError("写作室源内容不属于当前项目")

        current_chapter = {}
        for item in chapter_plan.get("chapters") or []:
            if isinstance(item, dict) and int(item.get("chapter_number") or 0) == int(chapter_number):
                current_chapter = item
                break

        # Writer Room is a real candidate pipeline, not a collection of
        # independent "latest content" lookups. Keep the direct upstream
        # candidate as provenance, while prose-only steps still use a prose
        # source for length guards and full-text editing.
        upstream_candidates = {
            "scene_beats": [source, chapter_outline],
            "character_rehearsal": [source, scene_beats, chapter_outline],
            "prose_draft": [source, rehearsal, scene_beats, chapter_outline],
            "prose_humanized": [source, draft, novel_body],
            "prose_review": [source, humanized, draft, novel_body],
            "prose_rewrite": [source, humanized, draft, novel_body],
        }.get(step, [source, chapter_outline])
        upstream_source = next((item for item in upstream_candidates if item is not None), None)
        prose_candidates = {
            "prose_humanized": [source, draft, novel_body],
            "prose_review": [source, humanized, draft, novel_body],
            "prose_rewrite": [source, humanized, draft, novel_body],
        }.get(step, [])
        prose_source = next(
            (
                item
                for item in prose_candidates
                if item is not None and item.content_type in {"novel_body", "prose_draft", "prose_humanized", "prose_rewrite"}
            ),
            None,
        )
        source_text = prose_source.text_content if prose_source else ""
        # A rewrite must follow the review of the exact version being rewritten.
        # Falling back to the newest chapter review can mix an old/empty candidate
        # with a newer body and produces contradictory rewrite instructions.
        review = (
            self._latest_writer_room_review_for_source(
                project_id,
                chapter_number,
                prose_source.id if prose_source else "",
            )
            if step == "prose_rewrite"
            else self._latest_content(project_id, "prose_review", chapter_number)
        )
        context_pack = context_pack or self._creative_context_pack(
            project_id,
            chapter_number,
            persist=True,
            stage=f"writer_room:{step}",
            source_content_id=source_content_id,
        )
        return {
            "outline": outline,
            "chapter_plan": chapter_plan,
            "current_chapter": current_chapter,
            "chapter_outline": loads_json(chapter_outline.data_json) if chapter_outline else {},
            "chapter_outline_id": chapter_outline.id if chapter_outline else "",
            "novel_body": loads_json(novel_body.data_json) if novel_body else {},
            "novel_body_text": novel_body.text_content if novel_body else "",
            "scene_beats": loads_json(scene_beats.data_json) if scene_beats else {},
            "character_rehearsal": loads_json(rehearsal.data_json) if rehearsal else {},
            "prose_draft": loads_json(draft.data_json) if draft else {},
            "prose_humanized": loads_json(humanized.data_json) if humanized else {},
            "prose_review": loads_json(review.data_json) if review else {},
            "source_content_id": upstream_source.id if upstream_source else "",
            "source_content_type": upstream_source.content_type if upstream_source else "",
            "source_content_version": upstream_source.version if upstream_source else 0,
            "prose_source_content_id": prose_source.id if prose_source else "",
            "prose_source_content_type": prose_source.content_type if prose_source else "",
            "prose_source_content_version": prose_source.version if prose_source else 0,
            "source_word_count": len("".join(source_text.split())),
            "source_text": source_text,
            "source_json": loads_json(prose_source.data_json) if prose_source else {},
            "selected_text": selected_text or "",
            "previous_context": context_pack["previous_context"],
            "project_context_pack": context_pack["text"],
            "locked_project_bible_context": context_pack["locked_project_bible_context"],
            "context_pack_metadata": context_pack["metadata"],
            "context_snapshot_id": context_pack.get("snapshot_id") or context_pack["metadata"].get("context_snapshot_id", ""),
        }

    def _writer_room_prompt_variables(
        self,
        *,
        project: CreativeProject,
        chapter_number: int,
        context: dict[str, Any],
        instruction: str,
        selected_text: str = "",
    ) -> dict[str, Any]:
        return {
            "project_title": project.title,
            "project_type": project.project_type,
            "chapter_number": chapter_number,
            "outline_json": dumps_json(context.get("outline")),
            "chapter_plan_json": dumps_json(context.get("chapter_plan")),
            "current_chapter_json": dumps_json(context.get("current_chapter")),
            "chapter_outline_json": dumps_json(context.get("chapter_outline")),
            "scene_beats_json": dumps_json(context.get("scene_beats")),
            "character_rehearsal_json": dumps_json(context.get("character_rehearsal")),
            "source_json": dumps_json(context.get("source_json")),
            "source_text": context.get("source_text") or context.get("novel_body_text") or "",
            "source_content_type": context.get("source_content_type") or "",
            "source_content_version": context.get("source_content_version") or 0,
            "source_word_count": context.get("source_word_count") or 0,
            "selected_text": selected_text or context.get("selected_text") or "",
            "prose_review_json": dumps_json(context.get("prose_review")),
            "previous_context": context.get("previous_context") or "暂无",
            "project_context_pack": context.get("project_context_pack") or "暂无",
            "locked_project_bible_context": context.get("locked_project_bible_context") or "暂无",
            "instruction": instruction or "",
        }

    def _writer_room_prompt(
        self,
        *,
        project: CreativeProject,
        step: str,
        chapter_number: int,
        context: dict[str, Any],
        instruction: str,
    ) -> str:
        variables = self._writer_room_prompt_variables(
            project=project,
            chapter_number=chapter_number,
            context=context,
            instruction=instruction,
        )
        common = f"""项目：{project.title}
第 {chapter_number} 章

故事大纲：
{variables["outline_json"]}

章节规划：
{variables["chapter_plan_json"]}

当前章节细纲：
{variables["chapter_outline_json"]}

前文上下文：
{variables["previous_context"]}

项目连续性上下文：
{variables["project_context_pack"]}

约束：已锁定项目事实不可改写或推翻；前文事件必须承接，不能让角色获得前文未得到的信息。
"""
        if step in {"prose_draft", "prose_humanized", "prose_rewrite"}:
            common += "\n\n" + self._writer_room_prose_style_contract() + "\n"
        if step == "prose_rewrite":
            requested_minimum = writer_room_requested_minimum_characters(instruction)
            requested_maximum = writer_room_requested_maximum_characters(instruction)
            if requested_minimum is not None:
                target = requested_minimum
                range_text = f"不少于 {requested_minimum} 个中文字符"
                if requested_maximum is not None:
                    target = requested_minimum + (requested_maximum - requested_minimum) // 2
                    range_text = f"{requested_minimum}-{requested_maximum} 个中文字符"
                common += f"""

硬性篇幅契约：最终 content 必须为 {range_text}，建议先按约 {target} 个字符规划场景和段落。提交前自行检查篇幅；不足时补一个推动关系或线索的完整场景，超出时删减解释和重复信息，不能删掉细纲事件或用摘要替代正文。服务端会拒绝区间外的候选。
"""

        if step == "scene_beats":
            return common + """请作为导演，把本章拆成可写正文的场景节拍 JSON。
要求：
1. 每个场景都要有目标、阻碍、冲突压力、动作节拍、潜台词、感官锚点和转折。
2. 不要写泛泛摘要，要写作者下一步能直接展开成正文的戏。
3. 输出严格 JSON，不要 Markdown。
格式：
{
  "chapter_number": 1,
  "title": "标题",
  "summary": "本章戏剧推进摘要",
  "scene_beats": [
    {
      "scene_number": 1,
      "title": "场景名",
      "purpose": "场景功能",
      "location": "地点",
      "characters": ["角色"],
      "dramatic_question": "这一场观众想知道的问题",
      "character_wants": ["角色想要什么"],
      "obstacle": "阻碍",
      "conflict_pressure": "冲突压力",
      "action_beats": ["具体动作节拍"],
      "subtext": "台词背后的真实意思",
      "sensory_anchors": ["可写进正文的物件/声音/触感/气味"],
      "turning_point": "转折",
      "hook": "场景尾钩子"
    }
  ],
  "continuity_notes": ["连续性备注"]
}"""
        if step == "character_rehearsal":
            return common + f"""场景节拍：
{variables["scene_beats_json"]}

请作为角色演绎室，让本章关键角色按自己的欲望、恐惧、已知信息和隐瞒信息先“演一遍”。
要求：
1. 角色不能替作者解释主题，只能从自身利益和情绪出发。
2. 输出能直接喂给正文作者的动作、对白方向和潜台词。
3. 输出严格 JSON。
格式：
{{
  "chapter_number": {chapter_number},
  "title": "标题",
  "scene_rehearsals": [{{"scene_number": 1, "conflict": "这场角色如何互相顶住", "usable_moments": ["可写瞬间"]}}],
  "character_reactions": [
    {{"character": "角色", "public_goal": "表面目标", "private_goal": "真实目标", "fear": "恐惧", "knows": "已知", "hides": "隐瞒", "likely_action": "会做什么", "likely_dialogue": ["可能说的话"], "subtext": "潜台词", "voice_rules": ["说话规则"]}}
  ],
  "usable_conflicts": ["可写冲突"],
  "continuity_notes": ["连续性备注"]
}}"""
        if step == "prose_draft":
            return common + f"""场景节拍：
{variables["scene_beats_json"]}

角色演绎：
{variables["character_rehearsal_json"]}

请写成本章小说正文初稿 JSON。
要求：
1. content 是完整正文，不是摘要，目标 3000-4500 中文字符。
2. 开头有钩子，中段有动作推进、对白、误解或反转，结尾留悬念。
3. 多写具体动作、物件互动、环境细节和潜台词，少写“他意识到/她感到/空气仿佛”这类泛化句。
4. 保留舒适分段，不要 Markdown。
5. 若本章导致角色或世界状态变化（升级、习得/遗忘技能、关系值增减、世界倒计时推进等），在 state_changes 中输出增量，每条含 scope（"character:<角色ID>" 或 "world"）、key（键名）、op（set/add/remove）、value（新值或增量）；没有变化则给空数组。不要改静态设定或已锁定事实。
格式：{{"chapter_number": {chapter_number}, "title": "章节标题", "content": "完整正文", "word_count": 0, "continuity_notes": ["备注"], "state_changes": [{{"scope":"character:角色ID","key":"level","op":"add","value":1}}]}}"""
        if step == "prose_humanized":
            return common + f"""待润色正文：
{variables["source_text"]}

来源：{variables["source_content_type"]} v{variables["source_content_version"]}，约 {variables["source_word_count"]} 字

用户额外要求：
{instruction or "无"}

请作为人味润色编辑，重写正文并输出 JSON。
要求：
1. 保留剧情事实、角色关系、场景顺序、有效信息和原有篇幅，不得把完整章节压缩成摘要。
2. 删掉解释性废话，把直接情绪改成动作、停顿、视线、物件互动和对白潜台词。
3. 改掉重复句式和万能比喻；句长要有变化，段落要有呼吸。
4. 除非用户明确要求增删篇幅，润色后的 content 必须保持在源稿字数的 90%-110% 之间；信息密度可以提升，但不能靠删戏压缩。
5. 不要只给建议，直接输出完整润色后的正文。
格式：{{"chapter_number": {chapter_number}, "title": "章节标题", "content": "完整润色正文", "word_count": 0, "continuity_notes": ["备注"], "state_changes": []}}"""
        if step == "prose_review":
            return common + f"""待审稿正文：
{variables["source_text"]}

请作为网文主编审稿，找出正文里“不像人写”的地方并输出 JSON。
要求：
1. 问题必须具体到段落、场景或句式位置，并在 location 或 problem 中写出本稿实际出现的短语、动作、对白或段落功能；不能用“全文”“第 X 段”“有 AI 味”这类无证据结论。
2. 必须覆盖：节奏、逻辑、角色声音、情绪连续性、爽点/钩子、AI腔。
3. quality_tags 输出 3-8 个短标签，例如“解释过密”“动作不足”“对白顺口”“钩子偏弱”。
4. ai_smell_checks 必须逐项检查：直接情绪标签、泛化形容词、万能比喻、重复句式、缺少物件互动、角色声音漂移、说明替代戏剧动作。
5. rewrite_instruction 要能直接用于下一轮重写。
6. quality_tags、ai_smell_checks、strengths、rewrite_plan 都必须是字符串数组。不要把检查项写成对象、字典、评分表或嵌套 JSON。
7. 只评价正文中真实存在的句子，不要把上一个版本的问题移植到本稿。系统、剧本、存在值是本书允许的设定词；只有它们替代人物行动、读起来像技术说明时才算 AI 腔。
8. 评分校准：完整、有场景推进、人物关系和章末行动的正文以 70 分为基线；只有逻辑断裂、人物动机矛盾、关键线索凭空出现、严重重复或无法阅读才判 high。普通措辞偏好只能记为 medium/low，不能单独让全文不合格。
9. approval_recommendation 必须明确填“建议提升”或“建议重写”，并与 overall_score 一致：70 分以上且无 high 问题才建议提升。即使建议提升，也必须写出至少两条 strengths 和两条实际检查结果，说明为什么本稿通过。
10. 若正文确立了值得后续锁定的连续性事实（如角色固定特征/关系、地点规则、带约束的物件、关键事件结果），在 continuity_candidates 中输出，最多 5 条；没有则给空数组。每条必须含 entity_type（character/place/item/event/other）、entity_name、claim（事实断言）、evidence_excerpt（正文证据片段）、severity（info/low/medium/high）、suggested_action（create_fact/merge/ignore）、target_fact_type（world_asset/project_bible）。不要把主观评价或待修问题写成候选；候选是“已经成立、后续章节不能自相矛盾”的事实。
格式：
{{
  "chapter_number": {chapter_number},
  "title": "标题",
  "overall_score": 0,
  "ai_smell_score": 0,
  "quality_tags": ["质量标签"],
  "ai_smell_checks": ["AI味检查项"],
  "strengths": ["优点"],
  "issues": [
    {{"severity": "high/medium/low", "category": "AI腔/节奏/逻辑/角色声音/情绪/钩子", "location": "位置", "problem": "问题", "suggestion": "建议", "rewrite_instruction": "重写指令"}}
  ],
  "rewrite_plan": ["重写计划"],
  "approval_recommendation": "是否建议提升为正文",
  "continuity_candidates": [
    {{"entity_type": "character", "entity_name": "角色名", "claim": "已确立的事实断言", "evidence_excerpt": "正文证据片段", "severity": "info", "suggested_action": "create_fact", "target_fact_type": "world_asset"}}
  ]
}}"""
        return common + f"""待重写正文：
{variables["source_text"]}

局部选段（如果为空则整章重写）：
{variables["selected_text"] or "无"}

审稿意见：
{variables["prose_review_json"]}

用户额外要求：
{instruction or "无"}

请作为重写作者，根据审稿意见输出完整重写正文 JSON。
要求：
1. 只改写表达、节奏、冲突呈现和人物反应，不擅自改主线事实。
2. 优先修复 high/medium 问题。
3. 如果提供了“局部选段”，只重写该选段相关段落，并把修好的段落替换回全文；content 仍必须输出完整正文。
4. 输出完整正文，不要只输出片段或解释。
格式：{{"chapter_number": {chapter_number}, "title": "章节标题", "content": "完整重写正文", "word_count": 0, "continuity_notes": ["备注"], "state_changes": []}}"""

    def _normalize_writer_room_review(self, data: dict[str, Any]) -> dict[str, Any]:
        issues = data.get("issues")
        if not isinstance(issues, list):
            issues = []
        if not issues and isinstance(data.get("review"), dict) and isinstance(data["review"].get("issues"), list):
            issues = data["review"]["issues"]
        chapter_review = data.get("chapter_review") if isinstance(data.get("chapter_review"), dict) else {}
        if not issues and isinstance(chapter_review.get("issues"), list):
            issues = chapter_review["issues"]
        issues = [item for item in issues if isinstance(item, dict)]
        normalized_issues = []
        for index, item in enumerate(issues, start=1):
            normalized_issues.append(
                {
                    "severity": item.get("severity") or ("high" if index <= 3 else "medium"),
                    "category": item.get("category") or item.get("type") or item.get("problem_type") or "AI腔",
                    "location": item.get("location") or item.get("position") or f"审稿问题 {index}",
                    "problem": item.get("problem") or item.get("description") or item.get("issue") or item.get("detail") or "",
                    "suggestion": item.get("suggestion") or item.get("detail") or "",
                    "rewrite_instruction": item.get("rewrite_instruction") or item.get("suggestion") or item.get("detail") or item.get("description") or "",
                }
            )
        issues = normalized_issues

        fallback_instruction = str(data.get("rewrite_instruction") or "").strip()
        checks = data.get("ai_smell_checks") if isinstance(data.get("ai_smell_checks"), list) else []
        if not issues and checks:
            for index, check in enumerate(checks, start=1):
                text = str(check).strip()
                if not text:
                    continue
                location = ""
                problem = text
                if text.startswith("[") and "]" in text:
                    location, problem = text[1:].split("]", 1)
                    problem = problem.strip(" -：: ")
                issues.append(
                    {
                        # A checklist signal is not a verified blocking defect.
                        # Only the editor's explicit issues may be marked high.
                        "severity": "medium",
                        "category": "AI腔",
                        "location": location or f"AI味检查 {index}",
                        "problem": problem,
                        "suggestion": fallback_instruction or "压低解释，改成动作、物件互动、停顿和对白潜台词。",
                        "rewrite_instruction": fallback_instruction or problem,
                    }
                )

        if fallback_instruction and not data.get("rewrite_plan"):
            data["rewrite_plan"] = [line.strip() for line in fallback_instruction.splitlines() if line.strip()]
        if not data.get("quality_tags") and issues:
            data["quality_tags"] = list({str(item.get("category") or "质量问题") for item in issues})
        if not data.get("overall_score") and issues:
            high_count = sum(1 for item in issues if str(item.get("severity", "")).lower() == "high")
            data["overall_score"] = max(35, 75 - high_count * 8 - max(0, len(issues) - high_count) * 4)
        if not data.get("ai_smell_score") and (checks or issues):
            data["ai_smell_score"] = min(95, 45 + len(checks or issues) * 6)
        recommendation = str(data.get("approval_recommendation") or "").strip()
        if recommendation and recommendation not in {"建议提升", "建议重写"}:
            if "重写" in recommendation:
                data["approval_recommendation"] = "建议重写"
            elif "提升" in recommendation:
                data["approval_recommendation"] = "建议提升"
            else:
                data["approval_recommendation"] = ""
        if not str(data.get("approval_recommendation") or "").strip():
            has_high_issue = any(str(item.get("severity") or "").lower() == "high" for item in issues)
            has_editorial_evidence = bool(
                issues
                or checks
                or [item for item in data.get("quality_tags") or [] if str(item).strip()]
                or [item for item in data.get("strengths") or [] if str(item).strip()]
            )
            # The editorial contract treats a complete, readable chapter as a
            # 70-point baseline. Medium and low style notes remain visible for
            # a human decision, but cannot turn into a fake blocking failure.
            # An empty JSON is not editorial evidence and must never receive
            # that baseline or a promotion recommendation.
            if has_editorial_evidence and not has_high_issue and int(data.get("overall_score") or 0) < 70:
                data["overall_score"] = 70
            data["approval_recommendation"] = (
                "建议提升" if int(data.get("overall_score") or 0) >= 70 and not has_high_issue else "建议重写"
            )
        data["issues"] = issues
        return data

    @staticmethod
    def _writer_room_review_has_substance(data: dict[str, Any]) -> bool:
        """Reject empty review JSON before it can masquerade as a passing score."""
        def nonempty_strings(value: Any) -> list[str]:
            if not isinstance(value, list):
                return []
            return [str(item).strip() for item in value if str(item).strip()]

        tags = nonempty_strings(data.get("quality_tags"))
        checks = nonempty_strings(data.get("ai_smell_checks"))
        strengths = nonempty_strings(data.get("strengths"))
        issues = [
            item
            for item in data.get("issues") or []
            if isinstance(item, dict)
            and str(item.get("location") or "").strip()
            and str(item.get("problem") or "").strip()
            and str(item.get("rewrite_instruction") or item.get("suggestion") or "").strip()
        ]
        recommendation = str(data.get("approval_recommendation") or "").strip()
        score = int(data.get("overall_score") or 0)
        return (
            score > 0
            and recommendation in {"建议提升", "建议重写"}
            and len(tags) >= 2
            and len(checks) >= 2
            and bool(strengths or issues)
        )

    def _writer_room_text(self, step: str, data: dict[str, Any]) -> str:
        if step == "scene_beats":
            lines = [data.get("summary") or ""]
            for item in data.get("scene_beats") or []:
                lines.append(f"场景 {item.get('scene_number')}: {item.get('title')} - {item.get('purpose')}")
                lines.extend(f"- {beat}" for beat in item.get("action_beats") or [])
            return "\n".join(line for line in lines if str(line).strip())
        if step == "character_rehearsal":
            lines = []
            for item in data.get("character_reactions") or []:
                lines.append(f"{item.get('character')}: {item.get('private_goal') or item.get('public_goal')}")
                if item.get("subtext"):
                    lines.append(f"潜台词：{item.get('subtext')}")
            return "\n".join(lines) or dumps_json(data)
        if step == "prose_review":
            lines = [
                f"总分：{data.get('overall_score', 0)}",
                f"AI腔：{data.get('ai_smell_score', 0)}",
            ]
            tags = data.get("quality_tags") or []
            if tags:
                lines.append("质量标签：" + "、".join(str(item) for item in tags))
            checks = data.get("ai_smell_checks") or []
            if checks:
                lines.append("AI味检查：" + "；".join(str(item) for item in checks))
            for issue in data.get("issues") or []:
                lines.append(f"[{issue.get('severity')}] {issue.get('category')} {issue.get('location')}: {issue.get('problem')}")
                if issue.get("rewrite_instruction"):
                    lines.append(f"重写：{issue.get('rewrite_instruction')}")
            return "\n".join(lines)
        return str(data.get("content") or dumps_json(data))

    def _writer_room_prose_style_contract(self) -> str:
        """Shared prose constraints for every Writer Room drafting pass."""
        return """写作质感硬约束：
1. 写成连载网文正文，不写提纲、审稿意见、设定说明或人物小传。每一场至少落到一个可触碰的物件、一个身体动作和一次具体选择。
2. 场景按“人物想做什么 -> 被什么打断/阻碍 -> 怎么临场应对 -> 付出什么后果”推进；不能用一段解释替代一场戏。
3. 对白必须互相接得住：有人打断、回避、答非所问、停顿或改口，而不是轮流发表完整观点。人物只说自己当下会说的话。
4. 情绪优先通过手、呼吸、视线、姿势、环境和物件表现；少用“他意识到、她感到、空气仿佛、某种、无法形容”等泛化句式。
5. 允许保留本书必要的“系统/剧本/存在值”等设定名词，但它们只能压迫人物、打断行动或带来后果；不要把代码、算法、接口、渲染、帧、模型、数据、3D打印、解剖术语写成旁白解释。
6. 一段只做一件事：推进动作、给出反应或改变关系。每 500-800 字至少发生一次可见变化，例如证据被夺走、话被截断、立场翻转、门被推开、选择落地；不要用连续奇观或术语清单充篇幅。
7. 不写工整口号、万能比喻或结论先行的推理报告。推理只说读者当下需要的一两步，并立刻用对手的反应、物件变化或代价验证；短句用于压力和转折，长句只服务于具体观察。
8. 章节结尾必须让人物已经做出一个会改变下一章处境的行动或选择，而不是仅用抽象感叹收尾。"""

    def _writer_room_title(self, step: str, chapter_number: int) -> str:
        labels = {
            "scene_beats": "场景节拍",
            "character_rehearsal": "角色演绎",
            "prose_draft": "正文初稿",
            "prose_humanized": "人味润色",
            "prose_review": "主编审稿",
            "prose_rewrite": "定向重写",
        }
        return f"第 {chapter_number} 章{labels.get(step, step)}"

    def _refine_novel_body_prompt(
        self,
        *,
        project: CreativeProject,
        content: ProjectContent,
        body_data: dict[str, Any],
        outline_context: dict[str, Any],
        instruction: str,
        project_context_pack: str,
    ) -> str:
        chapter_number = content.chapter_number or content.episode_number or body_data.get("chapter_number") or 1
        return f"""请根据用户的中文修改要求，微调第 {chapter_number} 章小说正文，并输出严格 JSON。

项目标题：{project.title}

当前单话细纲：
{dumps_json(outline_context)}

项目连续性上下文：
{project_context_pack or "暂无"}

当前正文：
{content.text_content or body_data.get("content", "")}

用户中文修改要求：
{instruction}

要求：
1. 只修改正文，不要输出解释、Markdown 或代码块；如果用户没有要求压缩，目标 3000-4500 个中文字符，最低不要低于 2800 字。
2. 保留原有主线、人物身份、连续性和重要伏笔，按照用户要求加强或压缩；已锁定项目事实不可改写或推翻，前文事件必须承接。
3. 如果用户要求“加强冲突/压缩对白/更爽/更细腻/更像网文”等，要落实到具体段落。
4. 输出完整正文，不要只输出修改片段。
5. 保留舒适分段，每个主要场景都要展开成可阅读段落。
6. 输出严格 JSON。

输出格式：
{{
  "chapter_number": {chapter_number},
  "title": "章节标题",
  "content": "修改后的完整小说正文",
  "word_count": 0,
  "continuity_notes": ["给下一章或拆页使用的连续性备注"]
}}"""

    def _comic_pages_prompt(
        self,
        project: CreativeProject,
        outline: dict[str, Any],
        storyboard: ProjectContent,
        page_count: int,
        reference_assets: list[dict[str, Any]] | None = None,
        visual_style: str | None = None,
        character_profiles: list[dict[str, Any]] | None = None,
    ) -> str:
        chapter_number = storyboard.chapter_number or storyboard.episode_number or 1
        storyboard_data = loads_json(storyboard.data_json)
        reference_text = dumps_json(reference_assets or [])
        character_profile_text = self._story_visual_context(
            outline,
            reference_assets=None,
            character_profiles=character_profiles or [],
        )
        effective_visual_style = visual_style or outline.get("visual_style", "")
        return f"""请根据分镜草稿整理成适合漫画生成的 {page_count} 页漫画脚本 JSON。

项目标题：{project.title}
章节：第 {chapter_number} 章
视觉风格：{effective_visual_style}
统一生图风格提示：{outline.get("image_style_prompt", "")}

项目参考资产：
{reference_text}

角色生产档案：
{character_profile_text}

分镜草稿：
{dumps_json(storyboard_data)}

要求：
1. pages 必须正好 {page_count} 页，page_number 从 1 连续递增。
2. 每页 content 使用【第1格】这样的分格标记，建议每页 3-6 格。
3. 每页应承接 storyboard panels，不要凭空改剧情；可以把多个 panel 合并成一页，也可以把复杂 panel 拆成多格。
4. 每格写清角色、动作、画面、对白气泡、音效和镜头节奏。
5. 每页 image_prompt 是该页关键视觉提示，能直接送到生图。
6. 保持角色外观和视觉风格一致；page.image_prompt 必须优先复用“角色生产档案”里的本项目身份、服装覆盖、OOC 约束和 Off-Model 约束。
7. 如果项目参考资产里有 character/background/style/world/reference，必须把对应参考意图写入 page 的 image_prompt。
8. 输出严格 JSON，不要 Markdown。

输出格式：
{{
  "episode_number": {chapter_number},
  "chapter_number": {chapter_number},
  "title": "漫画拆页标题",
  "page_count": {page_count},
  "visual_style": "统一视觉风格",
  "pages": [
    {{
      "page_number": 1,
      "title": "本页标题",
      "content": "第1页：\\n【第1格】...\\n【第2格】...",
      "image_prompt": "本页关键画面提示词"
    }}
  ]
}}"""

    def _project_character_production_profiles(
        self,
        project_id: str,
        outline: dict[str, Any],
    ) -> list[dict[str, Any]]:
        outline_characters = [
            item for item in outline.get("characters") or []
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
        links = self.session.exec(
            select(CharacterStoryLink).where(CharacterStoryLink.story_id == project_id)
        ).all()
        character_ids = [link.character_id for link in links if link.character_id]
        characters_by_id: dict[str, Character] = {}
        if character_ids:
            characters = self.session.exec(
                select(Character).where(Character.id.in_(character_ids))
            ).all()
            characters_by_id = {item.id: item for item in characters}
        links_by_character_id = {link.character_id: link for link in links}
        outline_by_name = {str(item.get("name")): item for item in outline_characters}

        profiles: list[dict[str, Any]] = []
        used_names: set[str] = set()
        for link in links:
            character = characters_by_id.get(link.character_id)
            if not character:
                continue
            outline_character = outline_by_name.get(character.name, {})
            profiles.append(self._character_production_profile(character, link, outline_character))
            used_names.add(character.name)

        for outline_character in outline_characters:
            name = str(outline_character.get("name") or "")
            if name in used_names:
                continue
            character_id = str(outline_character.get("character_id") or "")
            link = links_by_character_id.get(character_id)
            character = characters_by_id.get(character_id)
            if character and link:
                profiles.append(self._character_production_profile(character, link, outline_character))
                used_names.add(character.name)
                continue
            profiles.append(self._outline_character_profile(outline_character))

        return profiles

    def _character_production_profile(
        self,
        character: Character,
        link: CharacterStoryLink,
        outline_character: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        outline_character = outline_character or {}
        identity = loads_json(getattr(character, "identity_json", "{}"), {})
        motivation = loads_json(getattr(character, "motivation_json", "{}"), {})
        speech = loads_json(getattr(character, "speech_json", "{}"), {})
        behavior = loads_json(getattr(character, "behavior_json", "{}"), {})
        ability = loads_json(getattr(character, "ability_json", "{}"), {})
        arc = loads_json(getattr(character, "arc_json", "{}"), {})
        visual_profile = identity.get("visual_profile") if isinstance(identity.get("visual_profile"), dict) else {}
        visual_overrides = loads_json(getattr(link, "visual_overrides_json", "{}"), {})
        bible_overrides = loads_json(getattr(link, "bible_overrides_json", "{}"), {})
        reference_image_urls = visual_profile.get("reference_image_urls")
        if not isinstance(reference_image_urls, list):
            reference_image_urls = []
        return {
            "character_id": character.id,
            "name": character.name,
            "world_name": link.world_name or "",
            "usage_role": link.usage_role or character.role,
            "local_alias": link.local_alias or identity.get("alias") or "",
            "local_identity": link.local_identity or identity.get("logline") or outline_character.get("role") or "",
            "local_faction": link.local_faction or identity.get("organization") or "",
            "age_range": character.age_range or outline_character.get("age_range") or "",
            "appearance": visual_overrides.get("appearance") or character.appearance or outline_character.get("appearance") or "",
            "costume": link.local_costume or visual_overrides.get("costume") or character.costume_hint or outline_character.get("costume_hint") or "",
            "signature_items": _list_join(loads_json(character.signature_items, []) or outline_character.get("signature_items") or []),
            "expression_set": _list_join(loads_json(character.expressions, []) or outline_character.get("expressions") or []),
            "pose_set": _list_join(loads_json(character.poses, []) or outline_character.get("poses") or []),
            "visual_tags": _list_join(loads_json(link.local_prompt_tags, []) or outline_character.get("visual_tags") or []),
            "visual_consistency": "；".join(
                part for part in [
                    character.visual_consistency,
                    link.off_model_notes,
                    str(visual_overrides.get("consistency") or ""),
                ] if part
            ),
            "ooc_rules": "；".join(
                part for part in [
                    link.ooc_notes,
                    str(behavior.get("never_do") or ""),
                    str(behavior.get("boundary") or ""),
                    str(bible_overrides.get("ooc") or ""),
                ] if part
            ),
            "motivation": "；".join(part for part in [motivation.get("desire"), motivation.get("fear")] if part),
            "speech": "；".join(part for part in [speech.get("tone"), speech.get("catchphrase")] if part),
            "ability": "；".join(part for part in [ability.get("skills"), ability.get("limits")] if part),
            "arc": "；".join(part for part in [arc.get("turning_point"), arc.get("risk_notes")] if part),
            "portrait_node_id": getattr(character, "portrait_node_id", None),
            "portrait_url": getattr(character, "portrait_url", "") or "",
            "identity_reference_url": str(visual_profile.get("identity_reference_url") or "").strip(),
            "identity_reference_version_id": str(visual_profile.get("identity_reference_version_id") or "").strip(),
            "reference_image_count": len([url for url in reference_image_urls if str(url or "").strip()]),
        }

    def _outline_character_profile(self, character: dict[str, Any]) -> dict[str, Any]:
        return {
            "character_id": character.get("character_id", ""),
            "name": character.get("name", ""),
            "world_name": "",
            "usage_role": character.get("role", ""),
            "local_alias": "",
            "local_identity": character.get("role", ""),
            "local_faction": character.get("faction", ""),
            "age_range": character.get("age_range", ""),
            "appearance": character.get("appearance", ""),
            "costume": character.get("costume_hint", ""),
            "signature_items": _list_join(character.get("signature_items") or []),
            "expression_set": _list_join(character.get("expressions") or []),
            "pose_set": _list_join(character.get("poses") or []),
            "visual_tags": _list_join(character.get("visual_tags") or []),
            "visual_consistency": character.get("visual_consistency", ""),
            "ooc_rules": character.get("ooc_notes", ""),
            "motivation": character.get("motivation", ""),
            "speech": "",
            "ability": "",
            "arc": character.get("arc", ""),
            "portrait_node_id": "",
            "portrait_url": "",
            "identity_reference_url": "",
            "identity_reference_version_id": "",
            "reference_image_count": 0,
        }

    def _story_visual_context(
        self,
        outline: dict[str, Any],
        reference_assets: list[dict[str, Any]] | None = None,
        *,
        character_profiles: list[dict[str, Any]] | None = None,
    ) -> str:
        characters = outline.get("characters") or []
        locations = outline.get("locations") or []
        lines = [
            f"统一视觉风格：{outline.get('visual_style', '')}",
            f"统一生图风格提示：{outline.get('image_style_prompt', '')}",
        ]
        profiles = character_profiles or []
        if profiles:
            lines.append("角色生产档案（全局角色本体 + 本项目/世界使用覆盖，必须优先使用）：")
            for profile in profiles:
                lines.append(
                    " - "
                    + "；".join(
                        part
                        for part in [
                            f"姓名：{profile.get('name', '')}",
                            f"世界身份：{profile.get('local_identity', '')}",
                            f"本世界职责：{profile.get('usage_role', '')}",
                            f"阵营：{profile.get('local_faction', '')}",
                            f"年龄：{profile.get('age_range', '')}",
                            f"外貌：{profile.get('appearance', '')}",
                            f"服装：{profile.get('costume', '')}",
                            f"稳定标签：{profile.get('visual_tags', '')}",
                            f"标志物：{profile.get('signature_items', '')}",
                            f"表情：{profile.get('expression_set', '')}",
                            f"姿态：{profile.get('pose_set', '')}",
                            f"Off-Model 约束：{profile.get('visual_consistency', '')}",
                            f"OOC 约束：{profile.get('ooc_rules', '')}",
                            f"语言：{profile.get('speech', '')}",
                            f"动机：{profile.get('motivation', '')}",
                            f"身份基准图：{'已配置' if profile.get('identity_reference_url') else ''}",
                            f"默认参考图数量：{profile.get('reference_image_count') or ''}",
                        ]
                        if part.split("：", 1)[-1]
                    )
                )
        elif characters:
            lines.append("角色视觉档案：")
            for character in characters:
                if not isinstance(character, dict):
                    continue
                lines.append(
                    " - "
                    + "；".join(
                        part
                        for part in [
                            f"姓名：{character.get('name', '')}",
                            f"定位：{character.get('role', '')}",
                            f"年龄：{character.get('age_range', '')}",
                            f"外貌：{character.get('appearance', '')}",
                            f"服装：{character.get('costume_hint', '')}",
                            f"稳定标签：{'、'.join(character.get('visual_tags') or [])}",
                            f"标志物：{'、'.join(character.get('signature_items') or [])}",
                            f"常用表情：{'、'.join(character.get('expressions') or [])}",
                            f"常用姿态：{'、'.join(character.get('poses') or [])}",
                            f"一致性规则：{character.get('visual_consistency', '')}",
                            f"角色图提示：{character.get('image_prompt', '')}",
                        ]
                        if part.split("：", 1)[-1]
                    )
                )
        if locations:
            lines.append("场景视觉档案：")
            for location in locations:
                if not isinstance(location, dict):
                    continue
                lines.append(
                    " - "
                    + "；".join(
                        part
                        for part in [
                            f"地点：{location.get('name', '')}",
                            f"作用：{location.get('role', '')}",
                            f"视觉：{location.get('visual_description', '')}",
                            f"氛围：{location.get('mood', '')}",
                        ]
                        if part.split("：", 1)[-1]
                    )
                )
        if reference_assets:
            lines.append("项目参考素材：")
            for asset in reference_assets:
                meta = asset.get("metadata") or {}
                lines.append(
                    f" - asset_id={asset.get('asset_id')}；类型={asset.get('role')}；关系={asset.get('relation')}；说明={meta.get('character_name') or meta.get('source_title') or ''}"
                )
        return "\n".join(line for line in lines if line.strip())

    def _normalize_chapter_outline_v2(self, data: dict[str, Any]) -> None:
        scenes = data.get("scenes")
        if not isinstance(scenes, list):
            data["scenes"] = []
            return
        for index, scene in enumerate(scenes, start=1):
            if not isinstance(scene, dict):
                continue
            scene.setdefault("scene_number", index)
            for key in [
                "time_of_day",
                "weather",
                "spatial_axis",
                "character_positions",
                "movement_path",
            ]:
                scene.setdefault(key, "")
            props = scene.get("props")
            if props is None:
                scene["props"] = []
            elif not isinstance(props, list):
                scene["props"] = [str(props)]

    def _normalize_storyboard_v2(self, data: dict[str, Any]) -> None:
        panels = data.get("panels")
        if not isinstance(panels, list):
            data["panels"] = []
            return
        for index, panel in enumerate(panels, start=1):
            if not isinstance(panel, dict):
                continue
            panel.setdefault("panel_number", index)
            panel.setdefault("panel_goal", "")
            panel.setdefault("location", "")
            panel.setdefault("camera_angle", "")
            panel["camera_motion"] = self._normalize_storyboard_camera_motion(panel.get("camera_motion"))
            panel.setdefault("blocking", "")
            panel["duration_seconds"] = self._normalize_storyboard_duration(panel)
            panel.setdefault("music_hint", "")
            panel["generate_audio"] = self._normalize_storyboard_audio_flag(panel.get("generate_audio"))
            if not str(panel.get("video_prompt") or "").strip():
                panel["video_prompt"] = self._build_storyboard_video_prompt(panel)
            props = panel.get("props")
            if props is None:
                panel["props"] = []
            elif not isinstance(props, list):
                panel["props"] = [str(props)]

    @staticmethod
    def _normalize_storyboard_camera_motion(value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return "静止"
        normalized = raw.replace("镜头", "").replace("缓慢", "").replace("轻微", "").strip()
        motion_map = (
            ("环绕", "环绕"),
            ("跟", "跟拍"),
            ("推", "推近"),
            ("拉", "拉远"),
            ("摇", "摇镜"),
            ("移", "平移"),
            ("静", "静止"),
            ("固定", "静止"),
        )
        for marker, canonical in motion_map:
            if marker in normalized:
                return canonical
        return raw[:24]

    @staticmethod
    def _normalize_storyboard_duration(panel: dict[str, Any]) -> int:
        raw = panel.get("duration_seconds", panel.get("duration", ""))
        try:
            duration = int(float(raw))
        except (TypeError, ValueError):
            shot_size = str(panel.get("shot_size") or "")
            duration = 3 if any(marker in shot_size for marker in ("特写", "窄格")) else 5 if any(
                marker in shot_size for marker in ("远景", "大宽格")
            ) else 4
        return max(3, min(duration, 6))

    @staticmethod
    def _normalize_storyboard_audio_flag(value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "on", "是"}
        return bool(value)

    @staticmethod
    def _build_storyboard_video_prompt(panel: dict[str, Any]) -> str:
        subject_action = str(panel.get("action") or panel.get("panel_goal") or "人物完成当前镜头动作").strip()
        camera_motion = str(panel.get("camera_motion") or "静止").strip()
        shot_size = str(panel.get("shot_size") or "中景").strip()
        camera_angle = str(panel.get("camera_angle") or "平视").strip()
        location = str(panel.get("location") or "当前场景").strip()
        emotion = str(panel.get("emotion") or "").strip()
        parts = [
            f"竖屏短剧{shot_size}{camera_angle}镜头：{subject_action}",
            f"在{location}内以{camera_motion}完成镜头运动",
        ]
        if emotion:
            parts.append(f"人物情绪保持{emotion}")
        parts.append("动作自然连贯，保持首帧中的角色、服装、场景和光线一致，不出现字幕或新增人物")
        return "；".join(parts)

    def _enhance_storyboard_image_prompts(
        self,
        data: dict[str, Any],
        outline: dict[str, Any],
        reference_assets: list[dict[str, Any]] | None = None,
        *,
        character_profiles: list[dict[str, Any]] | None = None,
    ) -> None:
        characters = {
            str(character.get("name")): character
            for character in outline.get("characters") or []
            if isinstance(character, dict) and character.get("name")
        }
        profiles = {
            str(profile.get("name")): profile
            for profile in character_profiles or []
            if isinstance(profile, dict) and profile.get("name")
        }
        style_parts = [
            outline.get("image_style_prompt", ""),
            outline.get("visual_style", ""),
            "漫画分镜，画面可直接用于 AI 生图，角色外观保持一致",
        ]
        style_text = "，".join(part for part in style_parts if part)
        reference_hint = ""
        if reference_assets:
            refs = [f"{item.get('role')}:{item.get('asset_id')}" for item in reference_assets[:6] if item.get("asset_id")]
            if refs:
                reference_hint = "，参考项目素材：" + "、".join(refs)

        for panel in data.get("panels") or []:
            if not isinstance(panel, dict):
                continue
            prompt = str(panel.get("image_prompt") or "").strip()

            character_names = [str(name) for name in panel.get("characters") or [] if str(name).strip()]
            character_desc = []
            character_ids = []
            portrait_node_ids = []
            for name in character_names:
                profile = profiles.get(name)
                if profile:
                    character_ids.append(profile.get("character_id"))
                    portrait_node_ids.append(profile.get("portrait_node_id"))
                    desc = "，".join(
                        part
                        for part in [
                            name,
                            str(profile.get("local_identity") or ""),
                            str(profile.get("usage_role") or ""),
                            str(profile.get("age_range") or ""),
                            str(profile.get("appearance") or ""),
                            str(profile.get("costume") or ""),
                            str(profile.get("visual_tags") or ""),
                            str(profile.get("signature_items") or ""),
                            str(profile.get("visual_consistency") or ""),
                            str(profile.get("ooc_rules") or ""),
                            "已有身份基准图，生图时优先参考以保持同脸同服装" if profile.get("identity_reference_url") else "",
                            f"默认参考图{profile.get('reference_image_count')}张" if profile.get("reference_image_count") else "",
                        ]
                        if part
                    )
                    character_desc.append(desc)
                    continue
                character = characters.get(name)
                if not character:
                    character_desc.append(name)
                    continue
                character_ids.append(character.get("character_id"))
                desc = "，".join(
                    part
                    for part in [
                        name,
                        str(character.get("age_range") or ""),
                        str(character.get("appearance") or ""),
                        str(character.get("costume_hint") or ""),
                        "、".join(character.get("visual_tags") or []),
                        "、".join(character.get("signature_items") or []),
                        str(character.get("visual_consistency") or ""),
                    ]
                    if part
                )
                character_desc.append(desc)

            character_ids = _dedupe_keep_order(character_ids)
            portrait_node_ids = _dedupe_keep_order(portrait_node_ids)
            reference_asset_ids = list(panel.get("reference_asset_ids") or [])
            for asset in reference_assets or []:
                if not isinstance(asset, dict):
                    continue
                asset_id = asset.get("asset_id")
                if not asset_id:
                    continue
                meta = asset.get("metadata") or {}
                if asset.get("role") == "style":
                    reference_asset_ids.append(asset_id)
                elif asset.get("role") == "character" and (
                    meta.get("character_id") in character_ids
                    or meta.get("character_name") in character_names
                    or asset_id in portrait_node_ids
                ):
                    reference_asset_ids.append(asset_id)
                elif asset.get("role") in {"background", "world", "reference"}:
                    marker = " ".join(
                        str(value or "")
                        for value in [
                            meta.get("label"),
                            meta.get("source_title"),
                            meta.get("source_type"),
                            asset_id,
                        ]
                    ).lower()
                    panel_text = " ".join(
                        str(value or "")
                        for value in [
                            panel.get("location"),
                            panel.get("action"),
                            panel.get("image_prompt"),
                            panel.get("blocking"),
                            " ".join(str(prop) for prop in panel.get("props") or []),
                        ]
                    ).lower()
                    if marker and any(
                        token and token in panel_text
                        for token in re.split(r"[\s,，。；;、/|]+", marker)
                        if len(token) >= 2
                    ):
                        reference_asset_ids.append(asset_id)
            reference_asset_ids = _dedupe_keep_order(reference_asset_ids)

            enriched = "，".join(
                part
                for part in [
                    style_text,
                    f"角色：{'；'.join(character_desc)}" if character_desc else "",
                    f"动作：{panel.get('action', '')}" if panel.get("action") else "",
                    f"情绪：{panel.get('emotion', '')}" if panel.get("emotion") else "",
                    f"镜头：{panel.get('camera_hint', '')}" if panel.get("camera_hint") else "",
                    f"镜头角度：{panel.get('camera_angle', '')}" if panel.get("camera_angle") else "",
                    f"镜头运动：{panel.get('camera_motion', '')}" if panel.get("camera_motion") else "",
                    f"景别：{panel.get('shot_size', '')}" if panel.get("shot_size") else "",
                    f"构图：{panel.get('composition', '')}" if panel.get("composition") else "",
                    f"调度：{panel.get('blocking', '')}" if panel.get("blocking") else "",
                    f"道具：{'、'.join(panel.get('props') or [])}" if panel.get("props") else "",
                    f"对白气泡：{'；'.join(panel.get('dialogue_bubbles') or [])}" if panel.get("dialogue_bubbles") else "",
                    f"原始画面意图：{prompt}" if prompt else "",
                    "清晰人物脸部，准确手部，电影感光影，竖屏短剧漫画构图，避免文字乱码和多余肢体",
                    reference_hint,
                ]
                if part
            )
            panel["image_prompt"] = enriched
            panel["character_ids"] = character_ids
            panel["portrait_node_ids"] = portrait_node_ids
            panel["reference_asset_ids"] = reference_asset_ids
            if not panel.get("negative_prompt"):
                ooc_negative = "，".join(
                    profile.get("ooc_rules", "")
                    for name in character_names
                    for profile in [profiles.get(name)]
                    if profile and profile.get("ooc_rules")
                )
                panel["negative_prompt"] = "，".join(
                    part for part in [
                        "低清晰度，脸部崩坏，手指错误，多余肢体，文字乱码，角色服装不一致，画风突变",
                        ooc_negative,
                    ] if part
                )

    def _inherit_comic_page_references(self, data: dict[str, Any], storyboard_data: dict[str, Any]) -> None:
        panels = [panel for panel in storyboard_data.get("panels") or [] if isinstance(panel, dict)]
        panel_by_number = {
            int(panel.get("panel_number")): panel
            for panel in panels
            if str(panel.get("panel_number") or "").isdigit()
        }
        all_character_ids = _dedupe_keep_order(
            item
            for panel in panels
            for item in panel.get("character_ids", [])
        )
        all_portrait_node_ids = _dedupe_keep_order(
            item
            for panel in panels
            for item in panel.get("portrait_node_ids", [])
        )
        all_reference_asset_ids = _dedupe_keep_order(
            item
            for panel in panels
            for item in panel.get("reference_asset_ids", [])
        )

        for page in data.get("pages") or []:
            if not isinstance(page, dict):
                continue
            raw_numbers = page.get("source_panel_numbers") or page.get("source_panels") or []
            if isinstance(raw_numbers, (str, int)):
                raw_numbers = [raw_numbers]
            source_numbers = [
                int(value)
                for value in raw_numbers
                if str(value or "").isdigit()
            ]
            source_panels = [panel_by_number[number] for number in source_numbers if number in panel_by_number]
            if not source_panels:
                source_panels = panels
            page["character_ids"] = _dedupe_keep_order([
                *page.get("character_ids", []),
                *(item for panel in source_panels for item in panel.get("character_ids", [])),
                *all_character_ids,
            ])
            page["portrait_node_ids"] = _dedupe_keep_order([
                *page.get("portrait_node_ids", []),
                *(item for panel in source_panels for item in panel.get("portrait_node_ids", [])),
                *all_portrait_node_ids,
            ])
            page["reference_asset_ids"] = _dedupe_keep_order([
                *page.get("reference_asset_ids", []),
                *(item for panel in source_panels for item in panel.get("reference_asset_ids", [])),
                *all_reference_asset_ids,
            ])
            page["reference_notes"] = _dedupe_keep_order([
                *[str(note) for note in page.get("reference_notes", []) if str(note or "").strip()],
                *[
                    str(note)
                    for panel in source_panels
                    for note in panel.get("reference_notes", [])
                    if str(note or "").strip()
                ],
            ])

    def _storyboard_prompt(
        self,
        project: CreativeProject,
        script: ProjectContent,
        reference_assets: list[dict[str, Any]] | None = None,
        character_profiles: list[dict[str, Any]] | None = None,
    ) -> str:
        outline = loads_json(project.outline_json)
        script_data = loads_json(script.data_json)
        visual_context = self._story_visual_context(outline, reference_assets, character_profiles=character_profiles)
        return f"""请根据短剧脚本生成漫画/视频分镜 JSON。

视觉制作档案：
{visual_context}

脚本：
{dumps_json(script_data)}

要求：
1. 每个 panel 都要能独立用于 AI 图片生成，不能只写剧情摘要。
2. 每个 image_prompt 必须写成镜头级漫画生图提示词，包含：角色身份、角色外貌、服装、地点道具、动作、表情、景别、镜头角度、构图、光线色调、氛围、漫画风格、画面重点和一致性要求。
3. video_prompt 与 image_prompt 分开写：它只描述首帧之后可见的动作、镜头运动、节奏和情绪变化，不重复静态外貌清单，也不写字幕、分镜编号或模型参数。
4. duration_seconds 必须是 3-6 的整数；特写通常 3 秒，中景 4 秒，远景/大宽格 5-6 秒。camera_motion 只使用 推近/拉远/摇镜/平移/跟拍/环绕/静止 之一。
5. generate_audio 默认 false；只有该镜头确实需要原生环境声或音乐时才设 true，并在 music_hint 写简短声音建议。
6. panels 要覆盖完整剧情节拍，建议每场至少 2-4 个 panel，远景/中景/特写/大宽格交替，避免连续同景别。
7. dialogue_bubbles 写本格可见对白气泡，sound_effect 写拟声词或环境声，negative_prompt 写需要避免的画面问题。
8. image_prompt 必须复用上方角色视觉档案，不允许只写“某人醒来”“递合同”等剧情短句；没有明确角色外貌时也要写身份、年龄、体型、发型、服装和稳定视觉标签。
9. 如果项目参考素材里有 character/background/style/world/reference，请把参考意图写入 image_prompt，供后续图生图或人工关联。
10. 保持角色外观、服装、场景和视觉风格一致。
11. 输出严格 JSON。

输出格式：
{{
  "episode_number": {script.episode_number or 1},
  "title": "分镜标题",
  "visual_style": "统一视觉风格",
  "panels": [
    {{
      "panel_number": 1,
      "source_scene_number": 1,
      "panel_goal": "本格叙事目的",
      "location": "地点",
      "image_prompt": "生图提示词",
      "video_prompt": "只描述可见动作、镜头运动和节奏的视频提示词",
      "duration_seconds": 4,
      "camera_hint": "镜头",
      "camera_angle": "平视/俯视/仰视/过肩/主观视角",
      "camera_motion": "推近/拉远/摇镜/平移/跟拍/环绕/静止",
      "shot_size": "远景/中景/特写/大宽格/窄格",
      "composition": "构图说明",
      "blocking": "角色站位和调度",
      "characters": ["角色"],
      "action": "动作",
      "emotion": "情绪",
      "props": ["关键道具"],
      "dialogue_bubbles": ["对白气泡"],
      "sound_effect": "音效字",
      "music_hint": "可选的环境声或配乐建议",
      "generate_audio": false,
      "negative_prompt": "避免项",
      "notes": "备注"
    }}
  ]
}}"""

    def _outline_text(self, data: dict[str, Any]) -> str:
        return "\n".join(
            part
            for part in [
                f"# {data.get('title', '')}",
                data.get("logline", ""),
                data.get("worldview", ""),
                data.get("main_conflict", ""),
            ]
            if part
        )

    def _chapter_plan_text(self, data: dict[str, Any]) -> str:
        lines = [f"# 章节规划，共 {data.get('chapter_count', 0)} 章"]
        for item in data.get("chapters") or []:
            lines.append(f"## {item.get('chapter_number')}. {item.get('title', '')}")
            if item.get("goal"):
                lines.append(f"目标：{item.get('goal')}")
            if item.get("conflict"):
                lines.append(f"冲突：{item.get('conflict')}")
            if item.get("ending_hook"):
                lines.append(f"钩子：{item.get('ending_hook')}")
        return "\n".join(lines)

    def _chapter_outline_text(self, data: dict[str, Any]) -> str:
        lines = [
            f"# 第 {data.get('chapter_number', '')} 章 {data.get('title', '')}".strip(),
            data.get("summary", ""),
            f"目标：{data.get('objective', '')}" if data.get("objective") else "",
        ]
        for scene in data.get("scenes") or []:
            lines.append(f"## 场景 {scene.get('scene_number')}. {scene.get('title', '')}")
            if scene.get("purpose"):
                lines.append(f"场景作用：{scene.get('purpose')}")
            if scene.get("scene_role"):
                lines.append(f"场景位置：{scene.get('scene_role')}")
            if scene.get("conflict"):
                lines.append(f"冲突：{scene.get('conflict')}")
            for beat in scene.get("beats") or []:
                lines.append(f"- {beat}")
            lines.append(scene.get("action", ""))
            if scene.get("key_dialogue"):
                lines.append(f"关键台词：{scene.get('key_dialogue')}")
            if scene.get("emotional_turn") or scene.get("emotion"):
                lines.append(f"情绪：{scene.get('emotion', '')} {scene.get('emotional_turn', '')}".strip())
            if scene.get("shot_design"):
                lines.append(f"镜头设计：{scene.get('shot_design')}")
            if scene.get("image_prompt"):
                lines.append(f"生图提示：{scene.get('image_prompt')}")
        if data.get("ending_hook"):
            lines.append(f"结尾钩子：{data.get('ending_hook')}")
        return "\n".join(part for part in lines if part)

    def _comic_pages_text(self, data: dict[str, Any]) -> str:
        lines = [
            f"# {data.get('title') or '漫画拆页'}",
            f"视觉风格：{data.get('visual_style', '')}" if data.get("visual_style") else "",
        ]
        for page in data.get("pages") or []:
            lines.append(f"## 第 {page.get('page_number')} 页 {page.get('title', '')}".strip())
            lines.append(page.get("content", ""))
            if page.get("image_prompt"):
                lines.append(f"生图提示：{page.get('image_prompt')}")
        return "\n".join(part for part in lines if part)

    def _title_from_idea(self, idea: str) -> str:
        text = (idea or "").strip().replace("\n", " ")
        return text[:24] or "未命名创作项目"

    def _response_success(self, response: Any) -> bool:
        if isinstance(response, dict):
            return bool(response.get("success", True))
        return bool(getattr(response, "success", True))

    def _response_content(self, response: Any) -> str:
        if isinstance(response, dict):
            return str(response.get("content") or "")
        return str(getattr(response, "content", "") or "")

    def _response_error(self, response: Any) -> str:
        if isinstance(response, dict):
            return str(response.get("error") or response.get("message") or "")
        return str(getattr(response, "error", "") or "")

    def _response_attr(self, response: Any, key: str) -> str:
        if isinstance(response, dict):
            return str(response.get(key) or "")
        return str(getattr(response, key, "") or "")
