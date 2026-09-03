"""小说来源与世界提取 API。

真人用户和 Agent 走同一套契约：先预览（候选 + 证据），再显式确认写入项目。
提取接口默认不写项目事实，``apply`` 是独立且幂等的收口动作。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import time

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db.database import get_session
from app.db.models.character import Character, CharacterStoryLink
from app.db.models.creative_project import CreativeProject, ProjectContent
from app.db.models.novel_source import (
    CandidateOrigin,
    NovelSourceChapter,
    NovelSourceSnapshot,
    NovelTextChunk,
    WorldDomainDefinition,
    WorldEntity,
    WorldEntityRelation,
    WorldExtractionRun,
    WorldFactCandidate,
    WorldMapDocument,
)
from app.services.novel_source.world_map_visual import (
    generate_map_visual,
    optimize_map_visual_prompt,
)
from app.services.creative_project.service import loads_json
from app.services.novel_source.contracts import DETECTABLE_DOMAINS, EXTRACTABLE_DOMAINS
from app.services.novel_source.extraction import WorldExtractionService
from app.services.novel_source.service import NovelSourceService
from app.services.novel_source.world_domains import WorldDomainService
from app.services.novel_source.world_generation import WorldGenerationService
from app.services.novel_source.world_map import (
    WorldMapService,
    build_map_export,
    build_map_visual_prompt,
    render_map_svg,
    serialize_map,
)

def _local_file_url(path_or_url: str) -> str:
    """本地文件 → 平台内部下载地址（与角色立绘一致，本地已落盘的成图优先展示）。"""
    if not path_or_url:
        return ""
    if path_or_url.startswith(("/api/", "http://", "https://", "data:")):
        return path_or_url
    from app.services.asset_file_resolver import to_asset_download_url

    return to_asset_download_url(path_or_url)


router = APIRouter()
logger = logging.getLogger("ylcraft.novel_sources_api")

MAX_TXT_BYTES = 30 * 1024 * 1024
ALLOWED_TXT_SUFFIXES = (".txt", ".text", ".md")


class ImportBookshelfRequest(BaseModel):
    title: str = ""
    author: str = ""
    source_status: str = "serial"
    project_id: str | None = None
    source_asset_id: str | None = None
    chapters: list[dict[str, Any]] = Field(default_factory=list)


class SyncChaptersRequest(BaseModel):
    chapters: list[dict[str, Any]] = Field(default_factory=list)


class DomainPlanRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    requested_domains: list[str] | None = None
    sample_chunks: int = 6


class ExtractRequest(BaseModel):
    domains: list[str] | None = None
    domain_plan: list[dict[str, Any]] | None = None
    project_id: str | None = None
    provider: str | None = None
    model: str | None = None
    mode: str = "full"
    max_chunks: int = 60


class IndexChunksRequest(BaseModel):
    provider: str | None = None
    max_chunks: int = 2000


class SearchChunksRequest(BaseModel):
    query: str
    query_embedding: list[float] | None = None
    top_k: int = 10
    with_neighbors: int = 0


class CandidateDecision(BaseModel):
    candidate_id: str
    action: str = "accept"
    note: str = ""
    merge_into: str = ""


class DecideRequest(BaseModel):
    decisions: list[CandidateDecision] = Field(default_factory=list)


class ApplyRequest(BaseModel):
    project_id: str | None = None


class DeriveProjectRequest(BaseModel):
    derivation_kind: str = "continuation"
    title: str = ""
    project_type: str = "novel"


class ContradictionRequest(BaseModel):
    provider: str | None = None
    model: str | None = None


class AffectedFactsRequest(BaseModel):
    verdicts: list[dict[str, Any]] | None = None


class WorldMapCreateRequest(BaseModel):
    title: str = "世界地图"
    project_id: str | None = None
    snapshot_id: str | None = None
    map_json: dict[str, Any] | None = None


class WorldMapUpdateRequest(BaseModel):
    title: str = ""
    map_json: dict[str, Any] = Field(default_factory=dict)
    expected_revision: int = 1


class WorldDomainUpsertRequest(BaseModel):
    """项目级世界模块定义：覆盖内置模块，或新增自定义模块。"""

    label: str = Field(default="", description="展示名（留空沿用内置）")
    entity_type: str = Field(default="", description="自定义模块的实体类型（内置模块不可改）")
    extra_attributes: list[str] = Field(
        default_factory=list, description="追加的属性字段（内置字段不可删除）"
    )
    prompt_hint: str = Field(default="", description="提取提示（留空沿用内置）")
    is_enabled: bool = Field(default=True, description="是否启用该模块")
    source: str = Field(
        default="",
        description="来源：builtin_override / custom / ai_suggested（留空自动判定）",
    )


class WorldMapVisualRequest(BaseModel):
    prompt: str = Field(default="", description="提示词（留空则按结构化地图自动生成）")
    negative_prompt: str = Field(default="", description="负向提示词")
    provider: str = Field(default="", description="指定生图后端（image backend name）")
    model: str = Field(default="", description="动态指定模型名（控制花费）")
    size: str = Field(default="1024x1024", description="图片尺寸")
    n: int = Field(default=1, description="生成数量（>1 时取首张）")
    style: str = Field(default="", description="画风（如水墨、写实）")
    reference_images: list[str] = Field(default_factory=list, description="参考图 URL/base64 列表")
    save_to_asset_hub: bool = Field(default=True, description="是否入资产中枢（素材库）")


class WorldMapVisualPromptRequest(BaseModel):
    style_override: str = Field(default="", description="画风覆盖")
    prompt_override: str = Field(default="", description="提示词覆盖（留空则按结构化地图自动生成）")


class WorldMapVisualOptimizeRequest(BaseModel):
    """用 LLM 润色地图生图提示词（只改写提示词、不生成图、不落库）。"""

    prompt: str = Field(default="", description="待优化提示词（留空则先按结构化地图生成）")
    style: str = Field(default="", description="风格要求")
    focus: str = Field(default="", description="希望强调或修正的画面要点（可选）")
    provider: str = Field(default="")
    model: str = Field(default="")


class ProjectWorldExtractionStartRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    domains: list[str] | None = None
    force_reimport: bool = Field(default=False, description="是否忽略已绑定的来源快照，重新导入")


class CreateProjectFromNovelSourceRequest(BaseModel):
    snapshot_id: str
    title: str = ""
    project_type: str = "novel"


def serialize_outline_as_source_text(outline: dict[str, Any]) -> str:
    """把创作项目大纲序列化为可回溯的来源文本，供逐域世界提取管线使用。

    每个字段带【节】标记，AI 提取时引用的引文必须逐字落在该文本中，
    从而通过证据校验（与小说来源一致）。
    """
    lines: list[str] = []

    def add(section: str, value: Any) -> None:
        if value in (None, "", [], {}):
            return
        lines.append(f"【{section}】")
        if isinstance(value, str):
            lines.append(value)
        elif isinstance(value, list):
            lines.extend(str(item) for item in value if str(item).strip())
        elif isinstance(value, dict):
            for key, item in value.items():
                if item not in (None, ""):
                    lines.append(f"{key}：{item}")

    add("题材", outline.get("genre"))
    add("故事前提", outline.get("premise"))
    add("一句话梗概", outline.get("logline"))
    add("卖点", outline.get("selling_points"))
    add("目标读者", outline.get("target_reader"))
    add("受众情绪", outline.get("audience_emotion"))
    add("基调", outline.get("tone"))
    add("世界观", outline.get("worldview"))
    add("叙事规则", outline.get("narrative_rules"))
    add("核心冲突", outline.get("main_conflict"))
    add("主题", outline.get("themes"))

    character_fields = (
        ("name", "姓名"), ("role", "定位"), ("age_range", "年龄"), ("appearance", "外貌"),
        ("costume_hint", "服装"), ("personality", "性格"), ("background", "背景"),
        ("goal", "目标"), ("arc", "弧光"), ("voice", "音色"),
    )
    for index, character in enumerate(outline.get("characters") or [], start=1):
        if not isinstance(character, dict):
            continue
        lines.append(f"【角色 {index}】")
        for key, label in character_fields:
            value = character.get(key)
            if value not in (None, ""):
                lines.append(f"{label}：{value}")

    location_fields = (
        ("name", "名称"), ("role", "作用"), ("visual_description", "外观"),
        ("mood", "氛围"), ("reusable_asset_note", "复用备注"),
    )
    for index, location in enumerate(outline.get("locations") or [], start=1):
        if not isinstance(location, dict):
            continue
        lines.append(f"【地点 {index}】")
        for key, label in location_fields:
            value = location.get(key)
            if value not in (None, ""):
                lines.append(f"{label}：{value}")

    add("关系图谱", outline.get("relationship_map"))
    story_arc = outline.get("story_arc")
    if isinstance(story_arc, dict):
        add("故事开端", story_arc.get("beginning"))
        add("故事中段", story_arc.get("middle"))
        add("高潮", story_arc.get("climax"))
        add("结局方向", story_arc.get("ending_direction"))
    add("视觉风格", outline.get("visual_style"))
    add("生图风格提示", outline.get("image_style_prompt"))
    add("制作备注", outline.get("production_notes"))

    return "\n".join(line for line in lines if line.strip())


def source_service(session: Session = Depends(get_session)) -> NovelSourceService:
    return NovelSourceService(session)


def extraction_service(session: Session = Depends(get_session)) -> WorldExtractionService:
    return WorldExtractionService(session)


def _require_snapshot(service: NovelSourceService, snapshot_id: str) -> NovelSourceSnapshot:
    snapshot = service.get_snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="来源快照不存在")
    return snapshot


def _require_run(service: WorldExtractionService, run_id: str) -> WorldExtractionRun:
    run = service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="提取运行不存在")
    return run


def serialize_snapshot(snapshot: NovelSourceSnapshot) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "title": snapshot.title,
        "author": snapshot.author,
        "source_kind": snapshot.source_kind,
        "source_status": snapshot.source_status,
        "project_id": snapshot.project_id,
        "source_asset_id": snapshot.source_asset_id,
        "checksum": snapshot.checksum,
        "encoding": snapshot.encoding,
        "revision": snapshot.revision,
        "parent_snapshot_id": snapshot.parent_snapshot_id,
        "chapter_count": snapshot.chapter_count,
        "char_count": snapshot.char_count,
        "last_chapter_ordinal": snapshot.last_chapter_ordinal,
        "indexing_status": snapshot.indexing_status,
        "metadata": loads_json(snapshot.metadata_json, {}),
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "updated_at": snapshot.updated_at.isoformat() if snapshot.updated_at else None,
    }


def serialize_chapter(chapter: NovelSourceChapter) -> dict[str, Any]:
    return {
        "id": chapter.id,
        "ordinal": chapter.ordinal,
        "title": chapter.title,
        "start_offset": chapter.start_offset,
        "end_offset": chapter.end_offset,
        "char_count": chapter.char_count,
        "source_chapter_id": chapter.source_chapter_id,
    }


def serialize_chunk(chunk: NovelTextChunk, *, include_content: bool = True) -> dict[str, Any]:
    payload = {
        "id": chunk.id,
        "ordinal": chunk.ordinal,
        "chapter_id": chunk.chapter_id,
        "start_offset": chunk.start_offset,
        "end_offset": chunk.end_offset,
        "content_hash": chunk.content_hash,
        "embedding_model": chunk.embedding_model,
        "embedding_status": chunk.embedding_status,
    }
    if include_content:
        payload["content"] = chunk.content
    return payload


def serialize_run(run: WorldExtractionRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "snapshot_id": run.snapshot_id,
        "project_id": run.project_id,
        "mode": run.mode,
        "status": run.status,
        "pipeline_version": run.pipeline_version,
        "domains": loads_json(run.domains_json, []),
        "checkpoint": loads_json(run.checkpoint_json, {}),
        "trace": loads_json(run.trace_json, []),
        "diagnostics": loads_json(run.diagnostics_json, {}),
        "provider": run.provider,
        "model": run.model,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }


def serialize_candidate(candidate: WorldFactCandidate) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "run_id": candidate.run_id,
        "last_run_id": candidate.last_run_id,
        "snapshot_id": candidate.snapshot_id,
        "project_id": candidate.project_id,
        "domain": candidate.domain,
        "entity_name": candidate.entity_name,
        "payload": loads_json(candidate.payload_json, {}),
        "evidence": loads_json(candidate.evidence_json, []),
        "confidence": candidate.confidence,
        "origin": candidate.origin,
        "status": candidate.status,
        "target_entity_type": candidate.target_entity_type,
        "target_entity_id": candidate.target_entity_id,
        "review_note": candidate.review_note,
        "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
        "updated_at": candidate.updated_at.isoformat() if candidate.updated_at else None,
    }


def serialize_world_entity(entity: WorldEntity) -> dict[str, Any]:
    return {
        "id": entity.id,
        "project_id": entity.project_id,
        "snapshot_id": entity.snapshot_id,
        "domain": entity.domain,
        "entity_type": entity.entity_type,
        "name": entity.name,
        "summary": entity.summary,
        "attributes": loads_json(entity.attributes_json, {}),
        "evidence": loads_json(entity.evidence_json, []),
        "fact_layer": entity.fact_layer,
        "source_candidate_id": entity.source_candidate_id,
        "is_locked": entity.is_locked,
        "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
    }


def serialize_world_entity_relation(relation: WorldEntityRelation) -> dict[str, Any]:
    return {
        "id": relation.id,
        "project_id": relation.project_id,
        "source_entity_id": relation.source_entity_id,
        "target_entity_id": relation.target_entity_id,
        "relation_type": relation.relation_type,
        "note": relation.note,
        "evidence": loads_json(relation.evidence_json, []),
        "is_directed": relation.is_directed,
    }


@router.post("/api/v1/novel-sources/import-txt", summary="导入本地 TXT 为来源快照")
async def import_txt(
    file: UploadFile = File(...),
    title: str = Form(""),
    author: str = Form(""),
    source_status: str = Form("unknown"),
    project_id: str | None = Form(None),
    source_asset_id: str | None = Form(None),
    svc: NovelSourceService = Depends(source_service),
):
    """上传 TXT 并生成快照、章节和文本块。

    只保存原文与归一化正文，不改写内容；完本/连载状态由调用方声明。
    """
    name = file.filename or "novel.txt"
    if not name.lower().endswith(ALLOWED_TXT_SUFFIXES):
        raise HTTPException(status_code=400, detail="只支持 .txt / .text / .md 文本导入")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="上传文件为空")
    if len(raw) > MAX_TXT_BYTES:
        raise HTTPException(status_code=413, detail="TXT 文件超过 30MB 上限")
    try:
        snapshot = svc.import_txt(
            raw=raw,
            file_name=name,
            title=title,
            author=author,
            source_status=source_status,
            project_id=project_id,
            source_asset_id=source_asset_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": serialize_snapshot(snapshot)}


@router.post("/api/v1/novel-sources/import-bookshelf", summary="导入书架章节为来源快照")
def import_bookshelf(
    req: ImportBookshelfRequest,
    svc: NovelSourceService = Depends(source_service),
):
    """把书架选定章节落到与 TXT 相同的快照契约。"""
    try:
        snapshot = svc.import_bookshelf(
            title=req.title,
            author=req.author,
            chapters=req.chapters,
            source_status=req.source_status,
            project_id=req.project_id,
            source_asset_id=req.source_asset_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": serialize_snapshot(snapshot)}


@router.get("/api/v1/novel-sources", summary="列出来源快照")
def list_snapshots(
    project_id: str | None = Query(None),
    source_kind: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    svc: NovelSourceService = Depends(source_service),
):
    snapshots = svc.list_snapshots(project_id=project_id, source_kind=source_kind, limit=limit)
    return {"success": True, "data": [serialize_snapshot(item) for item in snapshots]}


@router.get("/api/v1/novel-sources/domains", summary="列出可检测的世界模块")
def list_domains():
    """返回模块清单与当前已实现提取的模块，供前端和 Agent 发现能力。"""
    from app.services.novel_source.contracts import BASIC_DOMAINS

    return {
        "success": True,
        "data": {
            "detectable": list(DETECTABLE_DOMAINS),
            "extractable": list(EXTRACTABLE_DOMAINS),
            "basic": list(BASIC_DOMAINS),
        },
    }


@router.get("/api/v1/novel-sources/{snapshot_id}", summary="获取来源快照详情")
def get_snapshot(snapshot_id: str, svc: NovelSourceService = Depends(source_service)):
    return {"success": True, "data": serialize_snapshot(_require_snapshot(svc, snapshot_id))}


@router.get("/api/v1/novel-sources/{snapshot_id}/chapters", summary="列出快照章节")
def list_chapters(
    snapshot_id: str,
    limit: int = Query(200, ge=1, le=2000),
    svc: NovelSourceService = Depends(source_service),
):
    _require_snapshot(svc, snapshot_id)
    chapters = svc.list_chapters(snapshot_id)[:limit]
    return {"success": True, "data": [serialize_chapter(item) for item in chapters]}


@router.get("/api/v1/novel-sources/{snapshot_id}/chunks", summary="列出快照文本块")
def list_chunks(
    snapshot_id: str,
    after_ordinal: int | None = Query(None),
    include_content: bool = Query(True),
    limit: int = Query(200, ge=1, le=2000),
    svc: NovelSourceService = Depends(source_service),
):
    _require_snapshot(svc, snapshot_id)
    chunks = svc.list_chunks(snapshot_id, after_ordinal=after_ordinal, limit=limit)
    return {
        "success": True,
        "data": [serialize_chunk(item, include_content=include_content) for item in chunks],
    }


@router.post("/api/v1/novel-sources/{snapshot_id}/chunks/index", summary="为小说文本块建立向量索引")
async def index_chunks(
    snapshot_id: str,
    req: IndexChunksRequest,
    svc: NovelSourceService = Depends(source_service),
):
    """建立可选向量索引；失败块保留为 failed，来源仍可走精确检索。"""
    _require_snapshot(svc, snapshot_id)
    from app.db.database import AsyncSessionLocal
    from app.services.embedding.service import EmbeddingService

    async with AsyncSessionLocal() as embedding_session:
        embedding_service = EmbeddingService(embedding_session, provider_name=req.provider)
        chunks = svc.list_chunks(snapshot_id, limit=max(1, min(req.max_chunks, 2000)))
        texts = [chunk.content for chunk in chunks]

        async def embedder(values):
            return await embedding_service.embed_texts(values)

        result = await svc.index_chunk_embeddings(
            snapshot_id,
            embedder=embedder,
            model_name=await embedding_service._get_effective_text_model_name(),
            max_chunks=req.max_chunks,
        )
    return {"success": True, "data": result}


@router.post("/api/v1/novel-sources/{snapshot_id}/chunks/search", summary="混合检索小说文本块")
async def search_chunks(
    snapshot_id: str,
    req: SearchChunksRequest,
    svc: NovelSourceService = Depends(source_service),
):
    """返回精确/向量混合召回结果，并保留章节和字符偏移。"""
    _require_snapshot(svc, snapshot_id)
    results = svc.search_chunks(
        snapshot_id,
        req.query,
        query_embedding=req.query_embedding,
        top_k=req.top_k,
        with_neighbors=req.with_neighbors,
    )
    return {"success": True, "data": results}


@router.post("/api/v1/novel-sources/{snapshot_id}/plan", summary="逐模块判断世界设定是否存在")
async def plan_domains(
    snapshot_id: str,
    req: DomainPlanRequest,
    svc: WorldExtractionService = Depends(extraction_service),
):
    """AI 只建议，不代劳：返回每域 detected/not_detected/uncertain 及理由。

    用户或 Agent 可逐域启用、关闭或改写后，把 ``domains`` 原样带回提取接口。
    """
    try:
        plan = await svc.plan_domains(
            snapshot_id,
            provider=req.provider,
            model=req.model,
            requested_domains=req.requested_domains,
            sample_chunks=req.sample_chunks,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": plan}


@router.post("/api/v1/novel-sources/{snapshot_id}/extract", summary="按模块提取世界候选")
async def extract_world(
    snapshot_id: str,
    req: ExtractRequest,
    svc: WorldExtractionService = Depends(extraction_service),
):
    """提取并落为待确认候选，不写项目事实。

    返回 run_id 与每域状态；单个域失败只让整体变 partial。
    """
    try:
        result = await svc.extract(
            snapshot_id,
            domains=req.domains,
            domain_plan=req.domain_plan,
            project_id=req.project_id,
            provider=req.provider,
            model=req.model,
            mode=req.mode,
            max_chunks=req.max_chunks,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": result}


@router.post("/api/v1/novel-sources/{snapshot_id}/derive", summary="从完本来源创建派生项目")
def derive_project(
    snapshot_id: str,
    req: DeriveProjectRequest,
    svc: WorldExtractionService = Depends(extraction_service),
):
    """创建改编/续写/同人派生项目。

    原作正典（已确认世界事实与角色关联）复制进新项目并标记为只读参考层；
    来源快照保持只读，新项目后续写入构成派生层。
    """
    _require_snapshot(svc, snapshot_id)
    try:
        result = svc.derive_project(
            snapshot_id,
            derivation_kind=req.derivation_kind,
            title=req.title,
            project_type=req.project_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": result}


@router.post("/api/v1/novel-sources/{snapshot_id}/sync", summary="连载来源追加新章节")
def sync_chapters(
    snapshot_id: str,
    req: SyncChaptersRequest,
    svc: NovelSourceService = Depends(source_service),
):
    """只追加新章节和新文本块，已导入章节与既有证据锚点保持不变。"""
    try:
        snapshot = svc.append_bookshelf_chapters(snapshot_id, chapters=req.chapters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": serialize_snapshot(snapshot)}


@router.get("/api/v1/world-extraction-runs/{run_id}", summary="获取提取运行状态")
def get_run(run_id: str, svc: WorldExtractionService = Depends(extraction_service)):
    return {"success": True, "data": serialize_run(_require_run(svc, run_id))}


@router.get("/api/v1/world-extraction-runs/{run_id}/candidates", summary="预览提取候选与证据")
def list_candidates(
    run_id: str,
    domain: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    svc: WorldExtractionService = Depends(extraction_service),
):
    """候选预览：每条都带逐字原文证据与文本块锚点。"""
    _require_run(svc, run_id)
    candidates = svc.list_candidates(run_id, domain=domain, status=status, limit=limit)
    return {"success": True, "data": [serialize_candidate(item) for item in candidates]}


@router.get("/api/v1/world-extraction-runs/{run_id}/reconcile", summary="跨域调和候选提示")
def reconcile_run(run_id: str, svc: WorldExtractionService = Depends(extraction_service)):
    """确定性找出跨模块重复、别名交叉、证据重叠与时序问题。

    只读提示，不调用模型，也不会自动合并或删除候选；取舍仍由真人或 Agent 决策。
    """
    _require_run(svc, run_id)
    return {"success": True, "data": svc.reconcile_run(run_id)}


@router.post("/api/v1/world-extraction-runs/{run_id}/contradictions", summary="判断重复候选是否同一实体或矛盾")
async def detect_contradictions(
    run_id: str,
    req: ContradictionRequest,
    svc: WorldExtractionService = Depends(extraction_service),
):
    """对调和发现的重复组做语义判断，只作审阅提示，不自动合并。"""
    _require_run(svc, run_id)
    try:
        result = await svc.detect_contradictions(
            run_id, provider=req.provider, model=req.model
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": result}


@router.post("/api/v1/world-extraction-runs/{run_id}/affected-facts", summary="把合并/矛盾结论传播到已写事实")
def propagate_affected_facts(
    run_id: str,
    req: AffectedFactsRequest,
    svc: WorldExtractionService = Depends(extraction_service),
):
    """把已写入的 world_asset 事实标记为待复核。

    候选被 merge 或判定为冲突后，其此前写入的事实可能不完整或不可信；
    这里只打 ``review_required`` 标记并附原因，不改写事实内容。
    """
    _require_run(svc, run_id)
    try:
        result = svc.propagate_affected_facts(run_id, verdicts=req.verdicts)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": result}


@router.post("/api/v1/world-extraction-runs/{run_id}/candidates/decide", summary="标记候选为接受或忽略")
def decide_candidates(
    run_id: str,
    req: DecideRequest,
    svc: WorldExtractionService = Depends(extraction_service),
):
    """决策只改候选状态，不写项目事实。"""
    _require_run(svc, run_id)
    result = svc.decide_candidates(
        run_id,
        [item.model_dump() for item in req.decisions],
    )
    return {"success": True, "data": result}


@router.post("/api/v1/world-extraction-runs/{run_id}/apply", summary="确认候选并写入项目")
async def apply_run(
    run_id: str,
    req: ApplyRequest,
    svc: WorldExtractionService = Depends(extraction_service),
):
    """把已接受的候选写入项目：角色进角色库，其余进锁定的 world_asset 事实卡。

    未携带 project_id 时按来源快照自动创建一个世界项目。
    """
    _require_run(svc, run_id)
    try:
        result = await svc.apply_run(run_id, project_id=req.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": result}


@router.post("/api/v1/creative-projects/from-novel-source", summary="从来源快照创建世界项目")
def create_project_from_novel_source(
    req: CreateProjectFromNovelSourceRequest,
    svc: WorldExtractionService = Depends(extraction_service),
):
    """从已导入的来源快照创建并绑定世界项目（design API ``from-novel-source``）。

    幂等：快照已绑定项目时直接返回既有项目。创建后可在 /novel-world 里
    对同一来源继续提取/审阅，或在该项目里追加世界设定。
    """
    snapshot = svc.sources.get_snapshot(req.snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="来源快照不存在")
    if snapshot.project_id:
        return {"success": True, "data": {"project_id": snapshot.project_id, "reused": True}}

    from app.services.creative_project.service import CreativeProjectService

    creative = CreativeProjectService(svc.session, ai_service=svc.ai_service)
    project = creative.create_project(
        title=(req.title or "").strip() or f"{snapshot.title or '未命名小说'} 世界项目",
        project_type=req.project_type or "novel",
        source_type="novel",
        source_ref={"novel_snapshot_id": snapshot.id},
        idea=f"基于来源《{snapshot.title or '未命名小说'}》建立世界设定",
        metadata={"novel_snapshot_id": snapshot.id},
    )
    snapshot.project_id = project.id
    snapshot.updated_at = datetime.now()
    svc.session.add(snapshot)
    svc.session.commit()
    return {"success": True, "data": {"project_id": project.id, "reused": False}}


@router.post("/api/v1/creative-projects/{project_id}/world-extraction/start", summary="从项目内容启动世界提取")
async def start_project_world_extraction(
    project_id: str,
    req: ProjectWorldExtractionStartRequest,
    svc: WorldExtractionService = Depends(extraction_service),
):
    """把创作项目大纲序列化为来源文本，启动逐域世界提取，产出待确认候选。

    与小说来源共用同一套提取/证据/候选管线；候选在 /novel-world 审阅确认后
    apply 回本项目。项目已绑定来源快照时复用（可用 ``force_reimport`` 重来）。
    """
    project = svc.session.get(CreativeProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="创作项目不存在")

    snapshot = None
    if not req.force_reimport:
        snapshot = svc.session.exec(
            select(NovelSourceSnapshot)
            .where(NovelSourceSnapshot.project_id == project_id)
            .order_by(NovelSourceSnapshot.created_at.desc())
        ).first()

    if snapshot is None:
        outline = loads_json(project.outline_json, {})
        text = serialize_outline_as_source_text(outline if isinstance(outline, dict) else {})
        if not text.strip():
            raise HTTPException(status_code=400, detail="项目还没有大纲内容，请先生成故事大纲")
        snapshot = svc.sources.import_txt(
            raw=text.encode("utf-8"),
            file_name=f"outline-{project_id}.txt",
            title=f"{project.title or '未命名'} 世界设定",
            source_status="completed",
            project_id=project_id,
        )

    result = await svc.extract(
        snapshot.id,
        # 有意的产品选择：本入口是「从大纲一次性生成整套世界设定候选」，大纲文本短、
        # 一次性，用户期待连世界观/力量体系/经济等扩展设定一起看到，所以默认跑全部
        # 可提取模块。其它入口（小说来源提取、Agent 工具）不指定模块时由服务层回落
        # 到基础层（角色/地点/势力/历史事件），避免扩展模块产生空候选噪声。
        domains=req.domains or list(EXTRACTABLE_DOMAINS),
        project_id=project_id,
        # 来源性质：这里的「原文」是项目大纲，不是某部真实作品——候选标记 outline，
        # 让 UI 能说明「依据来自你的大纲」，而不是伪装成原著出处。
        candidate_origin=CandidateOrigin.OUTLINE.value,
        provider=req.provider,
        model=req.model,
    )
    return {
        "success": True,
        "data": {
            "project_id": project_id,
            "snapshot_id": snapshot.id,
            "run_id": result.get("run_id", ""),
            "candidate_count": int(result.get("candidate_count", 0)),
            "status": result.get("status", ""),
        },
    }


@router.get("/api/v1/projects/{project_id}/world-entities", summary="列出项目类型化世界实体")
def list_project_world_entities(
    project_id: str,
    domain: str | None = Query(None),
    entity_type: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    svc: WorldExtractionService = Depends(extraction_service),
):
    """确认写入后物化的独立实体（势力/地点/物种/事件/力量体系/物品等）。"""
    entities = svc.list_world_entities(
        project_id, domain=domain, entity_type=entity_type, limit=limit
    )
    return {"success": True, "data": [serialize_world_entity(item) for item in entities]}


@router.get("/api/v1/projects/{project_id}/world-entity-relations", summary="列出项目类型化实体关系")
def list_project_world_entity_relations(
    project_id: str,
    limit: int = Query(500, ge=1, le=2000),
    svc: WorldExtractionService = Depends(extraction_service),
):
    """复杂实体间的类型化关系（势力敌对/地盘、事件发生地、物种栖息地等）。"""
    relations = svc.list_world_entity_relations(project_id, limit=limit)
    return {"success": True, "data": [serialize_world_entity_relation(item) for item in relations]}


@router.get("/api/v1/creative-projects/{project_id}/world-knowledge", summary="聚合项目世界知识")
def get_project_world_knowledge(
    project_id: str,
    session: Session = Depends(get_session),
):
    """项目世界知识的统一聚合视图（design API world-knowledge）。

    供 Agent/上下文一次取全：角色（项目关联）、类型化实体（按域）、
    实体关系、锁定事实卡、地图文档与来源快照。任意子集为空不影响返回。
    """
    project = session.get(CreativeProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="创作项目不存在")

    entities = session.exec(
        select(WorldEntity)
        .where(WorldEntity.project_id == project_id)
        .order_by(WorldEntity.entity_type, WorldEntity.name)
    ).all()
    relations = session.exec(
        select(WorldEntityRelation).where(WorldEntityRelation.project_id == project_id)
    ).all()
    facts = session.exec(
        select(ProjectContent)
        .where(
            ProjectContent.project_id == project_id,
            ProjectContent.content_type == "world_asset",
        )
        .order_by(ProjectContent.title)
    ).all()
    maps = session.exec(
        select(WorldMapDocument)
        .where(WorldMapDocument.project_id == project_id)
        .order_by(WorldMapDocument.updated_at.desc())
    ).all()
    snapshots = session.exec(
        select(NovelSourceSnapshot)
        .where(NovelSourceSnapshot.project_id == project_id)
        .order_by(NovelSourceSnapshot.created_at.desc())
    ).all()
    links = session.exec(
        select(CharacterStoryLink).where(CharacterStoryLink.story_id == project_id)
    ).all()

    characters: list[dict[str, Any]] = []
    for link in links:
        character = session.get(Character, str(link.character_id))
        if not character:
            continue
        characters.append(
            {
                "character_id": character.id,
                "name": character.name,
                "role": character.role,
                "aliases": loads_json(link.aliases_json, []),
                "evidence": loads_json(link.evidence_json, []),
                "world_name": link.world_name,
                "extract_origin": link.extract_origin,
            }
        )

    entity_by_id = {entity.id: entity for entity in entities}
    relations_view = [
        {
            "source_entity_id": item.source_entity_id,
            "source_name": entity_by_id.get(item.source_entity_id).name
            if item.source_entity_id in entity_by_id
            else item.source_entity_id,
            "relation_type": item.relation_type,
            "target_entity_id": item.target_entity_id,
            "target_name": entity_by_id.get(item.target_entity_id).name
            if item.target_entity_id in entity_by_id
            else item.target_entity_id,
            "note": item.note,
            "is_directed": item.is_directed,
        }
        for item in relations
    ]

    return {
        "success": True,
        "data": {
            "project_id": project_id,
            "title": project.title,
            "characters": characters,
            "entities": [serialize_world_entity(item) for item in entities],
            "relations": relations_view,
            "facts": [
                {
                    "id": item.id,
                    "title": item.title,
                    "domain": (loads_json(item.data_json, {}).get("domain") or ""),
                    "summary": item.text_content,
                    "is_locked": item.is_locked,
                }
                for item in facts
            ],
            "maps": [
                {
                    "id": item.id,
                    "title": item.title,
                    "revision": item.revision,
                    "node_count": len(loads_json(item.map_json, {}).get("nodes") or []),
                }
                for item in maps
            ],
            "snapshots": [
                {
                    "id": item.id,
                    "title": item.title,
                    "source_kind": item.source_kind,
                    "source_status": item.source_status,
                    "char_count": item.char_count,
                    "indexing_status": item.indexing_status,
                }
                for item in snapshots
            ],
            "counts": {
                "characters": len(characters),
                "entities": len(entities),
                "relations": len(relations),
                "facts": len(facts),
                "maps": len(maps),
                "snapshots": len(snapshots),
            },
        },
    }


def map_service(session: Session = Depends(get_session)) -> WorldMapService:
    return WorldMapService(session)


def domain_service(session: Session = Depends(get_session)) -> WorldDomainService:
    return WorldDomainService(session)


def generation_service(session: Session = Depends(get_session)) -> WorldGenerationService:
    return WorldGenerationService(session)


class SuggestedFieldActionRequest(BaseModel):
    """确认或忽略一个 AI 建议的字段。"""

    domain: str = Field(description="目标模块 key")
    field: str = Field(description="字段名")


class WorldDomainExpansionRequest(BaseModel):
    """按层次策略细化一个模块（异步执行，返回 task_id）。"""

    domain: str = Field(description="目标模块 key（须已启用）")
    template_id: str = Field(default="", description="世界构建模板 id")
    prompt_override: str = Field(default="", description="单次覆盖提示词")
    hint: str = Field(default="", description="本次细化的补充要求（写进提示词 {hint}）")
    limit: int = Field(default=12, description="本次最多新增条目数（1-40）")
    provider: str = Field(default="")
    model: str = Field(default="")


class WorldEntityExpansionRequest(BaseModel):
    """按域属性契约补充一个实体的字段（生成链路）。"""

    entity_id: str = Field(description="目标实体 id（world_entities.id）")
    fields: list[str] = Field(
        default_factory=list, description="待补充字段，必须属于该模块的属性契约"
    )
    template_id: str = Field(default="", description="使用的世界构建模板 id（留空用默认提示词）")
    prompt_override: str = Field(default="", description="单次覆盖提示词（留空用模板/默认）")
    provider: str = Field(default="")
    model: str = Field(default="")


def _serialize_domain_definition(row: WorldDomainDefinition) -> dict[str, Any]:
    return {
        "key": row.domain_key,
        "label": row.label,
        "entity_type": row.entity_type,
        "extra_attributes": loads_json(row.extra_attributes_json, []),
        "prompt_hint": row.prompt_hint,
        "is_enabled": row.is_enabled,
        "source": row.source,
    }


class WorldTemplateUpsertRequest(BaseModel):
    """新建或更新世界构建模板（层次策略 + 每档提示词）。"""

    template_id: str = Field(default="", description="留空为新建")
    name: str = Field(default="")
    layers: list[str] = Field(default_factory=list, description="层次策略，名称与层数由项目决定")
    prompts: dict[str, Any] = Field(
        default_factory=dict,
        description="每档提示词：{draft_world, expand_domain, expand_entity}",
    )
    is_default: bool = Field(default=False, description="设为该项目默认模板")


@router.get(
    "/api/v1/projects/{project_id}/world-templates",
    summary="列出世界构建模板（内置种子 + 项目私有）",
)
def list_world_templates(
    project_id: str, svc: WorldGenerationService = Depends(generation_service)
):
    """模板承载层次策略与提示词：层次叫什么、有几层由项目数据决定，不写死在代码里。"""
    return {"success": True, "data": {"templates": svc.list_templates(project_id)}}


@router.post(
    "/api/v1/projects/{project_id}/world-templates",
    summary="新建或更新世界构建模板",
)
def upsert_world_template(
    project_id: str,
    req: WorldTemplateUpsertRequest,
    svc: WorldGenerationService = Depends(generation_service),
):
    try:
        row = svc.upsert_template(
            project_id,
            template_id=req.template_id,
            name=req.name,
            layers=req.layers,
            prompts=req.prompts,
            is_default=req.is_default,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": svc._serialize_template(row)}


@router.delete(
    "/api/v1/projects/{project_id}/world-templates/{template_id}",
    summary="删除项目私有模板（内置模板不可删）",
)
def delete_world_template(
    project_id: str,
    template_id: str,
    svc: WorldGenerationService = Depends(generation_service),
):
    svc.delete_template(project_id, template_id)
    return {"success": True, "data": {"project_id": project_id, "template_id": template_id}}


class WorldTemplateDraftRequest(BaseModel):
    """让 AI 按项目已启用模块与补充要求起草一份模板草案（不落库）。"""

    domain: str = Field(default="", description="重点服务的模块 key（可选，须已启用）")
    hint: str = Field(default="", description="对层次策略与提示词的补充要求")
    provider: str = Field(default="")
    model: str = Field(default="")


@router.post(
    "/api/v1/projects/{project_id}/world-templates/draft",
    summary="AI 起草世界构建模板草案（不落库，确认后再保存）",
)
async def draft_world_template(
    project_id: str,
    req: WorldTemplateDraftRequest,
    svc: WorldGenerationService = Depends(generation_service),
):
    """让 LLM 参考项目已启用模块起草 {name, layers, prompts} 草案。

    草案只是回显预览，需用户/智能体确认后走 ``POST /world-templates`` 保存（R4 纪律）。
    """
    try:
        draft = await svc.draft_template(
            project_id,
            domain=req.domain,
            hint=req.hint,
            provider=req.provider or None,
            model=req.model or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": draft}


@router.post(
    "/api/v1/projects/{project_id}/world-generation/expand-entity/preview",
    summary="预览实体属性补充的提示词（不调用模型）",
)
def preview_entity_expansion(
    project_id: str,
    req: WorldEntityExpansionRequest,
    svc: WorldGenerationService = Depends(generation_service),
):
    """生成前先看提示词：不消耗配额，可据此调整模板或单次覆盖（R4）。"""
    try:
        preview = svc.preview_entity_expansion(
            project_id,
            req.entity_id,
            fields=req.fields,
            template_id=req.template_id or None,
            prompt_override=req.prompt_override,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": preview}


async def _run_domain_expansion_task(task_id: str, project_id: str, req: WorldDomainExpansionRequest):
    """后台执行域级细化：进度写既有任务中心，业务状态落在 WorldExtractionRun。

    任务中心（内存队列 + ProjectTaskRecord）负责进度展示与通知；真正的可靠状态源是
    数据库中的运行记录——进程重启后任务执行不会恢复，但已落库的运行与候选不会丢。
    """
    from app.core.task_queue import TaskStatus, get_task_queue

    queue = get_task_queue()
    try:
        await queue.update_progress(task_id, 10, "正在准备域级细化")
        with SessionLocal() as session:
            service = WorldGenerationService(session)
            result = await service.expand_domain(
                project_id,
                req.domain,
                template_id=req.template_id or None,
                prompt_override=req.prompt_override,
                hint=req.hint,
                limit=req.limit,
                provider=req.provider or None,
                model=req.model or None,
            )
        tracked = await queue.get_task(task_id)
        if tracked:
            tracked.status = TaskStatus.DONE
            tracked.progress = 100
            tracked.progress_message = f"已产出 {result['candidate_count']} 条候选，去审阅确认"
            tracked.result = result
            tracked.completed_at = time.time()
            await queue.update_task(tracked)
    except Exception as exc:  # noqa: BLE001 - 异步任务必须收敛异常到任务状态
        tracked = await queue.get_task(task_id)
        if tracked:
            tracked.status = TaskStatus.FAILED
            tracked.progress = 100
            tracked.progress_message = "域级细化失败"
            tracked.error = str(exc)[:500]
            tracked.completed_at = time.time()
            await queue.update_task(tracked)


@router.post(
    "/api/v1/projects/{project_id}/world-generation/expand-domain",
    summary="AI 域级细化（异步，接入既有任务中心）",
)
async def expand_domain_attributes(
    project_id: str,
    req: WorldDomainExpansionRequest,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """按层次策略细化整个模块（成本高于单实体补充，故异步执行）。

    返回 ``task_id``，用既有 ``GET /api/v1/tasks/{task_id}`` 轮询进度（任务中心可见、
    支持 WebSocket 推送）；完成后 ``result`` 含 ``run_id`` 与候选数，再到
    ``/novel-world?run_id=`` 审阅确认。
    """
    from app.core.task_queue import get_task_queue

    svc = WorldGenerationService(session)
    specs = {spec.key for spec in svc.domains.resolve_specs(project_id)}
    if req.domain not in specs:
        raise HTTPException(status_code=400, detail=f"模块未启用或不存在：{req.domain}")

    queue = get_task_queue()
    task = await queue.create_task(
        task_type="world_domain_expansion",
        payload={
            "project_id": project_id,
            "domain": req.domain,
            "stage_label": f"细化{req.domain}模块",
        },
    )
    background.add_task(_run_domain_expansion_task, task.task_id, project_id, req)
    return {
        "success": True,
        "data": {
            "task_id": task.task_id,
            "status": "pending",
            "domain": req.domain,
            "poll": f"/api/v1/tasks/{task.task_id}",
        },
    }


@router.post(
    "/api/v1/projects/{project_id}/world-generation/expand-entity",
    summary="AI 补充实体属性（产出 ai_draft 候选，需确认后写入）",
)
async def expand_entity_attributes(
    project_id: str,
    req: WorldEntityExpansionRequest,
    svc: WorldGenerationService = Depends(generation_service),
):
    """按域属性契约补齐勾选的字段。

    - 只回写勾选且在契约内的字段，不覆盖已填内容（R3 / D-4）
    - 产出的是**候选**（`origin=ai_draft`、无证据），需确认后由 `apply` 写入，不直接改正典
    - 模型提出的新字段/新模块只作为建议落库，默认不启用（R7 / 梯子原则 I2）
    """
    try:
        result = await svc.expand_entity(
            project_id,
            req.entity_id,
            fields=req.fields,
            template_id=req.template_id or None,
            prompt_override=req.prompt_override,
            provider=req.provider or None,
            model=req.model or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": result}


@router.get(
    "/api/v1/projects/{project_id}/world-generation/suggestions",
    summary="列出待确认的 AI 结构建议（模块 + 字段）",
)
def list_world_building_suggestions(
    project_id: str, svc: WorldDomainService = Depends(domain_service)
):
    """AI 建议的结构变更在此可见、可确认——**不会自动成为 schema**（梯子原则 I2）。

    - ``domains``：AI 建议的新模块（落库为 ``ai_suggested``、默认未启用）
    - ``fields``：AI 建议的新字段（尚未进入任何模块的属性契约）

    确认：模块用 ``PUT /world-domains/{key}``（``source=custom``、``is_enabled=true``）；
    字段用下方的确认端点。忽略：模块用 ``DELETE``，字段用忽略端点。
    """
    return {"success": True, "data": svc.pending_suggestions(project_id)}


@router.post(
    "/api/v1/projects/{project_id}/world-generation/suggestions/fields/confirm",
    summary="确认字段建议（写入模块属性契约）",
)
def confirm_suggested_field(
    project_id: str,
    req: SuggestedFieldActionRequest,
    svc: WorldDomainService = Depends(domain_service),
):
    try:
        svc.confirm_suggested_field(project_id, req.domain, req.field)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": {"domain": req.domain, "field": req.field, "state": "confirmed"}}


@router.post(
    "/api/v1/projects/{project_id}/world-generation/suggestions/fields/ignore",
    summary="忽略字段建议（不再重复提示）",
)
def ignore_suggested_field(
    project_id: str,
    req: SuggestedFieldActionRequest,
    svc: WorldDomainService = Depends(domain_service),
):
    try:
        svc.ignore_suggested_field(project_id, req.domain, req.field)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": {"domain": req.domain, "field": req.field, "state": "ignored"}}


@router.get(
    "/api/v1/projects/{project_id}/world-domains",
    summary="列出项目世界模块（内置 + 项目扩展）",
)
def list_project_world_domains(
    project_id: str, svc: WorldDomainService = Depends(domain_service)
):
    """世界模块随项目演化：内置模块提供默认值，项目可覆盖、扩展字段、禁用或新增模块。

    ``attributes`` 为「内置字段 + 项目追加字段」，``builtin_attributes`` 标出哪些是内置的
    （内置字段不可删除，保证既有 ``attributes_json`` 始终可解析）。
    """
    return {"success": True, "data": {"domains": svc.list_domains(project_id)}}


@router.put(
    "/api/v1/projects/{project_id}/world-domains/{domain_key}",
    summary="新增或更新项目世界模块定义",
)
def upsert_project_world_domain(
    project_id: str,
    domain_key: str,
    req: WorldDomainUpsertRequest,
    svc: WorldDomainService = Depends(domain_service),
):
    """覆盖内置模块（改展示名/提示词、追加字段、禁用），或新增自定义模块。

    自定义模块的实体写入 ``world_entities``，``entity_type`` 取本定义值，无需新表。
    AI 建议的模块以 ``source=ai_suggested`` 落库，默认不参与提取，需用户确认后启用。
    """
    try:
        row = svc.upsert_definition(
            project_id,
            domain_key,
            label=req.label,
            entity_type=req.entity_type,
            extra_attributes=req.extra_attributes,
            prompt_hint=req.prompt_hint,
            is_enabled=req.is_enabled,
            source=req.source or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": _serialize_domain_definition(row)}


@router.delete(
    "/api/v1/projects/{project_id}/world-domains/{domain_key}",
    summary="重置项目世界模块定义（内置恢复默认，自定义移除）",
)
def reset_project_world_domain(
    project_id: str, domain_key: str, svc: WorldDomainService = Depends(domain_service)
):
    svc.reset_definition(project_id, domain_key)
    return {"success": True, "data": {"project_id": project_id, "domain_key": domain_key}}


@router.get("/api/v1/world-maps", summary="列出世界地图文档")
def list_world_maps(
    project_id: str | None = Query(None),
    snapshot_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    svc: WorldMapService = Depends(map_service),
):
    documents = svc.list_maps(project_id=project_id, snapshot_id=snapshot_id, limit=limit)
    return {"success": True, "data": [serialize_map(item) for item in documents]}


@router.post("/api/v1/world-maps", summary="创建世界地图文档")
def create_world_map(req: WorldMapCreateRequest, svc: WorldMapService = Depends(map_service)):
    document = svc.create_map(
        title=req.title,
        project_id=req.project_id,
        snapshot_id=req.snapshot_id,
        map_json=req.map_json,
    )
    return {"success": True, "data": serialize_map(document)}


@router.post("/api/v1/projects/{project_id}/world-maps/from-places", summary="从地点实体生成地图初稿")
def create_world_map_from_project_places(
    project_id: str,
    svc: WorldMapService = Depends(map_service),
):
    """把确认写入的地点实体转成地图据点初稿，已有地图时追加、无地图时新建。

    坐标是自动排布的占位，之后在地图工作台拖拽精修即可。
    """
    try:
        document = svc.create_map_from_project_places(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": serialize_map(document)}


@router.get("/api/v1/world-maps/{map_id}", summary="获取世界地图文档")
def get_world_map(map_id: str, svc: WorldMapService = Depends(map_service)):
    document = svc.get_map(map_id)
    if not document:
        raise HTTPException(status_code=404, detail="地图文档不存在")
    return {"success": True, "data": serialize_map(document)}


@router.put("/api/v1/world-maps/{map_id}", summary="保存世界地图（revision CAS）")
def update_world_map(
    map_id: str, req: WorldMapUpdateRequest, svc: WorldMapService = Depends(map_service)
):
    try:
        document = svc.update_map(
            map_id,
            map_json=req.map_json,
            expected_revision=req.expected_revision,
            title=req.title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"success": True, "data": serialize_map(document)}


@router.get("/api/v1/world-maps/{map_id}/render", summary="渲染世界地图为 SVG")
def render_world_map(map_id: str, svc: WorldMapService = Depends(map_service)):
    """把结构化地图确定性地渲染为 SVG。

    本地渲染，不调用模型也不依赖外部生图供应商；前端用 ``<img>`` 引用即可。
    """
    document = svc.get_map(map_id)
    if not document:
        raise HTTPException(status_code=404, detail="地图文档不存在")
    return Response(content=render_map_svg(document), media_type="image/svg+xml")


@router.get(
    "/api/v1/world-maps/{map_id}/entities", summary="解析地图据点关联的实体与证据"
)
def resolve_world_map_entities(
    map_id: str, svc: WorldMapService = Depends(map_service)
):
    """把地图据点与地点实体关联起来：引用不复制，实体信息按需回查。

    游离标记（没有 ``entity_id`` 或实体已不存在）的 ``entity`` 为 ``null``，
    前端应提示去关联实体，而不是把它当作正典。
    """
    try:
        resolved = svc.resolve_nodes_with_entities(map_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "data": resolved}


@router.get(
    "/api/v1/world-maps/{map_id}/export", summary="导出世界地图（结构化点位 JSON / SVG）"
)
def export_world_map(
    map_id: str,
    fmt: str = Query("json", alias="format", pattern="^(json|svg)$"),
    svc: WorldMapService = Depends(map_service),
):
    """导出结构化点位数据或 SVG。

    ``format=json`` 返回带 ``entity_id`` / ``evidence`` 的结构化点位数据（不是图片）；
    ``format=svg`` 复用确定性渲染，返回 SVG 文本。
    """
    document = svc.get_map(map_id)
    if not document:
        raise HTTPException(status_code=404, detail="地图文档不存在")
    if fmt == "svg":
        return Response(content=render_map_svg(document), media_type="image/svg+xml")
    resolved = svc.resolve_nodes_with_entities(map_id)
    return {"success": True, "data": build_map_export(document, resolved)}


@router.post(
    "/api/v1/world-maps/{map_id}/generate-visual/prompt-preview",
    summary="预览地图生图提示词",
)
def preview_world_map_visual_prompt(
    map_id: str,
    req: WorldMapVisualPromptRequest,
    svc: WorldMapService = Depends(map_service),
):
    """先预览再生成：把结构化地图转成生图 prompt，不消耗生图配额。"""
    document = svc.get_map(map_id)
    if not document:
        raise HTTPException(status_code=404, detail="地图文档不存在")
    prompt = (req.prompt_override or "").strip() or build_map_visual_prompt(
        document, style=req.style_override
    )
    return {"success": True, "data": {"map_id": map_id, "prompt": prompt}}


@router.post(
    "/api/v1/world-maps/{map_id}/generate-visual/prompt-optimize",
    summary="AI 优化地图生图提示词（只改写，不生成图）",
)
async def optimize_world_map_visual_prompt(
    map_id: str,
    req: WorldMapVisualOptimizeRequest,
    svc: WorldMapService = Depends(map_service),
):
    """用 LLM 润色生图 prompt（保留结构化事实与坐标方位），返回优化文本供确认后再生图。

    只改写提示词、不生成图、不落库；消耗一次 LLM 文本配额（R4 预览纪律）。
    """
    document = svc.get_map(map_id)
    if not document:
        raise HTTPException(status_code=404, detail="地图文档不存在")
    try:
        optimized_result = await optimize_map_visual_prompt(
            document,
            prompt=req.prompt or "",
            style=req.style or "",
            focus=req.focus or "",
            provider=req.provider or "",
            model=req.model or "",
        )
    except RuntimeError as exc:
        status = 503 if "未初始化" in str(exc) else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return {
        "success": True,
        "data": {
            "map_id": map_id,
            "prompt": optimized_result["prompt"],
            "optimized_prompt": optimized_result["optimized_prompt"],
        },
    }


@router.post("/api/v1/world-maps/{map_id}/generate-visual", summary="用生图模型生成地图视觉成图")
async def generate_world_map_visual(
    map_id: str,
    req: WorldMapVisualRequest,
    svc: WorldMapService = Depends(map_service),
):
    """把结构化地图转成生图 prompt，调用已配置的生图 Provider 生成视觉成图并入库。

    生成成图是派生的视觉资产，不是地图真相来源；结构化 ``map_json`` 仍是正典，
    成图只以引用形式记在 ``map_json.visuals`` 里。需要先在 AI 连接器配置
    ``provider_type=image`` 的 Provider 并初始化 AIService。
    """
    document = svc.get_map(map_id)
    if not document:
        raise HTTPException(status_code=404, detail="地图文档不存在")
    try:
        generated = await generate_map_visual(
            svc.session,
            document,
            prompt=req.prompt or "",
            style=req.style or "",
            negative_prompt=req.negative_prompt or "",
            size=req.size or "1024x1024",
            n=req.n or 1,
            provider=req.provider or "",
            model=req.model or "",
            reference_images=req.reference_images or [],
            save_to_asset_hub=req.save_to_asset_hub,
        )
    except RuntimeError as exc:
        status = 503 if "未初始化" in str(exc) else 500 if "未返回图片" in str(exc) else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return {"success": True, "data": {"map_id": map_id, **generated}}


@router.delete("/api/v1/world-maps/{map_id}", summary="删除世界地图文档")
def delete_world_map(map_id: str, svc: WorldMapService = Depends(map_service)):
    try:
        svc.delete_map(map_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "data": {"id": map_id}}


def _serialize_map_revision(row: Any, *, include_json: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": row.id,
        "map_id": row.map_id,
        "revision": row.revision,
        "title": row.title,
        "operator": row.operator,
        "summary": row.summary,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if include_json:
        data["map_json"] = loads_json(row.map_json, {})
    return data


@router.get("/api/v1/world-maps/{map_id}/revisions", summary="地图版本历史列表")
def list_world_map_revisions(
    map_id: str, svc: WorldMapService = Depends(map_service)
):
    document = svc.get_map(map_id)
    if not document:
        raise HTTPException(status_code=404, detail="地图文档不存在")
    revisions = svc.list_revisions(map_id)
    return {
        "success": True,
        "data": {
            "map_id": map_id,
            "current_revision": document.revision,
            "revisions": [_serialize_map_revision(row) for row in revisions],
        },
    }


@router.get("/api/v1/world-maps/{map_id}/revisions/{revision}", summary="读取指定版本快照")
def get_world_map_revision(
    map_id: str, revision: int, svc: WorldMapService = Depends(map_service)
):
    row = svc.get_revision(map_id, revision)
    if not row:
        raise HTTPException(status_code=404, detail=f"历史版本不存在：v{revision}")
    return {"success": True, "data": _serialize_map_revision(row, include_json=True)}


class WorldMapRollbackRequest(BaseModel):
    """回滚到指定历史版本（产生新 revision，不改写历史链）。"""

    revision: int = Field(description="目标历史版本号")
    operator: str = Field(default="", description="操作者标识（可选）")


@router.post(
    "/api/v1/world-maps/{map_id}/rollback",
    summary="回滚地图到指定版本（append-only：产生新 revision）",
)
def rollback_world_map(
    map_id: str,
    req: WorldMapRollbackRequest,
    svc: WorldMapService = Depends(map_service),
):
    try:
        document = svc.rollback(map_id, req.revision, operator=req.operator or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": serialize_map(document)}
