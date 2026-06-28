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

from app.db.models.asset import Asset
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
        asset = self.session.get(Asset, asset_id)
        if not asset:
            raise ValueError("小说素材不存在")

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
            "novel_title": asset.title,
            "novel_author": asset.author,
            "source_sample": sample_text,
        }
        idea = f"改编小说《{asset.title}》"
        if chapters:
            title_list = "、".join(c.chapter_title for c in chapters[:5] if c.chapter_title)
            if title_list:
                idea += f"，选定章节：{title_list}"

        return self.create_project(
            title=title or f"{asset.title} 改编项目",
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
        effective_visual_style = (visual_style or outline.get("visual_style") or "").strip()
        default_prompt = self._comic_pages_prompt(project, outline, storyboard, page_count, reference_assets, effective_visual_style)
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
        visual_context = self._story_visual_context(outline, reference_assets)
        default_prompt = self._storyboard_prompt(project, script, reference_assets=reference_assets)
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
        self._enhance_storyboard_image_prompts(data, outline, reference_assets)
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
        roles = {"character", "background", "style", "reference"}
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

        synced: list[Character] = []
        changed = False
        for raw_character in outline_characters:
            if not isinstance(raw_character, dict):
                continue
            name = str(raw_character.get("name") or "").strip()
            if not name:
                continue

            character = existing_by_name.get(name)
            if character is None:
                character = Character(
                    name=name,
                    role=self._character_role(raw_character.get("role")),
                    source_types=dumps_json([CharacterSourceType.AI_GENERATED.value]),
                    appearance=str(raw_character.get("appearance") or raw_character.get("image_prompt") or ""),
                    costume_hint=str(raw_character.get("costume_hint") or ""),
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
                self.session.add(CharacterStoryLink(character_id=character.id, story_id=project_id))
            else:
                character.appearance = character.appearance or str(raw_character.get("appearance") or "")
                character.costume_hint = character.costume_hint or str(raw_character.get("costume_hint") or "")
                character.personality = character.personality or str(raw_character.get("personality") or "")
                character.background = character.background or str(raw_character.get("background") or raw_character.get("arc") or "")
                character.age_range = character.age_range or str(raw_character.get("age_range") or "")
                if raw_character.get("portrait_asset_id") and not character.portrait_asset_id:
                    character.portrait_asset_id = str(raw_character.get("portrait_asset_id"))

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

    def _character_role(self, value: Any) -> str:
        text = str(value or "").lower()
        if any(token in text for token in ["主角", "男主", "女主", "protagonist", "lead"]):
            return CharacterRole.PROTAGONIST.value
        if any(token in text for token in ["反派", "敌", "antagonist", "villain"]):
            return CharacterRole.ANTAGONIST.value
        if any(token in text for token in ["路人", "extra"]):
            return CharacterRole.EXTRA.value
        return CharacterRole.SUPPORTING.value

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
    ) -> str:
        chapter_number = storyboard.chapter_number or storyboard.episode_number or 1
        storyboard_data = loads_json(storyboard.data_json)
        reference_text = dumps_json(reference_assets or [])
        effective_visual_style = visual_style or outline.get("visual_style", "")
        return f"""请根据分镜草稿整理成适合漫画生成的 {page_count} 页漫画脚本 JSON。

项目标题：{project.title}
章节：第 {chapter_number} 章
视觉风格：{effective_visual_style}
统一生图风格提示：{outline.get("image_style_prompt", "")}

项目参考资产：
{reference_text}

分镜草稿：
{dumps_json(storyboard_data)}

要求：
1. pages 必须正好 {page_count} 页，page_number 从 1 连续递增。
2. 每页 content 使用【第1格】这样的分格标记，建议每页 3-6 格。
3. 每页应承接 storyboard panels，不要凭空改剧情；可以把多个 panel 合并成一页，也可以把复杂 panel 拆成多格。
4. 每格写清角色、动作、画面、对白气泡、音效和镜头节奏。
5. 每页 image_prompt 是该页关键视觉提示，能直接送到生图。
6. 保持角色外观和视觉风格一致；如果项目参考资产里有 character/background/style/reference，必须把对应参考意图写入 page 的 image_prompt。
7. 输出严格 JSON，不要 Markdown。

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

    def _story_visual_context(self, outline: dict[str, Any], reference_assets: list[dict[str, Any]] | None = None) -> str:
        characters = outline.get("characters") or []
        locations = outline.get("locations") or []
        lines = [
            f"统一视觉风格：{outline.get('visual_style', '')}",
            f"统一生图风格提示：{outline.get('image_style_prompt', '')}",
        ]
        if characters:
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

    def _enhance_storyboard_image_prompts(
        self,
        data: dict[str, Any],
        outline: dict[str, Any],
        reference_assets: list[dict[str, Any]] | None = None,
    ) -> None:
        characters = {
            str(character.get("name")): character
            for character in outline.get("characters") or []
            if isinstance(character, dict) and character.get("name")
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
                    f"景别：{panel.get('shot_size', '')}" if panel.get("shot_size") else "",
                    f"构图：{panel.get('composition', '')}" if panel.get("composition") else "",
                    f"对白气泡：{'；'.join(panel.get('dialogue_bubbles') or [])}" if panel.get("dialogue_bubbles") else "",
                    f"原始画面意图：{prompt}" if prompt else "",
                    "清晰人物脸部，准确手部，电影感光影，竖屏短剧漫画构图，避免文字乱码和多余肢体",
                    reference_hint,
                ]
                if part
            )
            panel["image_prompt"] = enriched
            if not panel.get("negative_prompt"):
                panel["negative_prompt"] = "低清晰度，脸部崩坏，手指错误，多余肢体，文字乱码，角色服装不一致，画风突变"

    def _storyboard_prompt(
        self,
        project: CreativeProject,
        script: ProjectContent,
        reference_assets: list[dict[str, Any]] | None = None,
    ) -> str:
        outline = loads_json(project.outline_json)
        script_data = loads_json(script.data_json)
        visual_context = self._story_visual_context(outline, reference_assets)
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
6. 如果项目参考素材里有 character/background/style/reference，请把参考意图写入 image_prompt，供后续图生图或人工关联。
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
      "image_prompt": "生图提示词",
      "camera_hint": "镜头",
      "shot_size": "远景/中景/特写/大宽格/窄格",
      "composition": "构图说明",
      "characters": ["角色"],
      "action": "动作",
      "emotion": "情绪",
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
