"""Context pack builders for Agent Center runs."""

from __future__ import annotations

from typing import Any

from sqlmodel import select

from app.db.database import SessionLocal
from app.db.models.character import Character, CharacterStoryLink
from app.db.models.creative_project import ProjectContent, ProjectGenerationLog
from app.services.creative_project.profiles import CONTENT_PRODUCTION_PROFILES
from app.services.creative_project.service import CreativeProjectService, loads_json


IMPORTANT_CONTENT_TYPES = [
    "chapter_outline",
    "novel_body",
    "script",
    "storyboard",
    "comic_pages",
    "reference_asset_match",
    "project_bible",
    "world_asset",
]


def _content_brief(content: ProjectContent) -> dict[str, Any]:
    data = loads_json(content.data_json)
    text = content.text_content or ""
    return {
        "id": content.id,
        "content_type": content.content_type,
        "chapter_number": content.chapter_number,
        "title": content.title,
        "version": content.version,
        "is_locked": content.is_locked,
        "summary": data.get("summary") or data.get("title") or text[:180],
        "updated_at": content.updated_at.isoformat() if content.updated_at else None,
    }


def _production_plan_brief(content: ProjectContent | None) -> dict[str, Any] | None:
    """Return the business-visible director plan state for an Agent context.

    A production plan is deliberately not a scratchpad for hidden model
    reasoning.  The context therefore carries only the user-editable plan
    fields and bounded node summaries needed to decide the next safe action.
    """
    if content is None:
        return None

    data = loads_json(content.data_json)
    nodes = list(data.get("nodes") or [])
    confirmation_nodes = []
    for node in nodes:
        if not isinstance(node, dict) or not node.get("requires_confirmation"):
            continue
        confirmation_nodes.append(
            {
                "id": str(node.get("id") or ""),
                "label": str(node.get("label") or ""),
                "stage": str(node.get("stage") or ""),
                "status": str(node.get("status") or "planned"),
            }
        )

    return {
        "content_id": content.id,
        "version": content.version,
        "source_plan_id": data.get("source_plan_id") or content.source_content_id or "",
        "title": content.title,
        "goal": (data.get("goal") or content.text_content or "")[:400],
        "production_profile": data.get("production_profile") or "",
        "status": data.get("status") or "draft",
        "confirmation_status": data.get("confirmation_status") or "pending",
        "canvas_document_id": data.get("canvas_document_id") or "",
        "asset_ids": list(data.get("asset_ids") or [])[:24],
        "node_count": len(nodes),
        "confirmation_nodes": confirmation_nodes[:24],
        "nodes": [
            {
                "id": str(node.get("id") or ""),
                "stage": str(node.get("stage") or ""),
                "label": str(node.get("label") or ""),
                "specialist_role": str(node.get("specialist_role") or ""),
                "status": str(node.get("status") or "planned"),
                "depends_on": list(node.get("depends_on") or []),
                "input_content_ids": list(node.get("input_content_ids") or []),
                "input_asset_ids": list(node.get("input_asset_ids") or []),
                "output_content_ids": list(node.get("output_content_ids") or []),
                "output_asset_ids": list(node.get("output_asset_ids") or []),
                "provider": str(node.get("provider") or ""),
                "model": str(node.get("model") or ""),
                "requires_confirmation": bool(node.get("requires_confirmation", True)),
                "rerun_scope": str(node.get("rerun_scope") or "node"),
                "planning_summary": node.get("planning_summary") if isinstance(node.get("planning_summary"), dict) else {},
            }
            for node in nodes[:48]
            if isinstance(node, dict)
        ],
        "updated_at": content.updated_at.isoformat() if content.updated_at else None,
    }


def _chapter_status(contents: list[ProjectContent]) -> list[dict[str, Any]]:
    by_chapter: dict[int, dict[str, Any]] = {}
    for item in contents:
        if not item.chapter_number:
            continue
        chapter = by_chapter.setdefault(
            int(item.chapter_number),
            {
                "chapter_number": int(item.chapter_number),
                "content_types": [],
                "latest_titles": {},
            },
        )
        if item.content_type not in chapter["content_types"]:
            chapter["content_types"].append(item.content_type)
        chapter["latest_titles"].setdefault(item.content_type, item.title)
    return [by_chapter[key] for key in sorted(by_chapter)]


