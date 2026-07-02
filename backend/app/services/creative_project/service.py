"""Creative project workflow service."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from app.db.models.asset_hub import AssetNode
from app.db.models.character import Character, CharacterRole, CharacterSourceType, CharacterStoryLink
from app.db.models.creative_project import (
    CreativeProject,
    CreativeProjectStatus,
    ProjectAssetLink,
    ProjectContent,
    ProjectGenerationLog,
)
from app.db.models.novel import NovelChapter
from app.db.models.platform_template import PlatformTemplate
from app.services.ai.types import LLMMessage
from app.services.creative_project.schemas import (
    ChapterOutlineScenesSchema,
    ChapterOutlineSchema,
    ChapterPlanSchema,
    ComicPagesSchema,
    NovelBodySchema,
    ShortDramaScriptSchema,
    StoryOutlineSchema,
    StoryboardSchema,
)

logger = logging.getLogger("ylcraft.creative_project")

TModel = TypeVar("TModel", bound=BaseModel)


def dumps_json(data: Any) -> str:
    return json.dumps(data or {}, ensure_ascii=False)


def loads_json(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return {} if fallback is None else fallback
    try:
        return json.loads(value)
    except Exception:
        return {} if fallback is None else fallback


def _list_join(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "、".join(str(item) for item in value if str(item or "").strip())
    return str(value)


class CreativeProjectService:
    """业务编排：创作项目、阶段内容、生成日志和素材关联。"""

    def __init__(self, session: Session, ai_service: Any | None = None):
        self.session = session
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
        provider: str | None = None,
        model: str | None = None,
        template_id: str | None = None,
    ) -> dict[str, Any]:
        project = self._require_project(project_id)
        outline = loads_json(project.outline_json)
        if not outline:
            raise ValueError("请先生成或保存故事大纲")

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
        default_prompt = self._script_prompt(outline, chapter_plan, chapter_number)
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
        )
        self._create_content(
            project_id=project.id,
            content_type="script",
            chapter_number=chapter_number,
            episode_number=data.get("episode_number") or chapter_number,
            title=data.get("title") or f"第 {chapter_number} 集脚本",
            data=data,
            text_content=dumps_json(data),
        )
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
        default_prompt = self._chapter_outline_prompt(outline, chapter_plan, current_chapter, chapter_number, previous_context)
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
        previous_context = self._previous_chapter_context(project_id, chapter_number)
        default_prompt = self._novel_body_prompt(outline, chapter_plan, chapter_outline_data, chapter_number, previous_context)
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
        )
        content = str(data.get("content") or "")
        if not data.get("word_count"):
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
        default_prompt = self._refine_novel_body_prompt(
            project=project,
            content=content,
            body_data=body_data,
            outline_context=outline_context,
            instruction=instruction,
        )
        prompt, system_prompt, template_meta = self._stage_prompt(
            stage="novel_body_refine",
            default_prompt=default_prompt,
            template_id=template_id,
            variables={
                "project_title": project.title,
                "project_type": project.project_type,
                "chapter_number": content.chapter_number or content.episode_number or 1,
                "instruction": instruction,
                "body_json": dumps_json(body_data),
                "body_text": content.text_content,
                "chapter_outline_json": dumps_json(outline_context),
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
        )
        text = str(data.get("content") or "")
        if not data.get("word_count"):
            data["word_count"] = len(text)
        content.title = data.get("title") or content.title
        content.data_json = dumps_json({**body_data, **data})
        content.text_content = text
        content.updated_at = datetime.now()
        self.session.add(content)
        self.session.commit()
        self.session.refresh(content)
        return content

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
        )
        self._normalize_storyboard_v2(data)
        self._enhance_storyboard_image_prompts(data, outline, reference_assets, character_profiles=character_profiles)
        self._create_content(
            project_id=project.id,
            content_type="storyboard",
            chapter_number=script.chapter_number,
            episode_number=script.episode_number,
            title=data.get("title") or f"{script.title} 分镜",
            data=data,
            text_content=dumps_json(data),
            source_content_id=script.id,
        )
        project.status = CreativeProjectStatus.READY.value
        project.current_stage = "assets"
        project.updated_at = datetime.now()
        self.session.add(project)
        self.session.commit()
        return data

    # ------------------------------------------------------------------
    # Contents and assets
    # ------------------------------------------------------------------

    def list_contents(self, project_id: str, content_type: str | None = None) -> list[ProjectContent]:
        query = select(ProjectContent).where(ProjectContent.project_id == project_id)
        if content_type:
            query = query.where(ProjectContent.content_type == content_type)
        return self.session.exec(
            query.order_by(ProjectContent.created_at.desc(), ProjectContent.version.desc())
        ).all()

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
            content.text_content = text_content
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

    def list_asset_links(self, project_id: str) -> list[ProjectAssetLink]:
        return self.session.exec(
            select(ProjectAssetLink)
            .where(ProjectAssetLink.project_id == project_id)
            .order_by(ProjectAssetLink.created_at.desc())
        ).all()

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
            title=title,
            data_json=dumps_json(data),
            text_content=text_content,
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
                max_tokens=5000,
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
                    if stage in {"novel_body", "novel_body_refine"}:
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
            self.session.rollback()
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
        try:
            model = schema_model.model_validate(data)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        return model.model_dump()

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
        if content.startswith("{"):
            title = self._extract_json_string_field(content, "title") or ""
            extracted_content = self._extract_json_string_field(content, "content")
            if extracted_content:
                content = extracted_content.strip()
            else:
                raise ValueError("模型返回了疑似 JSON，但无法解析为章节正文")
        elif "{" in content and "}" in content:
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
    ) -> None:
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

    def _script_prompt(
        self,
        outline: dict[str, Any],
        chapter_plan: dict[str, Any],
        chapter_number: int,
    ) -> str:
        selected = self._chapter_plan_item(chapter_plan, chapter_number)
        return f"""请把指定章节改写成短剧单集脚本 JSON。

