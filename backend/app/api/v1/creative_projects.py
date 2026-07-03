"""Creative project workflow API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db.database import get_session
from app.db.models.creative_project import (
    CreativeProject,
    ProjectAssetLink,
    ProjectContent,
    ProjectGenerationLog,
)
from app.services.creative_project.service import (
    CreativeProjectService,
    loads_json,
)

router = APIRouter()


class CreativeProjectCreateRequest(BaseModel):
    title: str = ""
    idea: str = ""
    project_type: str = "short_drama"
    source_type: str = "original_idea"
    source_ref: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreativeProjectUpdateRequest(BaseModel):
    title: str | None = None
    project_type: str | None = None
    source_type: str | None = None
    status: str | None = None
    current_stage: str | None = None
    source_ref: dict[str, Any] | None = None
    outline: dict[str, Any] | None = None
    chapter_plan: dict[str, Any] | None = None
    settings: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    canvas: dict[str, Any] | None = None


class FillDemoDataRequest(BaseModel):
    overwrite: bool = Field(default=False, description="是否覆盖项目已有阶段内容")


class GenerateOutlineRequest(BaseModel):
    idea: str = ""
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None


class GenerateChapterPlanRequest(BaseModel):
    chapter_count: int = Field(default=12, ge=1, le=200)
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None


class GenerateScriptRequest(BaseModel):
    chapter_number: int = Field(default=1, ge=1)
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None


class GenerateChapterOutlineRequest(BaseModel):
    chapter_number: int = Field(default=1, ge=1)
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None


class GenerateNovelBodyRequest(BaseModel):
    chapter_number: int = Field(default=1, ge=1)
    content_id: str | None = None
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None


class RefineNovelBodyRequest(BaseModel):
    content_id: str
    instruction: str
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None


class SplitComicPagesRequest(BaseModel):
    chapter_number: int = Field(default=1, ge=1)
    content_id: str | None = None
    page_count: int = Field(default=10, ge=1, le=80)
    visual_style: str | None = None
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None


class GenerateStoryboardRequest(BaseModel):
    content_id: str
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None


class MatchReferenceAssetsRequest(BaseModel):
    content_id: str
    provider: str | None = None
    model: str | None = None


class CreateFromNovelRequest(BaseModel):
    asset_id: str
    chapter_ids: list[str] = Field(default_factory=list)
    chapter_indices: list[int] = Field(default_factory=list)
    title: str = ""
    project_type: str = "short_drama"


class ProjectAssetLinkRequest(BaseModel):
    asset_id: str
    content_id: str | None = None
    role: str = "reference"
    relation: str = "references"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectContentUpdateRequest(BaseModel):
    title: str | None = None
    data: dict[str, Any] | None = None
    text_content: str | None = None
    is_locked: bool | None = None


class RegenerateChapterOutlineScenesRequest(BaseModel):
    content_id: str
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None


class CanvasSaveRequest(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    viewport: dict[str, Any] = Field(default_factory=dict)


class RunPipelineRequest(BaseModel):
    stages: list[str] = Field(default_factory=list)
    chapters: list[int] = Field(default_factory=list)
    chapter_count: int | None = Field(default=None, ge=1, le=200)
    page_count: int = Field(default=10, ge=1, le=80)
    visual_style: str | None = None
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None
    skip_existing: bool = True
    continue_on_error: bool = False
    match_source_type: str = "storyboard"


def service(session: Session = Depends(get_session)) -> CreativeProjectService:
    return CreativeProjectService(session)


@router.get("", summary="列出创作项目")
def list_projects(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = None,
    project_type: str | None = None,
    svc: CreativeProjectService = Depends(service),
):
    projects, total = svc.list_projects(
        limit=limit,
        offset=offset,
        status=status,
        project_type=project_type,
    )
    return {
        "success": True,
        "data": [serialize_project(p) for p in projects],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("", summary="创建创作项目")
def create_project(
    req: CreativeProjectCreateRequest,
    svc: CreativeProjectService = Depends(service),
):
    project = svc.create_project(
        title=req.title,
        idea=req.idea,
        project_type=req.project_type,
        source_type=req.source_type,
        source_ref=req.source_ref,
        settings=req.settings,
        metadata=req.metadata,
    )
    return {"success": True, "data": serialize_project(project)}


@router.post("/from-novel", summary="从小说章节创建创作项目")
def create_from_novel(
    req: CreateFromNovelRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        project = svc.create_from_novel(
            asset_id=req.asset_id,
            chapter_ids=req.chapter_ids,
            chapter_indices=req.chapter_indices,
            title=req.title,
            project_type=req.project_type,
        )
        return {"success": True, "data": serialize_project(project)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{project_id}", summary="获取创作项目详情")
def get_project(
    project_id: str,
    svc: CreativeProjectService = Depends(service),
):
    project = svc.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="创作项目不存在")
    return {"success": True, "data": serialize_project(project)}


@router.patch("/{project_id}", summary="更新创作项目")
def update_project(
    project_id: str,
    req: CreativeProjectUpdateRequest,
    svc: CreativeProjectService = Depends(service),
):
    data = req.model_dump(exclude_unset=True)
    project = svc.update_project(project_id, data)
    if not project:
        raise HTTPException(status_code=404, detail="创作项目不存在")
    return {"success": True, "data": serialize_project(project)}


@router.delete("/{project_id}", summary="删除创作项目")
def delete_project(
    project_id: str,
    svc: CreativeProjectService = Depends(service),
):
    try:
        stats = svc.delete_project(project_id)
        return {"success": True, "data": stats}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{project_id}/fill-demo-data", summary="为创作项目补充示例大纲、正文、脚本和分镜")
def fill_demo_data(
    project_id: str,
    req: FillDemoDataRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        result = svc.fill_demo_data(project_id, overwrite=req.overwrite)
        return {
            "success": True,
            "data": result["changed"],
            "project": serialize_project(result["project"]),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{project_id}/generate-outline", summary="生成故事大纲")
async def generate_outline(
    project_id: str,
    req: GenerateOutlineRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = await svc.generate_outline(
            project_id,
            idea=req.idea,
            provider=req.provider,
            model=req.model,
            template_id=req.template_id,
        )
        project = svc.get_project(project_id)
        return {"success": True, "data": data, "project": serialize_project(project) if project else None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/generate-chapter-plan", summary="生成章节规划")
async def generate_chapter_plan(
    project_id: str,
    req: GenerateChapterPlanRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = await svc.generate_chapter_plan(
            project_id,
            chapter_count=req.chapter_count,
            provider=req.provider,
            model=req.model,
            template_id=req.template_id,
        )
        project = svc.get_project(project_id)
        return {"success": True, "data": data, "project": serialize_project(project) if project else None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/run-pipeline", summary="Run creative project production pipeline")
async def run_pipeline(
    project_id: str,
    req: RunPipelineRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = await svc.run_pipeline(
            project_id,
            stages=req.stages,
            chapters=req.chapters,
            chapter_count=req.chapter_count,
            page_count=req.page_count,
            visual_style=req.visual_style,
            provider=req.provider,
            model=req.model,
            template_id=req.template_id,
            skip_existing=req.skip_existing,
            continue_on_error=req.continue_on_error,
            match_source_type=req.match_source_type,
        )
        project = svc.get_project(project_id)
        return {"success": True, "data": data, "project": serialize_project(project) if project else None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/generate-script", summary="生成短剧脚本")
async def generate_script(
    project_id: str,
    req: GenerateScriptRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = await svc.generate_script(
            project_id,
            chapter_number=req.chapter_number,
            provider=req.provider,
            model=req.model,
            template_id=req.template_id,
        )
        return {"success": True, "data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/generate-chapter-outline", summary="生成单话细纲")
async def generate_chapter_outline(
    project_id: str,
    req: GenerateChapterOutlineRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = await svc.generate_chapter_outline(
            project_id,
            chapter_number=req.chapter_number,
            provider=req.provider,
            model=req.model,
            template_id=req.template_id,
        )
        project = svc.get_project(project_id)
        return {"success": True, "data": data, "project": serialize_project(project) if project else None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/generate-novel-body", summary="生成章节正文")
async def generate_novel_body(
    project_id: str,
    req: GenerateNovelBodyRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = await svc.generate_novel_body(
            project_id,
            chapter_number=req.chapter_number,
            content_id=req.content_id,
            provider=req.provider,
            model=req.model,
            template_id=req.template_id,
        )
        project = svc.get_project(project_id)
        return {"success": True, "data": data, "project": serialize_project(project) if project else None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/refine-novel-body", summary="按中文要求微调章节正文")
async def refine_novel_body(
    project_id: str,
    req: RefineNovelBodyRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        content = await svc.refine_novel_body(
            project_id=project_id,
            content_id=req.content_id,
            instruction=req.instruction,
            provider=req.provider,
            model=req.model,
            template_id=req.template_id,
        )
        return {"success": True, "data": serialize_content(content)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/split-comic-pages", summary="拆分漫画页")
async def split_comic_pages(
    project_id: str,
    req: SplitComicPagesRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = await svc.split_comic_pages(
            project_id,
            chapter_number=req.chapter_number,
            content_id=req.content_id,
            page_count=req.page_count,
            visual_style=req.visual_style,
            provider=req.provider,
            model=req.model,
            template_id=req.template_id,
        )
        project = svc.get_project(project_id)
        return {"success": True, "data": data, "project": serialize_project(project) if project else None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/generate-storyboard", summary="生成分镜草稿")
async def generate_storyboard(
    project_id: str,
    req: GenerateStoryboardRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = await svc.generate_storyboard(
            project_id,
            content_id=req.content_id,
            provider=req.provider,
            model=req.model,
            template_id=req.template_id,
        )
        return {"success": True, "data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/match-reference-assets", summary="AI 匹配脚本/分镜参考卡")
async def match_reference_assets(
    project_id: str,
    req: MatchReferenceAssetsRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        content = await svc.match_reference_assets(
            project_id,
            content_id=req.content_id,
            provider=req.provider,
            model=req.model,
        )
        return {"success": True, "data": serialize_content(content)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{project_id}/contents", summary="列出项目阶段内容")
def list_contents(
    project_id: str,
    content_type: str | None = None,
    svc: CreativeProjectService = Depends(service),
):
    if not svc.get_project(project_id):
        raise HTTPException(status_code=404, detail="创作项目不存在")
    contents = svc.list_contents(project_id, content_type=content_type)
    return {"success": True, "data": [serialize_content(c) for c in contents]}


@router.patch("/{project_id}/contents/{content_id}", summary="保存项目阶段内容")
def update_content(
    project_id: str,
    content_id: str,
    req: ProjectContentUpdateRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        content = svc.update_content(
            project_id=project_id,
            content_id=content_id,
            title=req.title,
            data=req.data,
            text_content=req.text_content,
            is_locked=req.is_locked,
        )
        return {"success": True, "data": serialize_content(content)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/regenerate-chapter-outline-scenes", summary="只重生成单话细纲场景")
async def regenerate_chapter_outline_scenes(
    project_id: str,
    req: RegenerateChapterOutlineScenesRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        content = await svc.regenerate_chapter_outline_scenes(
            project_id=project_id,
            content_id=req.content_id,
            provider=req.provider,
            model=req.model,
            template_id=req.template_id,
        )
        return {"success": True, "data": serialize_content(content)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{project_id}/assets", summary="列出项目素材关联")
def list_project_assets(
    project_id: str,
    svc: CreativeProjectService = Depends(service),
):
    if not svc.get_project(project_id):
        raise HTTPException(status_code=404, detail="创作项目不存在")
    links = svc.list_asset_links(project_id)
    return {"success": True, "data": [serialize_asset_link(link) for link in links]}


@router.get("/{project_id}/generation-logs", summary="列出项目生成日志")
def list_generation_logs(
    project_id: str,
    stage: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    svc: CreativeProjectService = Depends(service),
):
    try:
        logs, total = svc.list_generation_logs(
            project_id,
            stage=stage,
            status=status,
            limit=limit,
            offset=offset,
        )
        return {
            "success": True,
            "data": [serialize_generation_log(log) for log in logs],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/logs/generation", summary="跨项目查询生成日志")
def list_generation_logs_global(
    scene: str | None = None,
    ref_id: str | None = None,
    stage: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    svc: CreativeProjectService = Depends(service),
):
    """
    跨项目查询生成日志，支持按 scene / ref_id 过滤。

    典型用法：
    - GET /api/v1/creative-projects/logs/generation?scene=character_portrait
    - GET /api/v1/creative-projects/logs/generation?scene=character_portrait&ref_id={character_id}
    """
    logs, total = svc.list_generation_logs(
        project_id=None,
        scene=scene,
        ref_id=ref_id,
        stage=stage,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {
        "success": True,
        "data": [serialize_generation_log(log) for log in logs],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/{project_id}/assets", summary="关联项目素材")
def link_project_asset(
    project_id: str,
    req: ProjectAssetLinkRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        link = svc.link_asset(
            project_id=project_id,
            asset_id=req.asset_id,
            content_id=req.content_id,
            role=req.role,
            relation=req.relation,
            metadata=req.metadata,
        )
        return {"success": True, "data": serialize_asset_link(link)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/sync-characters", summary="同步大纲角色到角色库")
def sync_project_characters(
    project_id: str,
    svc: CreativeProjectService = Depends(service),
):
    try:
        characters = svc.sync_outline_characters(project_id)
        project = svc.get_project(project_id)
        return {
            "success": True,
            "data": [serialize_character(item) for item in characters],
            "project": serialize_project(project) if project else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{project_id}/canvas", summary="获取项目画布状态")
def get_canvas(
    project_id: str,
    svc: CreativeProjectService = Depends(service),
):
    try:
        return {"success": True, "data": svc.get_canvas(project_id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/{project_id}/canvas", summary="保存项目画布状态")
def save_canvas(
    project_id: str,
    req: CanvasSaveRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = svc.save_canvas(project_id, req.model_dump())
        return {"success": True, "data": data}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


def serialize_project(project: CreativeProject | None) -> dict[str, Any] | None:
    if project is None:
        return None
    return {
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


def serialize_content(content: ProjectContent) -> dict[str, Any]:
    return {
        "id": content.id,
        "project_id": content.project_id,
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


def serialize_asset_link(link: ProjectAssetLink) -> dict[str, Any]:
    return {
        "id": link.id,
        "project_id": link.project_id,
        "asset_id": link.asset_id,
        "content_id": link.content_id,
        "role": link.role,
        "relation": link.relation,
        "metadata": loads_json(link.metadata_json),
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


def serialize_generation_log(log: ProjectGenerationLog) -> dict[str, Any]:
    request = loads_json(log.request_json)
    normalized = loads_json(log.normalized_json)
    return {
        "id": log.id,
        "project_id": log.project_id,
        "content_id": log.content_id,
        "scene": log.scene,
        "ref_id": log.ref_id,
        "stage": log.stage,
        "provider": log.provider,
        "model": log.model,
        "status": log.status,
        "prompt": log.prompt,
        "request": request,
        "prompt_template": request.get("prompt_template") if isinstance(request, dict) else None,
        "raw_response": log.raw_response,
        "normalized": normalized,
        "validation_error": log.validation_error,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def serialize_character(character: Any) -> dict[str, Any]:
    return {
        "id": character.id,
        "name": character.name,
        "role": character.role,
        "appearance": character.appearance,
        "personality": character.personality,
        "costume_hint": character.costume_hint,
        "signature_items": loads_json(getattr(character, "signature_items", "[]"), []),
        "expressions": loads_json(getattr(character, "expressions", "[]"), []),
        "poses": loads_json(getattr(character, "poses", "[]"), []),
        "visual_consistency": getattr(character, "visual_consistency", "") or "",
        "background": character.background,
        "age_range": character.age_range,
        "portrait_url": getattr(character, "portrait_url", "") or "",
        "portrait_asset_id": character.portrait_asset_id,
        "portrait_node_id": getattr(character, "portrait_node_id", None),
        "reference_asset_ids": loads_json(character.reference_asset_ids, []),
        "created_at": character.created_at.isoformat() if character.created_at else None,
        "updated_at": character.updated_at.isoformat() if character.updated_at else None,
    }