def _character_briefs(project_id: str, limit: int = 12) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        links = session.exec(
            select(CharacterStoryLink)
            .where(CharacterStoryLink.story_id == project_id)
            .order_by(CharacterStoryLink.updated_at.desc())
            .limit(limit)
        ).all()
        if not links:
            return []
        ids = [item.character_id for item in links if item.character_id]
        characters = session.exec(select(Character).where(Character.id.in_(ids))).all() if ids else []
        by_id = {item.id: item for item in characters}
        briefs = []
        for link in links:
            character = by_id.get(link.character_id)
            if not character:
                continue
            briefs.append(
                {
                    "character_id": character.id,
                    "name": character.name,
                    "role": link.usage_role or character.role,
                    "identity": link.local_identity,
                    "faction": link.local_faction,
                    "appearance": character.appearance[:220],
                    "costume": link.local_costume or character.costume_hint,
                    "portrait_node_id": character.portrait_node_id,
                    "portrait_url": character.portrait_url,
                }
            )
        return briefs


def build_creative_project_context_pack(
    project_id: str,
    *,
    chapter_number: int | None = None,
    content_limit: int = 24,
) -> dict[str, Any]:
    """Build a compact read-only project context for agent reasoning."""
    if not project_id:
        return {}

    with SessionLocal() as session:
        service = CreativeProjectService(session)
        project = service.get_project(project_id)
        if not project:
            return {
                "project_id": project_id,
                "found": False,
                "warning": "creative project not found",
            }

        outline = loads_json(project.outline_json)
        chapter_plan = loads_json(project.chapter_plan_json)
        settings = loads_json(project.settings_json)
        profile_id = str(settings.get("production_profile") or "")
        profile = CONTENT_PRODUCTION_PROFILES.get(profile_id) or {}
        contents = service.list_contents(project_id)
        production_plan = service.get_production_plan(project_id)
        assets = service.list_asset_links(project_id)
        logs, _ = service.list_generation_logs(project_id, limit=8)

        latest_by_type: dict[str, dict[str, Any]] = {}
        filtered_contents = []
        for content in contents:
            if chapter_number and content.chapter_number and int(content.chapter_number) != int(chapter_number):
                continue
            if content.content_type in IMPORTANT_CONTENT_TYPES:
                filtered_contents.append(content)
            latest_by_type.setdefault(content.content_type, _content_brief(content))

        bible_cards = [
            _content_brief(content)
            for content in contents
            if content.content_type in {"project_bible", "world_asset"}
        ][:12]

        return {
            "project": {
                "id": project.id,
                "title": project.title,
                "project_type": project.project_type,
                "status": project.status,
                "current_stage": project.current_stage,
                "production_profile": {
                    "id": profile_id,
                    "label": profile.get("label") or "",
                    "recommended_stages": list(profile.get("recommended_stages") or []),
                    "optional_stages": list(profile.get("optional_stages") or []),
                },
                "outline_title": outline.get("title") or "",
                "logline": outline.get("logline") or "",
                "chapter_count": chapter_plan.get("chapter_count") or len(chapter_plan.get("chapters") or []),
            },
            "chapter_number": chapter_number,
            "production_plan": _production_plan_brief(production_plan),
            "chapter_status": _chapter_status(contents),
            "latest_contents": list(latest_by_type.values())[:content_limit],
            "focused_contents": [_content_brief(item) for item in filtered_contents[:content_limit]],
            "characters": _character_briefs(project_id),
            "reference_assets": [
                {
                    "asset_id": link.asset_id,
                    "content_id": link.content_id,
                    "role": link.role,
                    "relation": link.relation,
                    "metadata": loads_json(link.metadata_json),
                }
                for link in assets[:18]
            ],
            "bible_cards": bible_cards,
            "recent_logs": [
                {
                    "stage": log.stage,
                    "status": log.status,
                    "provider": log.provider,
                    "model": log.model,
                    "validation_error": log.validation_error,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in logs
            ],
            "known_gaps": _known_gaps(chapter_plan, contents, assets),
        }


def _known_gaps(chapter_plan: dict[str, Any], contents: list[ProjectContent], assets: list[Any]) -> list[str]:
    gaps: list[str] = []
    if not chapter_plan.get("chapters"):
        gaps.append("缺少章节规划")
    content_types = {item.content_type for item in contents}
    for content_type, label in [
        ("project_bible", "项目圣经"),
        ("chapter_outline", "章节细纲"),
        ("novel_body", "正文"),
        ("script", "脚本"),
        ("storyboard", "分镜"),
    ]:
        if content_type not in content_types:
            gaps.append(f"缺少{label}")
    if not assets:
        gaps.append("缺少项目参考素材")
    return gaps[:8]