故事大纲：
{dumps_json(outline)}

当前章节：
{dumps_json(selected)}

要求：
1. 开头 5 秒必须有钩子。
2. 场景适合 60-120 秒竖屏短剧。
3. 每个 scene 都要给出可用于 AI 生图的 image_prompt。
4. 输出严格 JSON。

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
      "image_prompt": "画面提示词"
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

要求：
1. 单话细纲要比章节规划更细，必须能直接服务后续小说正文、短剧脚本、漫画分镜和生图。
2. 顶层必须写清 summary、objective、keywords、key_dialogues、foreshadowing、ending_hook、continuity_notes，不能只写空泛总结。
3. scenes 建议 4-8 个，每个 scene 必须有 purpose/scene_role/objective/conflict/beats/action/key_dialogue/emotion/emotional_turn/visual_focus/shot_design/image_prompt。
4. beats 是 2-5 条具体节拍，按镜头或剧情动作顺序写，不要写概念词。
5. key_dialogues 写可直接进入正文或漫画气泡的关键台词。
6. image_prompt 必须是镜头级中文提示词，至少包含：角色外观或身份、地点、动作、表情、构图景别、光线色调、氛围、漫画/影视风格、一致性要求；不要只写一句剧情。
7. foreshadowing 和 continuity_notes 要帮助后续章节保持连续。
8. 输出严格 JSON，不要 Markdown。

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
        previous_context: str,
    ) -> str:
        return f"""请根据单话细纲生成第 {chapter_number} 章小说正文 JSON。

故事大纲：
{dumps_json(outline)}

章节规划：
{dumps_json(chapter_plan)}

当前单话细纲：
{dumps_json(chapter_outline)}

前文上下文：
{previous_context or "暂无"}

要求：
1. content 字段输出完整小说正文，不要只写摘要。
2. 正文要遵守大纲中的人物设定、视觉风格、世界规则和连续性备注。
3. 保持网文/短剧改编友好的节奏：开头有钩子，中段有推进，结尾留悬念。
4. 可以有对白、动作和心理描写，但不要输出 Markdown 标题。
5. 输出严格 JSON，不要 Markdown。

输出格式：
{{
  "chapter_number": {chapter_number},
  "title": "章节标题",
  "content": "完整小说正文",
  "word_count": 0,
  "continuity_notes": ["给下一章或拆页使用的连续性备注"]
}}"""

    def _refine_novel_body_prompt(
        self,
        *,
        project: CreativeProject,
        content: ProjectContent,
        body_data: dict[str, Any],
        outline_context: dict[str, Any],
        instruction: str,
    ) -> str:
        chapter_number = content.chapter_number or content.episode_number or body_data.get("chapter_number") or 1
        return f"""请根据用户的中文修改要求，微调第 {chapter_number} 章小说正文，并输出严格 JSON。

项目标题：{project.title}

当前单话细纲：
{dumps_json(outline_context)}

当前正文：
{content.text_content or body_data.get("content", "")}

用户中文修改要求：
{instruction}

要求：
1. 只修改正文，不要输出解释、Markdown 或代码块。
2. 保留原有主线、人物身份、连续性和重要伏笔，按照用户要求加强或压缩。
3. 如果用户要求“加强冲突/压缩对白/更爽/更细腻/更像网文”等，要落实到具体段落。
4. 输出完整正文，不要只输出修改片段。
5. 输出严格 JSON。

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
        visual_overrides = loads_json(getattr(link, "visual_overrides_json", "{}"), {})
        bible_overrides = loads_json(getattr(link, "bible_overrides_json", "{}"), {})
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
            panel.setdefault("camera_motion", "")
            panel.setdefault("blocking", "")
            props = panel.get("props")
            if props is None:
                panel["props"] = []
            elif not isinstance(props, list):
                panel["props"] = [str(props)]

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
            if len(prompt) >= 90 and any(key in prompt for key in ["镜头", "构图", "光线", "景别", "特写", "中景", "远景"]):
                continue

            character_names = [str(name) for name in panel.get("characters") or [] if str(name).strip()]
            character_desc = []
            for name in character_names:
                profile = profiles.get(name)
                if profile:
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
                        ]
                        if part
                    )
                    character_desc.append(desc)
                    continue
                character = characters.get(name)
                if not character:
                    character_desc.append(name)
                    continue
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
3. panels 要覆盖完整剧情节拍，建议每场至少 2-4 个 panel，远景/中景/特写/大宽格交替，避免连续同景别。
4. dialogue_bubbles 写本格可见对白气泡，sound_effect 写拟声词或环境声，negative_prompt 写需要避免的画面问题。
5. image_prompt 必须复用上方角色视觉档案，不允许只写“某人醒来”“递合同”等剧情短句；没有明确角色外貌时也要写身份、年龄、体型、发型、服装和稳定视觉标签。
6. 如果项目参考素材里有 character/background/style/world/reference，请把参考意图写入 image_prompt，供后续图生图或人工关联。
7. 保持角色外观、服装、场景和视觉风格一致。
8. 输出严格 JSON。

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
      "camera_hint": "镜头",
      "camera_angle": "平视/俯视/仰视/过肩/主观视角",
      "camera_motion": "推/拉/摇/移/静止",
      "shot_size": "远景/中景/特写/大宽格/窄格",
      "composition": "构图说明",
      "blocking": "角色站位和调度",
      "characters": ["角色"],
      "action": "动作",
      "emotion": "情绪",
      "props": ["关键道具"],
      "dialogue_bubbles": ["对白气泡"],
      "sound_effect": "音效字",
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
